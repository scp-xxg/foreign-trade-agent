from copy import deepcopy
from types import SimpleNamespace
import sys
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from core.db.engine import Base
from core.foreign_trade import lexicon_hooks as hooks
from core.foreign_trade.inquiry import InquiryService,build_drafts
from core.foreign_trade.content import ContentPackService
from core.foreign_trade.review import ReviewService

NOTICE='【敏感词提示】L2 best，需人工复核，不是法律结论。'

def report():
    return {'status':'checked','matches':[{'rule_id':'test.best','level':'L2','field':'body','start':0,'end':4,'match':'best','reason':'待核验的夸大表达','suggestion':'采用可核验事实','source_section':'第3章','source_line':12,'source_url':'/api/v1/catalog/kb/kb_aaaaaaaaaaaaaaaa/documents/doc_bbbbbbbbbbbbbbbb'}], 'match_count':1,'version':'test-v1','source_name':'Synthetic private lexicon','source_sha256':'a'*64}

@pytest.fixture
def db():
    engine=create_engine('sqlite://');Base.metadata.create_all(engine)
    with Session(engine) as session:yield session
    engine.dispose()

@pytest.fixture
def fake_engine(monkeypatch):
    seen=[]
    def scan(db,uid,fields):
        seen.append((uid,deepcopy(fields)))
        return report()
    monkeypatch.setitem(sys.modules,'core.foreign_trade.lexicon',SimpleNamespace(scan_fields=scan,format_notice=lambda r:NOTICE))
    return seen

def test_scanner_exception_is_visible_without_private_error_details(monkeypatch):
    def fail(*a):raise RuntimeError('secret-private-value')
    monkeypatch.setitem(sys.modules,'core.foreign_trade.lexicon',SimpleNamespace(scan_fields=fail,format_notice=lambda r:''))
    r,n=hooks.scan_output(None,'owner',{'body':'draft'})
    assert r['status']=='error' and '检查未完成' in n and 'secret-private-value' not in n

@pytest.mark.asyncio
async def test_chat_stream_saved_text_and_child_reply_receive_the_same_notice(monkeypatch):
    monkeypatch.setattr(hooks,'scan_chat_output',lambda uid,text:(report(),NOTICE))
    emitted=[];segments=[]
    async def emit(event):emitted.append(event)
    turn=SimpleNamespace(full_response='Original best claim',user_id='owner',chat_id='chat',segments=SimpleNamespace(add_text=segments.append),emit=emit)
    await hooks.finish_chat_notice(turn,{})
    assert turn.full_response=='Original best claim\n\n'+NOTICE
    assert emitted[0]['delta']==segments[0] and turn.full_response.endswith(emitted[0]['delta'])
    assert await hooks.finish_child_notice('owner','Original best claim',emitted.append)==turn.full_response
    assert emitted[-1]['sub_type']=='content'
    monkeypatch.setattr(hooks,'scan_chat_output',lambda uid,text:({'status':'not_configured','matches':[]},''))
    assert await hooks.finish_child_notice('other','Original claim')=='Original claim'


def test_inquiry_generated_and_edited_drafts_keep_original_text(db,fake_engine):
    svc=InquiryService(db)
    row=svc.create('owner',{'title':'demo','buyer':{},'items':[]})
    expected=build_drafts(row)
    row=svc.draft('owner',row['id'],row['revision'])
    assert row['drafts']['en']==expected['en'] and row['drafts']['zh']==expected['zh']
    assert row['drafts']['sensitive_terms']['match_count']==1 and NOTICE in row['drafts']['warnings']
    row=svc.update_drafts('owner',row['id'],row['revision'],{'en':'best product','zh':'原始稿件'})
    assert row['drafts']['en']=='best product' and row['drafts']['zh']=='原始稿件'
    assert all(uid=='owner' for uid,_ in fake_engine)

@pytest.mark.asyncio
async def test_product_generation_checks_listing_bullets_and_faq_without_editing_facts(db,fake_engine,monkeypatch):
    import core.foreign_trade.content_generation as generation
    output={'listing':{'title':'Best','description':'best body','bullets':['best bullet']},'faq':[{'question':'best?','answer':'best answer'}],'warnings':[],'assets':[],'generated_at':'2026-11-01T00:00:00Z'}
    async def generate(*a):return deepcopy(output)
    monkeypatch.setattr(generation,'generate_pack',generate)
    svc=ContentPackService(db);row=svc.create('owner','pack')
    facts=[{'label':'Material','value':'PP','source_url':''}]
    row=svc.update('owner',row['pack_id'],row['revision'],{'product_name':'Demo','facts':facts})
    row=await svc.generate('owner',row['pack_id'],row['revision'],True,'ai')
    assert row['facts']==facts and row['outputs']['listing']==output['listing']
    assert row['outputs']['faq']==output['faq'] and NOTICE in row['outputs']['warnings']
    assert set(fake_engine[-1][1])=={'title','body','bullets[0]','faq[0].question','faq[0].answer'}


def test_review_saves_lexicon_provenance_and_detects_lexicon_version_change(db,monkeypatch):
    current=report()
    monkeypatch.setattr(hooks,'scan_output',lambda *a:(deepcopy(current),NOTICE))
    svc=InquiryService(db)
    row=svc.create('owner',{'buyer':{},'items':[{'sku':'DESK-001','quantity':500,'custom_packaging':False}],'destination_country':'Spain','is_demo_inquiry':True})
    row=svc.quote('owner',row['id'],row['revision'])
    values={'source_type':'inquiry','source_id':row['id'],'source_revision':row['revision'],'channel':'alibaba_rfq','draft':{'title':'Demo DESK-001','body':'best DEMO DESK-001 500 units standard packaging USD 2400.00. Freight and taxes excluded.','language':'en','locale':'en_US','bullets':[]}}
    review=ReviewService(db).create('owner',values)
    found=[a for a in review['text_annotations'] if a['category']=='sensitive_terms']
    assert len(found)==1 and found[0]['level']=='L2' and found[0]['source_line']==12
    assert review['draft']['body']==values['draft']['body']
    assert review['sensitive_terms']['source_sha256']=='a'*64
    current['source_sha256']='b'*64
    newer=ReviewService(db).create('owner',{**values,'previous_review_id':review['review_id']})
    assert newer['comparison']['rules_changed']


def test_review_scan_failure_and_receipt_capacity_are_visible():
    feedback={'text_annotations':[],'checks':[],'risk_labels':[],'summary':{}}
    rules=[]
    hooks.append_review_feedback(feedback,rules,{'status':'error','matches':[]},'amazon_listing')
    assert feedback['summary']['needs_confirmation_count']==1
    assert '检查未完成' in feedback['text_annotations'][0]['message']
    many=report()
    many['matches']=[dict(many['matches'][0],start=i,end=i+4) for i in range(120)]
    feedback={'text_annotations':[],'checks':[],'risk_labels':[],'summary':{}}
    hooks.append_review_feedback(feedback,[],many,'amazon_listing')
    assert many['review_truncated'] and many['review_visible_count']==100
    assert len(feedback['text_annotations'])==100


def test_quote_without_draft_checks_product_names_and_keeps_price_identity(db,monkeypatch):
    import core.foreign_trade.inquiry as inquiry
    items=[{'sku':'DESK-001','quantity':500,'custom_packaging':False}]
    original=inquiry.calculate_quote(items,'Spain',None)
    original['data']['items'][0]['name']='best simulated organizer'
    snapshot=deepcopy(original)
    monkeypatch.setattr(inquiry,'calculate_quote',lambda *a:deepcopy(snapshot))
    seen=[]
    def scan(db,owner,fields):
        seen.append((owner,fields))
        return report(),NOTICE
    monkeypatch.setattr(hooks,'scan_output',scan)
    svc=InquiryService(db)
    row=svc.create('owner',{'title':'quote only','buyer':{},'items':items,'destination_country':'Spain'})
    row=svc.quote('owner',row['id'],row['revision'])
    assert not row.get('drafts')
    assert row['quote']['data']==snapshot['data']
    assert row['quote']['warnings'][:-1]==snapshot['warnings']
    assert row['quote']['warnings'][-1]=={'code':'SENSITIVE_TERMS','message':NOTICE}
    assert all(isinstance(w,dict) and 'message' in w for w in row['quote']['warnings'])
    assert row['quote']['sensitive_terms']['match_count']==1
    assert seen[0][0]=='owner' and 'best simulated organizer' in seen[0][1]['items[0].name']
    assert svc.get('owner',row['id'])['quote']==row['quote']


@pytest.mark.parametrize('failed',[False,True])
def test_saturated_review_preserves_original_annotations_and_never_passes_lexicon(failed):
    annotations=[{'annotation_id':f'base_{i}','rule_id':'base_rule','status':'issue','message':'existing feedback'} for i in range(500)]
    original=deepcopy(annotations)
    feedback={'text_annotations':annotations,'checks':[],'risk_labels':[],'summary':{}}
    result={'status':'error','matches':[],'match_count':0} if failed else report()
    rules=[]
    hooks.append_review_feedback(feedback,rules,result,'amazon_listing')
    assert feedback['text_annotations']==original and len(feedback['text_annotations'])==500
    assert result['review_truncated'] and result['review_visible_count']==0
    assert feedback['checks'][-1]['status']=='needs_confirmation'
    assert feedback['checks'][-1]['annotation_count']==0
    assert feedback['risk_labels'][-1]['count']==1
    assert feedback['summary']['issue_count']==500
    assert feedback['summary']['needs_confirmation_count']==0
    assert feedback['summary']['review_status']=='needs_revision'
    assert '未完成' in rules[-1]['title'] if failed else '命中 1 处' in rules[-1]['title']
    assert result['review_notice'] and '未检出' not in rules[-1]['summary']

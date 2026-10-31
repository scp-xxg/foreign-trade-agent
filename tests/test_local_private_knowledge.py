"""Exercise the real CE HTTP contracts with isolated storage and owner-bound records."""
import io
from types import SimpleNamespace
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from core.db.engine import Base, get_db
from core.db.models import UserShadow
from core.auth.backend import get_current_user
from core.infra.exceptions import BadRequestError
from features.knowledge.models import KBSpace, KBDocument, KBChunk
from features.knowledge import runtime
from features.knowledge.api import kb_spaces, kb_documents, kb_mutations, kb_runtime, kb_chunks
from features.knowledge.personal_request_models import CreateKBSpaceRequest, UpdateKBSpaceRequest

@pytest.fixture
def local_kb(tmp_path, monkeypatch):
    engine = create_engine('sqlite:///' + str(tmp_path/'kb.db'), connect_args={'check_same_thread':False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as db:
        db.add_all([UserShadow(user_id='owner',username='owner'), UserShadow(user_id='other',username='other')]);db.commit()
    monkeypatch.setenv('LOCAL_PRIVATE_KB_ENABLED','true')
    monkeypatch.setattr(runtime,'local_mode_enabled',lambda:True)
    monkeypatch.setattr('core.models.embedding.resolve_embed_config',lambda:('','',''))
    monkeypatch.setattr('features.knowledge.wiki.llm.wiki_model_configured',lambda:True)
    monkeypatch.setattr('core.auth.capabilities.resolve_user_capabilities',lambda db,uid:{'can_create_private_kb':True})
    user=SimpleNamespace(user_id='owner')
    app=FastAPI()
    from api.middleware.error_handler import setup_error_handlers
    setup_error_handlers(app)
    for module in (kb_runtime,kb_spaces,kb_documents,kb_mutations,kb_chunks):app.include_router(module.router,prefix='/kb')
    def get_session():
        with Session() as db:yield db
    app.dependency_overrides[get_db]=get_session
    app.dependency_overrides[get_current_user]=lambda:user
    yield TestClient(app,raise_server_exceptions=False),Session,user,monkeypatch
    engine.dispose()


def test_create_and_update_real_ce_requests_preserve_modes_and_owner(local_kb):
    client,Session,user,_=local_kb
    created=client.post('/kb',json={'name':'测试外贸手册','index_modes':['wiki'],'wiki_config':{'granularity':'focused'}})
    assert created.status_code==201,created.text
    kid=created.json()['data']['kb_id']
    with Session() as db:
        row=db.get(KBSpace,kid);assert row.user_id=='owner'
        assert row.extra_data['index_modes']==['wiki']
        assert row.extra_data['wiki_config']['max_llm_calls']==100
    edited=client.patch('/kb/'+kid,json={'name':'新名称','wiki_config':{'content_instructions':'引用原文'}})
    assert edited.status_code==200,edited.text
    with Session() as db:
        row=db.get(KBSpace,kid)
        assert row.extra_data['index_modes']==['wiki']
        assert row.extra_data['wiki_config']['granularity']=='focused'
        assert row.extra_data['wiki_config']['content_instructions']=='引用原文'
    user.user_id='other'
    assert client.patch('/kb/'+kid,json={'name':'不可修改'}).status_code in (403,404)
    with Session() as db:assert db.get(KBSpace,kid).name=='新名称'


def test_missing_embedding_rejects_before_creating_space(local_kb):
    client,Session,_,_=local_kb
    caps=client.get('/kb/runtime').json()['data']
    assert caps=={'local_private_only':True,'embedding_configured':False,'wiki_configured':True,'default_index_modes':['wiki']}
    # Domain errors may be wrapped by the application's normal exception handlers.
    result=client.post('/kb',json={'name':'RAG not ready','index_modes':['rag']})
    assert result.status_code==400
    with Session() as db:assert db.query(KBSpace).count()==0
    assert client.post('/kb',json={'name':'Default Wiki'}).status_code==201


@pytest.mark.parametrize('modes',[[],['invalid'],['rag','wiki','rag']])
def test_invalid_index_modes_rejected_by_real_request_model(modes):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):CreateKBSpaceRequest(name='x',index_modes=modes)


def test_readiness_guard_precedes_storage_and_reindex_deletion(local_kb):
    client,Session,_,monkeypatch=local_kb
    with Session() as db:
        db.add(KBSpace(kb_id='kb_rag',user_id='owner',name='Existing RAG',visibility='private',extra_data={'index_modes':['rag']}))
        db.add(KBDocument(document_id='doc_rag',kb_id='kb_rag',title='Original',filename='a.md',size_bytes=5,mime_type='text/markdown',storage_key='safe',indexing_status='completed'))
        db.add(KBChunk(chunk_id='c_original',kb_id='kb_rag',document_id='doc_rag',chunk_index=0,content='preserve evidence'));db.commit()
    def no_storage():raise AssertionError('storage must not be called')
    monkeypatch.setattr(kb_documents,'get_storage',no_storage)
    assert client.post('/kb/kb_rag/documents',files={'file':('new.md',b'new content','text/markdown')}).status_code==400
    assert client.post('/kb/kb_rag/documents/doc_rag/reindex',json={}).status_code==400
    with Session() as db:
        assert db.query(KBDocument).count()==1
        assert db.get(KBChunk,'c_original').content=='preserve evidence'
        assert db.get(KBDocument,'doc_rag').indexing_status=='completed'


def test_wiki_upload_queues_without_embedding_and_blocks_other_owner(local_kb):
    client,Session,user,monkeypatch=local_kb
    created=client.post('/kb',json={'name':'Wiki intake','index_modes':['wiki']})
    kid=created.json()['data']['kb_id']
    saved=[]; queued=[]
    monkeypatch.setattr(kb_documents,'get_storage',lambda:SimpleNamespace(upload_bytes=lambda content,key:saved.append(content)))
    monkeypatch.setattr(kb_documents.kb_helpers,'enqueue_document_indexing',lambda db,**values:queued.append(values))
    result=client.post('/kb/'+kid+'/documents',files={'file':('sample.md',b'# Product\nFacts from supplied document.','text/markdown')})
    assert result.status_code==201,result.text
    assert len(saved)==len(queued)==1
    assert queued[0]['index_modes']==['wiki']
    user.user_id='other'
    assert client.post('/kb/'+kid+'/documents',files={'file':('other.md',b'not owned','text/markdown')}).status_code in (403,404)
    assert len(saved)==1


def test_local_catalog_opt_in_keeps_other_deployment_gates(monkeypatch):
    from features.workbench.catalog import project
    monkeypatch.setattr('features.workbench.catalog.local_mode_enabled',lambda:True)
    monkeypatch.setattr(runtime,'local_mode_enabled',lambda:True)
    item={'applicationKey':'builtin:my_space','enabled':True}
    layout={'defaultPinned':[],'forced':[]}
    monkeypatch.delenv('LOCAL_PRIVATE_KB_ENABLED',raising=False)
    assert project(item,layout)['availability']=={'available':False,'reason':'origin_unavailable'}
    monkeypatch.setenv('LOCAL_PRIVATE_KB_ENABLED','true')
    enabled=project(item,layout)
    assert enabled['availability']['available'] and enabled['localPrivateKnowledgeOnly']
    assert project({**item,'enabled':False},layout)['availability']['available'] is False
    monkeypatch.setattr(runtime,'local_mode_enabled',lambda:False)
    assert not runtime.local_private_knowledge_enabled()


def test_explicit_existing_admin_enable_is_narrow_and_idempotent(local_kb):
    from foreign_trade.enable_private_kb import grant_existing_admin
    _,Session,_,_=local_kb
    original={'role':'super_admin','can_switch_model':False,'marker':'retain','can_create_private_kb':False}
    with Session() as db:
        db.get(UserShadow,'owner').extra_data=original;db.commit()
        assert grant_existing_admin(db,'owner')['changed'] is True
        with Session() as readback:
            assert readback.get(UserShadow,'owner').extra_data=={**original,'can_create_private_kb':True}
        assert db.get(UserShadow,'owner').extra_data=={**original,'can_create_private_kb':True}
        assert grant_existing_admin(db,'owner')['changed'] is False
        assert db.get(UserShadow,'other').extra_data in (None,{})
        with pytest.raises(PermissionError):grant_existing_admin(db,'other')
        with pytest.raises(ValueError):grant_existing_admin(db,'missing')


def test_ce_wiki_routes_search_and_source_remain_owner_scoped(local_kb):
    from api.routes.v1 import CE_ROUTERS, iter_edition_routers
    from features.knowledge.models import KBWikiPage
    client,Session,user,monkeypatch=local_kb
    entries=[entry for entry in CE_ROUTERS if entry[0]=='features.knowledge.api.kb_wiki']
    assert len(entries)==1, 'The actual CE registry must expose Wiki reads'
    for _,router,_ in iter_edition_routers(entries):client.app.include_router(router)
    monkeypatch.setattr('core.db.engine.SessionLocal',Session)
    monkeypatch.setattr('features.knowledge.wiki.local_provider.SessionLocal',Session)
    monkeypatch.setattr('features.knowledge.wiki.local_graph.SessionLocal',Session)
    created=client.post('/kb',json={'name':'Owned Wiki','index_modes':['wiki']})
    kid=created.json()['data']['kb_id']
    with Session() as db:
        db.add(KBDocument(document_id='doc_source',kb_id=kid,title='原始手册',filename='source.md',size_bytes=20,mime_type='text/markdown',storage_key='safe',indexing_status='completed'))
        db.add(KBChunk(chunk_id='chunk_source',kb_id=kid,document_id='doc_source',chunk_index=0,content='样品退款同时要求30日内确认订单和800套。'))
        db.add(KBWikiPage(page_id='page_one',kb_id=kid,slug='concept/sample-refund',title='样品退款条件',page_type='concept',content='退款条件见原文。',summary='样品退款',source_refs=['doc_source'],chunk_refs=['chunk_source']))
        db.commit()
    path='/v1/catalog/kb/'+kid+'/wiki'
    assert client.get(path+'/capability').json()['data']['supports_wiki'] is True
    assert client.get(path+'/graph').status_code==200
    from extensions.mcp_servers.retrieve_dataset_content_mcp.wiki_impl import wiki_overview
    overview=wiki_overview(dataset_id=kid,allowed_kb_ids=kid,current_user_id='owner')
    assert overview['total_pages']==1
    search=client.get(path+'/search',params={'q':'退款'})
    assert search.status_code==200,search.text
    assert search.json()['data']['pages'][0]['slug']=='concept/sample-refund'
    source=client.get(path+'/source/concept/sample-refund')
    assert source.status_code==200,source.text
    assert source.json()['data']['chunks'][0]['document_title']=='原始手册'
    assert '800套' in source.json()['data']['chunks'][0]['content']
    def no_vectors(*args,**kwargs):raise AssertionError('Wiki source browsing must not require Milvus')
    monkeypatch.setattr('features.knowledge.vector_indexing.get_children_for_parent',no_vectors)
    assert client.get('/kb/'+kid+'/chunks/chunk_source/children').json()['data']=={'children':[],'count':0}
    assert client.patch('/kb/'+kid+'/chunks/chunk_source',json={'content':'unsafe direct edit'}).status_code==400
    with Session() as db:assert '800套' in db.get(KBChunk,'chunk_source').content
    user.user_id='other'
    assert client.get(path+'/capability').json()['data']['supports_wiki'] is False
    assert client.get(path+'/search',params={'q':'退款'}).status_code==403
    assert client.get(path+'/source/concept/sample-refund').status_code==403
    assert client.get(path+'/page/concept/sample-refund').status_code==403


def test_wiki_metadata_routes_queries_without_embedding(local_kb):
    client,Session,_,monkeypatch=local_kb
    monkeypatch.setattr('core.db.engine.SessionLocal',Session)
    kid=client.post('/kb',json={'name':'Wiki routing','index_modes':['wiki']}).json()['data']['kb_id']
    from extensions.mcp_servers.retrieve_dataset_content_mcp.impl import _list_local_datasets
    _,private=_list_local_datasets(allowed_kb_ids=None,current_user_id='owner')
    assert private[0]['index_modes']==['wiki']
    assert private[0]['capabilities']['vector'] is False
    assert private[0]['recommended_tools']==['wiki_locate','wiki_fetch_source']
    assert _list_local_datasets(allowed_kb_ids=None,current_user_id='other')==([],[])
    def no_embedding(*args,**kwargs):raise AssertionError('Wiki must not call embedding')
    monkeypatch.setattr('core.models.embedding.embed_text',no_embedding)
    from extensions.mcp_servers.retrieve_dataset_content_mcp.local_impl import retrieve_local_kb
    result=retrieve_local_kb(kid,'sample',allowed_kb_ids=kid,current_user_id='owner')
    assert result['error']['code']=='wiki_index_only'
    assert result['recommended_tools']==['wiki_locate','wiki_fetch_source']


def test_prompt_index_mode_changes_invalidate_cached_routing(local_kb):
    client,Session,_,monkeypatch=local_kb
    monkeypatch.setattr('core.db.engine.SessionLocal',Session)
    from prompts.kb_lite_section import _build_kb_lite_section,invalidate_kb_lite_cache
    invalidate_kb_lite_cache()
    kid=client.post('/kb',json={'name':'Mode change','index_modes':['wiki']}).json()['data']['kb_id']
    initial=_build_kb_lite_section([kid]);assert '仅 Wiki' in initial and 'wiki_fetch_source' in initial
    monkeypatch.setattr('core.models.embedding.resolve_embed_config',lambda:('http://embedding.invalid/v1','fixture',''))
    assert client.patch('/kb/'+kid,json={'index_modes':['rag']}).status_code==200
    updated=_build_kb_lite_section([kid]);assert 'RAG 向量检索' in updated and '仅 Wiki' not in updated
    invalidate_kb_lite_cache()


def test_permission_cli_preserves_existing_accounts_and_private_backup(local_kb,tmp_path):
    import json, sqlite3, stat, subprocess, sys
    from pathlib import Path
    _,Session,_,_=local_kb
    with Session() as db:
        db.get(UserShadow,'owner').extra_data={'role':'super_admin','keep':'unchanged'};db.commit()
    home=tmp_path/'cli-home';home.mkdir()
    original=Session.kw['bind'].url.database
    with sqlite3.connect(original) as src,sqlite3.connect(home/'data.db') as dst:src.backup(dst)
    root=Path(__file__).resolve().parents[1]
    command=[sys.executable,str(root/'extensions/foreign_trade/enable_private_kb.py'),'--app-home',str(home),'--username','owner','--enable-create']
    result=subprocess.run(command,cwd=root,capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr[-500:]
    receipt=json.loads(result.stdout.strip().splitlines()[-1])
    assert receipt['changed'] and not receipt['other_capabilities_changed']
    assert stat.S_IMODE(Path(receipt['backup']).stat().st_mode)==0o600
    with sqlite3.connect(home/'data.db') as db:
        value=json.loads(db.execute("SELECT metadata FROM users_shadow WHERE user_id='owner'").fetchone()[0])
        assert value=={'role':'super_admin','keep':'unchanged','can_create_private_kb':True}
        assert db.execute('SELECT count(*) FROM users_shadow').fetchone()[0]==2

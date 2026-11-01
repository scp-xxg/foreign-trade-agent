import json
from io import BytesIO
from pathlib import Path
import sys
import unittest
from unittest.mock import patch, MagicMock
from pydantic import ValidationError
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/backend'))
from core.foreign_trade.listing import ListingInput,prepare,adapt_image,STAGES,review_hash

def image_bytes(size=(600,400),mode='RGB'):
    out=BytesIO();Image.new(mode,size,'red').save(out,format='PNG');return out.getvalue()

class ListingTests(unittest.TestCase):
    def data(self):
        def fact(field,value):return dict(field=field,value=value,confirmed=True,evidence=[dict(source_id='s',excerpt=value)])
        return dict(batch_id='B1',as_of='2026-10-31T00:00:00Z',platform='test',site='US',language='en',
            sources=[dict(id='s',reference='spec and platform snapshot',text='Bottle M1 steel 500 ml 0.5 L 100 10 days Red White rules reviewed')],
            products=[dict(sku='A1',product_id='P1',version='v1',facts=[fact('name','Bottle'),fact('model','M1'),fact('material','steel'),fact('capacity','500 ml'),fact('moq','100'),fact('delivery','10 days')])],
            rules=dict(version='r1',retrieved_at='2026-10-30T00:00:00Z',valid_until='2026-11-30T00:00:00Z',evidence=[dict(source_id='s',excerpt='rules')],
                categories=[dict(id='c',path='Bottle',match_fields=['name'],attributes=[dict(field='material',values=['steel'])])],required_fields=['name','model','material','moq','delivery'],title_max=100,description_max=1000,min_images=1,min_width=100,min_height=100,max_width=500,max_height=500,max_image_bytes=1000000,formats=['PNG'],forbidden_terms=['guaranteed']),
            selections=[dict(sku='A1',category_id='c',confirmed=True)],
            keywords=[dict(sku='A1',term='steel bottle',intent='purchase',fact_fields=['name','material'],confirmed=True)],
            drafts=[dict(sku='A1',title='Bottle M1 steel',description='Bottle M1 steel 0.5 L MOQ 100 delivery 10 days',fact_fields=['name','model','material','capacity','moq','delivery'],reviewed=True)],
            media=[dict(sku='A1',file_id='f',role='main',sku_confirmed=True,rights_reference='owner supplied',appearance_reviewed=True)])
    def req(self,**kw):
        data=self.data();data.update(kw);return ListingInput(**data)
    def test_normalization_equivalence_and_provenance(self):
        d=self.data();d['products'][0]['facts'].append(dict(field='容量',value='0.5 L',confirmed=True,evidence=[dict(source_id='s',excerpt='0.5 L')]))
        x=prepare(ListingInput(**d),'normalize')['items'][0]
        self.assertEqual(x['facts']['capacity']['value'],'0.5 L');self.assertEqual(x['facts']['capacity']['state'],'confirmed')
        self.assertEqual(len(x['facts']['capacity']['entries']),2)
    def test_conflicts_missing_and_expired(self):
        d=self.data();d['products'][0]['facts'][2]['valid_until']='2026-10-29T00:00:00Z'
        d['products'][0]['facts'].append(dict(field='model',value='Red',confirmed=True,evidence=[dict(source_id='s',excerpt='Red')]))
        x=prepare(ListingInput(**d),'normalize')['items'][0]
        self.assertEqual(x['facts']['model']['state'],'conflict');self.assertEqual(x['facts']['material']['state'],'expired');self.assertTrue(x['issues'])
    def test_invalid_evidence_unknown_and_duplicates(self):
        for edit in ['quote','value','sku','reference','time']:
            d=self.data()
            if edit=='quote':d['products'][0]['facts'][0]['evidence'][0]['excerpt']='invented'
            if edit=='value':d['products'][0]['facts'][0]['value']='invented'
            if edit=='sku':d['products'].append(d['products'][0])
            if edit=='reference':d['keywords'][0]['sku']='unknown'
            if edit=='time':d['as_of']='2026-10-31T00:00:00'
            with self.subTest(edit=edit),self.assertRaises(ValidationError):ListingInput(**d)
    def test_taxonomy_requires_current_rules_and_confirmation(self):
        x=prepare(self.req(),'taxonomy')['items'][0];self.assertEqual(x['attributes'][0]['state'],'mapped');self.assertFalse(x['needs_confirmation'])
        x=prepare(self.req(selections=[]),'taxonomy')['items'][0];self.assertTrue(x['needs_confirmation']);self.assertEqual(x['candidates'][0]['matched_fields'],['name'])
        x=prepare(self.req(as_of='2027-01-01T00:00:00Z'),'taxonomy')['items'][0];self.assertTrue(x['needs_confirmation'])
        d=self.data();d['rules']['categories'][0]['attributes'][0]['values']=['wood']
        self.assertEqual(prepare(ListingInput(**d),'taxonomy')['items'][0]['attributes'][0]['state'],'invalid_enum')
    def test_keywords_never_invent_volume_and_duplicate_coverage(self):
        x=prepare(self.req(),'keywords')['items'][0];self.assertIsNone(x['keywords'][0]['search_volume'])
        d=self.data();d['keywords'][0]['search_volume']=500
        with self.assertRaises(ValidationError):ListingInput(**d)
        d=self.data();d['products'].append({**d['products'][0],'sku':'A2'});d['keywords'].append({**d['keywords'][0],'sku':'A2'})
        self.assertEqual(prepare(ListingInput(**d),'keywords')['items'][0]['keywords'][0]['duplicate_skus'],['A2'])
    def test_content_is_draft_and_format_checked(self):
        x=prepare(self.req(drafts=[]),'compose')['items'][0];self.assertFalse(x['reviewed']);self.assertIn('0.5 L',x['description'])
        d=self.data();d['rules']['title_max']=2
        self.assertFalse(prepare(ListingInput(**d),'compose')['items'][0]['format_passed'])
        self.assertFalse(prepare(self.req(),'compose')['published'])
    def test_real_image_resize_and_corrupt(self):
        content=image_bytes();payload,report=adapt_image(content,self.req().rules,convert=True)
        self.assertEqual((report['width'],report['height']),(500,333));self.assertTrue(report['spec_passed']);self.assertNotEqual(content,payload)
        with Image.open(BytesIO(payload)) as im:self.assertEqual(im.size,(500,333))
        with self.assertRaises((ValueError,OSError)):adapt_image(b'bad',self.req().rules,convert=True)
        _,report=adapt_image(image_bytes((50,40)),self.req().rules,convert=True);self.assertFalse(report['spec_passed']);self.assertEqual(report['width'],50)
    def reports(self,req):
        _,report=adapt_image(image_bytes((400,300)),req.rules,convert=False)
        return [dict(**report,sku='A1',file_id='f',role='main')]
    def ready(self):
        d=self.data();d['media'][0]['reviewed_sha256']=self.reports(ListingInput(**d))[0]['sha256'];req=ListingInput(**d)
        d['reviews']=[dict(sku='A1',check=c,state='passed',scope_hash=review_hash(req),evidence=[dict(source_id='s',excerpt='reviewed')]) for c in ['restricted_products','intellectual_property','claims']]
        return ListingInput(**d)
    def test_preflight_empty_missing_and_ready(self):
        x=prepare(self.req(products=[],selections=[],drafts=[],keywords=[],media=[]),'preflight');self.assertEqual(x['status'],'needs_products')
        x=prepare(self.req(rules=None),'preflight',self.reports(self.req()));self.assertEqual(x['status'],'needs_completion')
        req=self.ready();x=prepare(req,'preflight',self.reports(req));self.assertEqual(x['status'],'ready_for_publish_review');self.assertFalse(x['published'])
    def test_preflight_stale_review_media_mutation_and_content_block(self):
        req=self.ready();d=req.model_dump(mode='json');d['drafts'][0]['description']='guaranteed TBD'
        x=prepare(ListingInput(**d),'preflight',self.reports(req));codes={i['code'] for i in x['items'][0]['issues']}
        self.assertTrue({'forbidden_term','unresolved_placeholder','review_incomplete'}<=codes)
        reports=self.reports(req);reports[0]['sha256']='0'*64
        codes={i['code'] for i in prepare(req,'preflight',reports)['items'][0]['issues']};self.assertIn('media_changed_or_unreviewed',codes)
        self.assertNotEqual(prepare(req,'preflight',reports)['items'][0]['checked_input_hash'],prepare(req,'preflight',self.reports(req))['items'][0]['checked_input_hash'])
    def test_preflight_isolates_skus_and_duplicate_variants(self):
        req=self.ready();d=req.model_dump(mode='json');d['products'].append({**d['products'][0],'sku':'A2'});d['rules']['categories'][0]['variant_fields']=['material'];d['selections'].append(dict(sku='A2',category_id='c',confirmed=True))
        x=prepare(ListingInput(**d),'preflight',self.reports(req));self.assertEqual(len(x['items']),2)
        self.assertIn('duplicate_variant',{i['code'] for i in x['items'][0]['issues']})

class DispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_actions_catalog_gate_and_import(self):
        from core.llm.tools import foreign_trade_tool as adapter
        from core.capabilities.catalog.loader import _load_builtin_skill_metadata
        from core.foreign_trade.tool_names import TRADE_TOOL_NAMES
        ids={m.id for m in _load_builtin_skill_metadata()};required=[];kit=[]
        adapter.register_foreign_trade_tools(kit,user_id='owner',chat_id='chat',install_id='fixture',require_skill=required.append)
        call=next(t._func for t in kit if t.name=='trade_listing_prepare');self.assertIn('trade_listing_prepare',TRADE_TOOL_NAMES)
        data=ListingTests().data();data['media']=[]
        with patch.object(adapter,'_assert_available'):
            for stage,slug in STAGES.items():
                receipt=json.loads((await call(stage,data)).content[0].text)
                self.assertTrue(receipt['ok'],receipt);self.assertEqual(required[-1],slug);self.assertIn(slug,ids)
            with patch.object(adapter,'SessionLocal') as session,patch.object(adapter,'_attached_file_bytes',return_value=('spec.csv',b'SKU,name\nA1,Bottle')):
                receipt=json.loads((await call('normalize',data,file_ids=['f'])).content[0].text)
                self.assertTrue(receipt['ok']);self.assertIn('Bottle',receipt['data']['imported_documents'][0]['text'])
        def deny(slug):raise PermissionError('disabled')
        kit=[];adapter.register_foreign_trade_tools(kit,user_id='owner',chat_id='chat',install_id='fixture',require_skill=deny)
        call=next(t._func for t in kit if t.name=='trade_listing_prepare')
        with patch.object(adapter,'_assert_available'):
            receipt=json.loads((await call('normalize',data)).content[0].text);self.assertEqual(receipt['status'],403)
    async def test_media_attachment_permissions_and_actual_outputs(self):
        from core.llm.tools import foreign_trade_tool as adapter
        kit=[];adapter.register_foreign_trade_tools(kit,user_id='owner',chat_id='chat',install_id='fixture');call=next(t._func for t in kit if t.name=='trade_listing_prepare')
        with patch.object(adapter,'_assert_available'),patch.object(adapter,'SessionLocal'),patch.object(adapter,'_attached_file_bytes',return_value=('a.png',image_bytes())),patch('core.files.artifacts.service.store_bytes_as_artifact',return_value=MagicMock(artifact_id='generated')) as save:
            receipt=json.loads((await call('media',ListingTests().data())).content[0].text)
            self.assertTrue(receipt['ok'],receipt);self.assertEqual(receipt['data']['items'][0]['media'][0]['output_file_id'],'generated')
            self.assertEqual(save.call_args.kwargs['user_id'],'owner');self.assertEqual(save.call_args.kwargs['chat_id'],'chat')
            with Image.open(BytesIO(save.call_args.kwargs['content'])) as im:self.assertEqual(im.size,(500,333))
        from core.foreign_trade.content import ContentPackError
        with patch.object(adapter,'_assert_available'),patch.object(adapter,'SessionLocal'),patch.object(adapter,'_attached_file_bytes',side_effect=ContentPackError(404,'attachment unavailable')):
            receipt=json.loads((await call('preflight',ListingTests().data())).content[0].text);self.assertEqual(receipt['status'],404)

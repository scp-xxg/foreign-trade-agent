import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from pydantic import ValidationError
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src/backend'))
from core.foreign_trade.diligence import DiligenceInput, assess, run_stage, STAGES

class DiligenceTests(unittest.IsolatedAsyncioTestCase):
    def data(self, **changes):
        data=dict(company_name='Example Ltd',seller_product='steel bottles',as_of='2026-10-31T00:00:00Z',
                  evidence=[dict(id='registry-1',source_url='https://example.com/record',retrieved_at='2026-10-01T00:00:00Z',source_type='registry',text='Example Ltd registered in GB; record 123')],
                  findings=[dict(category='identity',subject='Example Ltd',field='registration',value='123',evidence_id='registry-1',excerpt='record 123')])
        data.update(changes);return data

    def test_identity_and_no_false_clearance(self):
        r=assess(DiligenceInput(**self.data()),'identity-check')
        self.assertTrue(r['needs_review']);self.assertEqual(r['status'],'evidence_pending_review')
        self.assertEqual(r['findings'][0]['source_type'],'registry')
        r=assess(DiligenceInput(company_name='Example'),'transaction-risk')
        self.assertEqual(r['status'],'incomplete_checks')
        self.assertTrue(all(c['status']=='not_queried' for c in r['query_coverage']))
        self.assertEqual(r['persistence_status'],'not_saved')

    def test_evidence_rejects_fabrication_future_duplicates(self):
        for change in [dict(evidence=[]),dict(as_of='2026-09-01T00:00:00Z'),dict(website='http://localhost'),dict(identity_reviewed=True),dict(company_name=' ')]:
            with self.assertRaises(ValidationError):DiligenceInput(**self.data(**change))
        data=self.data();data['findings'][0]['excerpt']='fabricated'
        with self.assertRaises(ValidationError):DiligenceInput(**data)
        data=self.data();data['evidence']*=2
        with self.assertRaises(ValidationError):DiligenceInput(**data)
        with self.assertRaises(ValidationError):DiligenceInput(**self.data(max_pages=True))

    def test_conflicts_unknowns_and_versions(self):
        data=self.data();data['findings'][0]['result']='conflicts'
        self.assertEqual(assess(DiligenceInput(**data),'identity-check')['status'],'conflict')
        req=DiligenceInput(company_name='Example')
        self.assertEqual(assess(req,'business-fit')['status'],'needs_seller_product')
        self.assertEqual(assess(req,'decision-chain')['status'],'insufficient_data')
        a=assess(req,'identity-check')['report_version']
        self.assertEqual(a,assess(req,'identity-check')['report_version'])
        self.assertNotEqual(a,assess(DiligenceInput(company_name='Other',as_of=req.as_of),'identity-check')['report_version'])

    def test_transaction_candidate_and_entity_change(self):
        data=self.data(contract_entity='Example Ltd',payee_entity='Other',account_changed=True)
        data['findings'][0].update(category='sanctions',result='candidate_hit')
        r=assess(DiligenceInput(**data),'transaction-risk')
        self.assertEqual(r['status'],'risk_review_required');self.assertEqual(len(r['risks']),3)
        self.assertEqual(r['query_coverage'][2]['status'],'not_queried') # registry is not sanctions source
        self.assertEqual(r['risks'][0]['severity'],'undetermined')
        data['evidence'][0]['source_type']='sanctions'
        r=assess(DiligenceInput(**data),'transaction-risk')
        self.assertEqual(r['query_coverage'][2]['status'],'evidence_pending_review')

    async def test_public_reads_and_missing_website(self):
        with patch('core.foreign_trade.diligence.due_diligence',new=AsyncMock(return_value={'unresolved':['website binding unknown']})) as public:
            for stage in ['identity-check','business-fit']:
                r=await run_stage(DiligenceInput(**self.data(website='https://example.com')),stage)
                self.assertIn('public_research',r)
            self.assertEqual(public.await_count,2)
        with patch('core.foreign_trade.diligence.discover_contacts',new=AsyncMock(return_value={'channels':[]})):
            self.assertIn('public_channels',await run_stage(DiligenceInput(**self.data(website='https://example.com')),'decision-chain'))
        self.assertNotIn('public_research',await run_stage(DiligenceInput(**self.data()),'identity-check'))

    async def test_chat_dispatch_skill_gate(self):
        from core.llm.tools import foreign_trade_tool as adapter
        from core.llm.foreign_trade_plugin import TradeSkillRequired
        toolkit=[];required=[]
        adapter.register_foreign_trade_tools(toolkit,user_id='fixture',chat_id=None,install_id='fixture',require_skill=required.append)
        call=next(t._func for t in toolkit if t.name=='trade_buyer_research')
        with patch.object(adapter,'_assert_available'):
            for stage,slug in STAGES.items():
                result=json.loads((await call(stage,self.data())).content[0].text)
                self.assertTrue(result['ok']);self.assertEqual(required[-1],slug)
        def deny(slug):raise TradeSkillRequired('fixture')
        toolkit=[];adapter.register_foreign_trade_tools(toolkit,user_id='fixture',chat_id=None,install_id='fixture',require_skill=deny)
        call=next(t._func for t in toolkit if t.name=='trade_buyer_research')
        with patch.object(adapter,'_assert_available'):
            self.assertFalse(json.loads((await call('identity-check',self.data())).content[0].text)['ok'])

    def test_api_auth_validation_and_catalog(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.routes.v1 import foreign_trade_buyers as api
        from core.auth import backend as auth
        app=FastAPI();app.include_router(api.router);client=TestClient(app)
        with patch.object(auth,'_auth_mode',return_value='session'),patch.object(auth,'_resolve_host_user',new=AsyncMock(return_value=None)),patch.object(auth,'_resolve_session_user',new=AsyncMock(return_value=None)):
            for stage in STAGES:self.assertEqual(client.post('/v1/foreign-trade/buyer-search/diligence/'+stage,json=self.data()).status_code,401)
        app.dependency_overrides[api.get_current_user]=lambda:object()
        for stage in STAGES:self.assertEqual(client.post('/v1/foreign-trade/buyer-search/diligence/'+stage,json=self.data()).status_code,200)
        self.assertEqual(client.post('/v1/foreign-trade/buyer-search/diligence/unknown',json=self.data()).status_code,422)
        from core.capabilities.catalog.loader import _load_builtin_skill_metadata
        ids={m.id for m in _load_builtin_skill_metadata()}
        root=Path(__file__).resolve().parents[1]
        for slug in STAGES.values():
            self.assertIn(slug,ids)
            self.assertEqual((root/'extensions/foreign_trade/plugin/skills'/slug/'SKILL.md').read_text(),(root/'src/backend/extensions/skills/default'/slug/'SKILL.md').read_text())

import sys
import unittest
from pathlib import Path
from pydantic import ValidationError
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/backend'))
from core.foreign_trade.lead_outreach import LeadInput, OutreachInput, prioritize, draft_outreach

class LeadOutreachTests(unittest.TestCase):
    def lead(self, **overrides):
        data=dict(buyer_id='fixture',dossier_version='1',review_version='2',review_decision='suitable',review_reason='checked',has_channel=True,
            assessments=[dict(dimension=d,result='match',excerpt='Fixture evidence',source_url='https://example.com',retrieved_at='2026-10-31') for d in ['product','buyer_type','market','supply']])
        data.update(overrides)
        return LeadInput(**data)

    def outreach(self, **overrides):
        data=dict(lead=self.lead(),channel='sales@example.com',channel_type='email',channel_source_url='https://example.com/contact',channel_retrieved_at='2026-10-31',company_name='Fixture Buyer',sender_company='Fixture Supplier',product_en='Water bottles',supplier_claim_en='MOQ: 500 pieces.',supplier_claim_reference='Merchant catalog page 2',facts_confirmed=True)
        data.update(overrides)
        return OutreachInput(**data)

    def test_unknown_is_not_mismatch_but_limits_priority(self):
        assessments=[dict(dimension='product',result='match',excerpt='Bottles',source_url='https://example.com',retrieved_at='2026-10-31')]
        r=prioritize(self.lead(assessments=assessments))
        self.assertEqual(r['fit_score'],100);self.assertEqual(r['evidence_coverage'],.35)
        self.assertEqual(r['priority'],'research_first');self.assertEqual(r['ranking_score'],35)
        r=prioritize(self.lead(assessments=[]));self.assertIsNone(r['fit_score'])

    def test_stop_and_review_gates(self):
        for changes in [dict(do_not_contact=True),dict(hard_excluded=True),dict(review_decision='unsuitable')]:
            lead=self.lead(**changes)
            self.assertEqual(prioritize(lead)['priority'],'stop')
            with self.assertRaises(ValueError): draft_outreach(self.outreach(lead=lead))
        self.assertEqual(prioritize(self.lead(has_channel=False))['priority'],'research_first')
        with self.assertRaises(ValueError):draft_outreach(self.outreach(facts_confirmed=False))
        with self.assertRaises(ValueError):draft_outreach(self.outreach(lead=self.lead(review_decision='unknown')))

    def test_duplicate_and_unsourced_assessments_rejected(self):
        a=self.lead().assessments[0]
        with self.assertRaises(ValidationError):self.lead(assessments=[a,a])
        with self.assertRaises(ValidationError):self.lead(assessments=[dict(dimension='product',result='match')])
        with self.assertRaises(ValidationError):self.outreach(channel='invalid')
        with self.assertRaises(ValidationError):self.outreach(product_en='[TODO]')

    def test_draft_uses_supplied_facts_and_team_greeting(self):
        r=draft_outreach(self.outreach(buyer_fact_en='We sell bottles.'))
        self.assertIn('Hello Fixture Buyer team',r['body']);self.assertIn('MOQ: 500 pieces.',r['body'])
        self.assertEqual(len(r['buyer_evidence']),1)
        self.assertEqual(r['review_status'],'draft');self.assertEqual(r['sending_status'],'not_sent')
        self.assertEqual(r['supplier_claims'][0]['type'],'user_statement')
        self.assertEqual(draft_outreach(self.outreach())['buyer_evidence'],[])
        lead=self.lead();lead.assessments[0].result='unknown'
        with self.assertRaises(ValueError):draft_outreach(self.outreach(lead=lead,buyer_fact_en='fact'))

    def test_authenticated_routes_and_catalog(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from unittest.mock import patch, AsyncMock
        from api.routes.v1 import foreign_trade_buyers as api
        from core.auth import backend as auth
        app=FastAPI();app.include_router(api.router);client=TestClient(app)
        with patch.object(auth,'_auth_mode',return_value='session'),patch.object(auth,'_resolve_host_user',new=AsyncMock(return_value=None)),patch.object(auth,'_resolve_session_user',new=AsyncMock(return_value=None)):
            for action in ['prioritize','outreach']:self.assertEqual(client.post('/v1/foreign-trade/buyer-search/'+action,json={}).status_code,401)
        app.dependency_overrides[api.get_current_user]=lambda:object()
        self.assertEqual(client.post('/v1/foreign-trade/buyer-search/prioritize',json=self.lead().model_dump()).status_code,200)
        self.assertEqual(client.post('/v1/foreign-trade/buyer-search/outreach',json=self.outreach(facts_confirmed=False).model_dump()).status_code,422)
        self.assertEqual(client.post('/v1/foreign-trade/buyer-search/outreach',json=self.outreach().model_dump()).status_code,200)
        from core.capabilities.catalog.loader import _load_builtin_skill_metadata
        ids={m.id for m in _load_builtin_skill_metadata()}
        for slug in ['trade-lead-prioritization','trade-personalized-outreach']:
            self.assertIn(slug,ids)
            root=Path(__file__).resolve().parents[1]
            self.assertEqual((root/'src/backend/extensions/skills/default'/slug/'SKILL.md').read_text(),(root/'extensions/foreign_trade/plugin/skills'/slug/'SKILL.md').read_text())

if __name__=='__main__':unittest.main()

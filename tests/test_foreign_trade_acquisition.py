"""Acquisition stages preserve evidence boundaries, auth and independent catalog skills."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/backend'))
from core.foreign_trade import acquisition as svc
from core.foreign_trade.public_data import PublicPage, PublicDataError
from pydantic import ValidationError

class AcquisitionTests(unittest.IsolatedAsyncioTestCase):
    def test_profile_is_unconfirmed_statement_draft(self):
        p=svc.draft_profile(svc.ProfileInput(product='Drinkware',markets=['DE'],constraints='MOQ 500'))
        self.assertEqual(p['status'],'draft'); self.assertEqual(p['rules'],[])
        self.assertEqual(p['evaluation_status'],'not_evaluated')
        self.assertIn('Drinkware distributor DE',p['search_plan'][0]['queries'])
        with self.assertRaises(ValidationError): svc.ProfileInput(product=' ')
        with self.assertRaises(ValidationError): svc.ResearchInput(company_name='A',website='http://127.0.0.1')
        with self.assertRaises(ValidationError): svc.ResearchInput(company_name='A',website='https://example.com',profile={'rules':[{'rule_id':'x','level':'must','basis':'hypothesis'}]})

    async def test_dossier_keeps_identity_unknown_and_hard_rule_rejection(self):
        async def verify(*args,**kwargs):
            return {'facts':[{'key':'lei','value':'fixture','source_url':'https://api.gleif.org/fixture'}], 'sources':[], 'warnings':[]}
        req=svc.ResearchInput(company_name='Fixture',website='https://www.example.com', profile={'rules':[{'rule_id':'x','level':'must','field':'domain','operator':'equals','value':'other.com'}]})
        d=await svc.due_diligence(req,verify=verify)
        self.assertEqual(d['decision'],'rejected');self.assertEqual(d['identity_status'],'unverified')
        req.profile={'rules':[]}
        d=await svc.due_diligence(req,verify=verify)
        self.assertEqual(d['decision'],'needs_review')
        self.assertEqual(d['buyer_id'],svc.buyer_id('http://example.com/other'))

    async def test_contacts_extract_only_explicit_public_evidence_dedupe_exclude(self):
        seen=[]
        def fetch(url):
            seen.append(url)
            return PublicPage(url, '''<script>secret@example.com</script><p>sales@example.com</p>
              <a href="mailto:sales@example.com">Mail</a><a href="mailto:old@example.com">Old</a>
              <p>Guess: first.last at example dot com</p><a href="/contact">Contact</a>
              <a href="https://other.com/team">Team</a>''','text/html','2026-10-31T00:00:00Z')
        result=await svc.discover_contacts(svc.ResearchInput(company_name='Fixture',website='https://example.com',excluded_channels=['OLD@example.com']),fetch=fetch)
        self.assertEqual(len(seen),2)
        self.assertEqual({c['channel'] for c in result['channels']},{'sales@example.com','https://example.com/contact'})
        self.assertTrue(all(c['role'] is None and c['deliverability']=='unknown' for c in result['channels']))
        self.assertTrue(all(c['source_url'] and c['retrieved_at'] for c in result['channels']))

    async def test_redirect_failures_and_budget_leave_no_fake_contacts(self):
        def redirect(url):return PublicPage('https://other.com','<p>x@other.com</p>','text/html','fixture')
        req=svc.ResearchInput(company_name='Fixture',website='https://example.com',max_pages=1)
        result=await svc.discover_contacts(req,fetch=redirect)
        self.assertEqual(result['channels'],[]);self.assertEqual(result['status'],'no_public_channel')
        def failure(url):raise PublicDataError('blocked')
        result=await svc.discover_contacts(req,fetch=failure)
        self.assertEqual(result['metrics']['pages_read'],0);self.assertEqual(result['sources'][0]['status'],'unavailable')

    def test_routes_require_auth_and_validate(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.routes.v1 import foreign_trade_buyers as api
        app=FastAPI();app.include_router(api.router)
        client=TestClient(app)
        from core.auth import backend as auth
        from unittest.mock import AsyncMock
        with patch.object(auth, '_auth_mode', return_value='session'), patch.object(auth, '_resolve_host_user', new=AsyncMock(return_value=None)), patch.object(auth, '_resolve_session_user', new=AsyncMock(return_value=None)):
            for stage in ['profile','due-diligence','contacts']:
                self.assertEqual(client.post('/v1/foreign-trade/buyer-search/'+stage,json={}).status_code,401)
        app.dependency_overrides[api.get_current_user]=lambda:object()
        self.assertEqual(client.post('/v1/foreign-trade/buyer-search/profile',json={'product':'Drinkware'}).status_code,200)
        self.assertEqual(client.post('/v1/foreign-trade/buyer-search/contacts',json={'company_name':'A','website':'http://localhost'}).status_code,422)

    def test_all_four_builtin_skills_backfill_existing_catalog(self):
        from core.capabilities.catalog.loader import _load_builtin_skill_metadata, _filter_to_static_defaults
        metadata={m.id:m for m in _load_builtin_skill_metadata()}
        slugs=['trade-customer-profile','trade-buyer-search','trade-buyer-due-diligence','trade-buyer-contact-discovery']
        for slug in slugs:self.assertIn(slug,metadata)
        data={'skills':[]};_filter_to_static_defaults(data,{'skills':[{'id':slug} for slug in slugs]})
        self.assertEqual({r['id'] for r in data['skills']},set(slugs))
        root=Path(__file__).resolve().parents[1]
        for slug in slugs:
            self.assertEqual((root/'src/backend/extensions/skills/default'/slug/'SKILL.md').read_text(),(root/'extensions/foreign_trade/plugin/skills'/slug/'SKILL.md').read_text())

    async def test_chat_tools_require_plugin_and_correct_skill(self):
        from core.llm.tools import foreign_trade_tool as adapter
        from core.llm.foreign_trade_plugin import TradeSkillRequired
        tools=[];required=[]
        adapter.register_foreign_trade_tools(tools,user_id='fixture',chat_id=None,install_id='fixture',require_skill=required.append)
        call=next(t._func for t in tools if t.name=='trade_buyer_research')
        with patch.object(adapter,'_assert_available'):
            result=json.loads((await call('profile',{'product':'Drinkware'})).content[0].text)
            self.assertTrue(result['ok']);self.assertEqual(required,['trade-customer-profile'])
        with patch.object(adapter,'_assert_available',side_effect=PermissionError()):
            result=json.loads((await call('profile',{'product':'Drinkware'})).content[0].text)
            self.assertEqual(result['status'],403)
        def blocked(name):raise TradeSkillRequired('read first')
        tools=[];adapter.register_foreign_trade_tools(tools,user_id='fixture',chat_id=None,install_id='fixture',require_skill=blocked)
        with patch.object(adapter,'_assert_available'):
            call=next(t._func for t in tools if t.name=='trade_buyer_research')
            result=json.loads((await call('contacts',{'company_name':'A','website':'https://example.com'})).content[0].text)
            self.assertEqual(result['status'],409)

if __name__=='__main__':unittest.main()

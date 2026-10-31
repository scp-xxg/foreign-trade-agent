"""Buyer discovery behavior; injected search/page fixtures never call live providers."""
import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/backend'))
from core.foreign_trade import buyer_search as svc
from core.foreign_trade.public_data import PublicPage, PublicDataError
from pydantic import ValidationError


def source(url, title='Fixture website'):
    return {'url': url, 'title': title, 'content': 'Fixture text'}


class BuyerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = patch.object(svc, 'search_available', return_value=True)
        self.config.start(); self.addCleanup(self.config.stop)

    async def test_dedupe_exclusion_pages_and_unknown_semantics(self):
        async def search(req):
            return {'status': 'complete', 'results': [source(u) for u in [
                'https://www.example.com/a','https://example.com/b','https://sub.excluded.com',
                'https://linkedin.com/company/x','http://127.0.0.1', 'https://example.org']]}
        async def fetch(url):
            return PublicPage(url,'<title>Fixture</title><p>Products</p>','text/html','2026-10-31T00:00:00Z')
        req=svc.SearchInput(product_terms=['drinkware'], excluded_domains=['excluded.com'],max_pages=1,
            profile={'rules':[{'rule_id':'R1','level':'must','field':'operating_markets','operator':'in','value':['DE']}]})
        run=await svc.run_search(req,search=search,fetch=fetch)
        self.assertEqual([c['domain'] for c in run['candidates']], ['example.com','example.org'])
        self.assertTrue(all(c['decision']=='needs_review' for c in run['candidates']))
        self.assertEqual(run['metrics']['pages_attempted'],1)
        self.assertEqual(run['metrics']['pages_read'],1)
        self.assertIsNone(run['metrics']['effective_lead_rate'])
        self.assertEqual(run['candidates'][1]['page_status'],'not_read')

    async def test_partial_failure_and_redirect_identity(self):
        calls=0
        async def search(req):
            nonlocal calls
            calls+=1
            if calls==2: raise RuntimeError('provider private details')
            return {'status':'complete','results':[source('https://example.com')]}
        async def fetch(url):
            return PublicPage('https://example.org','<p>Other</p>','text/html','now')
        result=await svc.run_search(svc.SearchInput(queries=['a','b']), search=search,fetch=fetch)
        self.assertEqual(result['stop_reason'],'search_error')
        self.assertEqual(len(result['candidates']),1)
        self.assertEqual(result['candidates'][0]['page_status'],'redirect_requires_review')
        self.assertNotIn('provider private details',str(result))

    async def test_target_and_low_yield_stops(self):
        async def populated(req): return {'status':'complete','results':[source('https://example.com'),source('https://example.org')]}
        result=await svc.run_search(svc.SearchInput(queries=['a','b'],target_count=1,max_pages=0),search=populated)
        self.assertEqual(result['stop_reason'],'target_reached')
        self.assertEqual(result['metrics']['queries_executed'],1)
        async def empty(req): return {'status':'complete','results':[]}
        result=await svc.run_search(svc.SearchInput(queries=['a','b','c','d']),search=empty)
        self.assertEqual(result['stop_reason'],'low_yield')
        self.assertEqual(result['metrics']['queries_executed'],3)

    def test_exact_rules_and_validation(self):
        rules=[{'rule_id':'D','level':'must','field':'domain','operator':'in','value':['www.example.com']}]
        self.assertEqual(svc.assess_rules(rules,'example.com')[1],'qualified')
        self.assertEqual(svc.assess_rules(rules,'example.org')[1],'rejected')
        self.assertEqual(svc.assess_rules([], 'example.com')[1],'needs_review')
        rules[0]['value']=[]
        self.assertEqual(svc.assess_rules(rules,'example.com')[1],'needs_review')
        with self.assertRaises(ValidationError): svc.SearchInput(product_terms=['a'], target_count=True)
        with self.assertRaises(ValidationError): svc.SearchInput(profile={'rules':[{'rule_id':'H','level':'must','basis':'hypothesis'}]})
        with self.assertRaises(ValueError): svc.make_plan(svc.SearchInput())
        req=svc.SearchInput(product_terms=['p'], queries=['explicit'],profile={'search_plan':[{'queries':['profile']} ]})
        self.assertEqual(svc.make_plan(req)['queries'],['explicit'])

    async def test_rejected_candidate_not_returned(self):
        async def search(req): return {'status':'complete','results':[source('https://example.com')]}
        req=svc.SearchInput(queries=['a'],max_pages=0,profile={'rules':[{'rule_id':'X','level':'exclude','field':'domain','operator':'equals','value':'example.com'}]})
        result=await svc.run_search(req,search=search)
        self.assertEqual(result['candidates'],[])
        self.assertEqual(result['search_log'][0]['skipped'],1)

    async def test_search_timeout_and_page_failure_preserve_results(self):
        async def timeout(req): raise TimeoutError()
        result=await svc.run_search(svc.SearchInput(queries=['a']),search=timeout)
        self.assertEqual(result['stop_reason'],'time_budget')
        self.assertEqual(result['candidates'],[])
        async def search(req): return {'status':'complete','results':[source('https://example.com')]}
        async def fetch(url): raise PublicDataError('blocked')
        result=await svc.run_search(svc.SearchInput(queries=['a']),search=search,fetch=fetch)
        self.assertEqual(result['candidates'][0]['page_status'],'unavailable')
        self.assertEqual(result['metrics']['pages_read'],0)

    async def test_chat_adapter_permissions_skill_and_validation(self):
        import json
        from core.llm.tools import foreign_trade_tool as adapter
        from core.llm.foreign_trade_plugin import TradeSkillRequired
        class Collector(list):
            def append(self, tool):
                super().append(tool)
                if tool.name=='trade_buyer_search': self.search=tool._func
        tools=Collector(); required=[]
        adapter.register_foreign_trade_tools(tools,user_id='fixture-owner',chat_id='fixture-chat',install_id='fixture-install',require_skill=required.append)
        def read(response): return json.loads(response.content[0].text)
        with patch.object(adapter,'_assert_available') as guard:
            result=read(await tools.search('plan',{'queries':['fixture query']}))
            self.assertTrue(result['ok'])
            self.assertEqual(required,['trade-buyer-search'])
            guard.assert_called_once_with('fixture-owner','fixture-install')
            result=read(await tools.search('run',{'target_count':True}))
            self.assertEqual(result['status'],422)
        with patch.object(adapter,'_assert_available',side_effect=PermissionError()):
            self.assertEqual(read(await tools.search('plan',{'queries':['a']}))['status'],403)
        required_tools=Collector()
        def require(name): raise TradeSkillRequired('Read skill first')
        adapter.register_foreign_trade_tools(required_tools,user_id='fixture-owner',chat_id=None,install_id='fixture-install',require_skill=require)
        with patch.object(adapter,'_assert_available'):
            self.assertEqual(read(await required_tools.search('plan',{'queries':['a']}))['status'],409)

    def test_api_requires_auth_and_returns_envelope(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.routes.v1 import foreign_trade_buyers as api
        app=FastAPI(); app.include_router(api.router)
        client=TestClient(app)
        from core.auth import backend as auth
        from unittest.mock import AsyncMock
        with patch.object(auth, '_auth_mode', return_value='session'), patch.object(auth, '_resolve_host_user', new=AsyncMock(return_value=None)), patch.object(auth, '_resolve_session_user', new=AsyncMock(return_value=None)):
            self.assertEqual(client.post('/v1/foreign-trade/buyer-search/plan',json={'product_terms':['a']}).status_code,401)
        app.dependency_overrides[api.get_current_user]=lambda: object()
        response=client.post('/v1/foreign-trade/buyer-search/plan',json={'product_terms':['a']})
        self.assertEqual(response.status_code,200)
        self.assertEqual(len(response.json()['data']['queries']),2)
        self.assertEqual(client.post('/v1/foreign-trade/buyer-search/plan',json={}).status_code,422)

if __name__=='__main__': unittest.main()

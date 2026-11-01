import sys
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from pydantic import ValidationError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/backend'))
from core.foreign_trade.negotiation import STAGES, NegotiationInput, negotiate

class NegotiationTests(unittest.TestCase):
    def request(self, **changes):
        data=dict(buyer_id='buyer',sources=[dict(id='s',reference='seller approved quote v1',text='approved costs and authority; buyer says too expensive; sample requested')])
        data.update(changes)
        return NegotiationInput(**data)
    def offer(self, **changes):
        data=dict(version='v1',currency='USD',unit_price='10',unit_cost='6',quantity=100,extra_cost='100',minimum_unit_price='8',minimum_margin_pct='20',max_discount_pct='15',proposed_unit_price='9',exchange_condition='advance payment',basis='approved costs and authority',authority_confirmed=True)
        data.update(changes)
        return data
    def test_exact_money_and_pending_review(self):
        result=negotiate(self.request(offer=self.offer()),'concession-planning')
        self.assertEqual(result['calculations'],dict(revenue='900.00',total_cost='700.00',profit='200.00',margin_pct='22.22',discount_pct='10.00',profit_reduction='100.00'))
        self.assertEqual(result['breaches'],[])
        self.assertTrue(result['internal_only']);self.assertTrue(result['approval_required'])
        self.assertFalse(result['sent']);self.assertFalse(result['saved'])
    def test_all_floor_and_authority_checks(self):
        result=negotiate(self.request(offer=self.offer(proposed_unit_price='7',authority_confirmed=False)),'concession-planning')
        self.assertEqual(set(result['breaches']),{'below_price_floor','below_margin_floor','discount_exceeds_authority','authority_unconfirmed'})
        self.assertEqual(result['status'],'approval_required')
    def test_missing_inputs_remain_unknown(self):
        result=negotiate(self.request(),'negotiation-strategy')
        self.assertEqual(result['opportunity_stage'],'unknown');self.assertIsNone(result['metrics']['business_accuracy'])
        self.assertEqual(negotiate(self.request(),'concession-planning')['status'],'needs_cost_and_authority')
        self.assertEqual(negotiate(self.request(),'objection-resolution')['status'],'needs_evidence')
    def test_validation_rejects_fabrication_and_bad_numbers(self):
        for change in [dict(unit_cost='-1'),dict(unit_cost='NaN'),dict(quantity=True),dict(quantity=0),dict(currency='usd'),dict(authority_confirmed='yes'),dict(basis='nonexistent')]:
            with self.subTest(change=change),self.assertRaises(ValidationError):self.request(offer=self.offer(**change))
        with self.assertRaises(ValidationError):self.request(claims=[dict(field='quote_requested',source_id='s',excerpt='invented')])
    def test_objections_are_evidence_linked_and_unresolved(self):
        req=self.request(claims=[dict(field='objection:price',source_id='s',excerpt='buyer says too expensive')])
        item=negotiate(req,'objection-resolution')['objections'][0]
        self.assertEqual(item['status'],'unresolved');self.assertEqual(item['cause'],'unknown')
        self.assertEqual(item['evidence']['reference'],'seller approved quote v1')
    def test_plan_is_not_actual_shipping_and_conflicts_need_review(self):
        result=negotiate(self.request(),'sample-trial')
        self.assertEqual(result['actual_state'],'not_recorded');self.assertIn('acceptance_criteria',result['missing_fields'])
        result=negotiate(self.request(claims=[dict(field=field,source_id='s',excerpt='sample requested') for field in ['sample_passed','sample_failed']]),'sample-trial')
        self.assertEqual(result['actual_state'],'requires_reconciliation')
    def test_opt_out_stops_all_actions(self):
        for action in STAGES:
            result=negotiate(self.request(do_not_contact=True),action)
            self.assertEqual(result['status'],'stopped');self.assertNotIn('calculations',result);self.assertNotIn('objections',result)

class DispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_catalog_and_skill_gate(self):
        from core.llm.tools import foreign_trade_tool as adapter
        from core.capabilities.catalog.loader import _load_builtin_skill_metadata
        ids={m.id for m in _load_builtin_skill_metadata()};toolkit=[];required=[]
        adapter.register_foreign_trade_tools(toolkit,user_id='fixture',chat_id=None,install_id='fixture',require_skill=required.append)
        call=next(t._func for t in toolkit if t.name=='trade_buyer_research')
        with patch.object(adapter,'_assert_available'):
            for stage,slug in STAGES.items():
                result=json.loads((await call(stage,dict(buyer_id='fixture'))).content[0].text)
                self.assertTrue(result['ok'],result);self.assertEqual(required[-1],slug);self.assertIn(slug,ids)
        def deny(slug):raise PermissionError('skill is not enabled')
        toolkit=[]
        adapter.register_foreign_trade_tools(toolkit,user_id='fixture',chat_id=None,install_id='fixture',require_skill=deny)
        call=next(t._func for t in toolkit if t.name=='trade_buyer_research')
        with patch.object(adapter,'_assert_available'):
            result=json.loads((await call('concession-planning',dict(buyer_id='fixture'))).content[0].text)
            self.assertFalse(result['ok'])

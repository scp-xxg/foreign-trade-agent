import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from pydantic import ValidationError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/backend'))
from core.foreign_trade.closing import ClosingInput, STAGES, close_order

class ClosingTests(unittest.TestCase):
    def ref(self,source='s',text='confirmed'):return [dict(source_id=source,excerpt=text)]
    def request(self,**changes):
        data=dict(order_id='SO-1',as_of='2026-10-31T12:00:00+08:00',sources=[dict(id='s',reference='email',text='confirmed 100 USD buyer account'),dict(id='policy',reference='policy v1',text='approved rules and account',kind='approved_policy'),dict(id='bank',reference='bank export',text='credit confirmed',kind='bank_record')])
        data.update(changes);return ClosingInput(**data)
    def requirement(self,id='a',phase='readiness',**changes):
        data=dict(id=id,phase=phase,label='条件',policy_evidence=self.ref('policy','approved'),state='confirmed',evidence=self.ref())
        data.update(changes);return data
    def term(self,field,value,document='quote',**changes):
        data=dict(field=field,value=value,document_id=document,version='v1',confirmed=True,evidence=self.ref())
        data.update(changes);return data
    def account(self):return dict(account_id='acct',beneficiary='seller',approved=True,evidence=self.ref('policy','account'))
    def payment(self,**changes):
        data=dict(transaction_id='t1',order_id='SO-1',kind='bank_credit',amount='100.10',currency='USD',payer='buyer',account_id='acct',at='2026-10-30T12:00:00+08:00',evidence=self.ref('bank','credit'))
        data.update(changes);return data
    def payment_request(self,**changes):
        data=dict(account=self.account(),currency='USD',expected_due='100.10',due_evidence=self.ref('s','100'),expected_payer='buyer',payments=[self.payment()],requirements=[self.requirement('pay','payment')])
        data.update(changes);return self.request(**data)
    def test_empty_never_passes(self):
        for stage in STAGES:
            r=close_order(self.request(),stage)
            self.assertTrue(r['approval_required']);self.assertFalse(r['saved']);self.assertFalse(r['sent']);self.assertFalse(r['execution_started'])
        self.assertEqual(close_order(self.request(),'closing-readiness')['status'],'needs_rules')
    def test_dependencies_and_conflicts_block(self):
        r=close_order(self.request(requirements=[self.requirement('a',state='pending'),self.requirement('b',depends_on=['a'])]),'closing-readiness')
        self.assertEqual(r['blocking_ids'],['a','b']);self.assertEqual(r['checklist'][1]['dependency_blockers'],['a'])
        r=close_order(self.request(requirements=[self.requirement()]),'closing-readiness')
        self.assertEqual(r['status'],'conditions_supported_pending_review')
    def test_bad_evidence_rules_dependencies_and_naive_dates(self):
        for change in [dict(as_of='2026-10-31T12:00:00'),dict(requirements=[self.requirement(evidence=[])]),dict(requirements=[self.requirement(policy_evidence=self.ref())]),dict(requirements=[self.requirement(depends_on=['missing'])]),dict(requirements=[self.requirement(depends_on=['a'])]),dict(requirements=[self.requirement(evidence=self.ref(text='invented'))])]:
            with self.subTest(change=change),self.assertRaises(ValidationError):self.request(**change)
    def test_versions_and_delivery_trigger_conflict(self):
        r=close_order(self.request(terms=[self.term('delivery','30 days after deposit'),self.term('delivery','30 days after drawing','po')]),'order-reconciliation')
        self.assertEqual(next(x for x in r['matrix'] if x['field']=='delivery')['state'],'conflict')
        self.assertIn('buyer',r['issues']);self.assertIn('delivery',r['issues'])
    def test_template_missing_and_approved_draft_exact_arithmetic(self):
        self.assertIsNone(close_order(self.request(),'sales-document-drafting')['draft'])
        template='PI {{buyer}} {{line_items}} {{subtotal}} {{currency}} {{account_id}} {{unknown}}'
        req=self.request(sources=[*self.request().model_dump()['sources'],dict(id='tpl',kind='approved_template',reference='template v1',text=template)],template=dict(kind='pi',version='v1',approved=True,text=template,evidence=self.ref('tpl',template)),terms=[self.term('buyer','Buyer Ltd'),self.term('currency','USD'),self.term('account_id','untrusted')],required_fields=['buyer','currency'],currency='USD',account=self.account(),lines=[dict(sku='A',description='product',quantity='3',unit='pcs',unit_price='0.10',evidence=self.ref())])
        r=close_order(req,'sales-document-drafting')
        self.assertEqual(r['subtotal'],'0.30');self.assertIn('acct',r['draft']);self.assertNotIn('untrusted',r['draft']);self.assertIn('unknown',r['missing_fields']);self.assertEqual(r['template_version'],'v1')
        with self.assertRaises(ValidationError):self.request(template=dict(kind='pi',version='v1',text=template,approved=True,evidence=self.ref()))
    def test_conflicting_term_not_filled(self):
        text='{{buyer}}'
        r=close_order(self.request(sources=[*self.request().model_dump()['sources'],dict(id='tpl',kind='approved_template',reference='tpl',text=text)],template=dict(kind='contract',version='v2',text=text,approved=True,evidence=self.ref('tpl',text)),terms=[self.term('buyer','A'),self.term('buyer','B','po')]),'sales-document-drafting')
        self.assertIn('【待确认：buyer】',r['draft'])
    def test_signature_steps_and_messages(self):
        r=close_order(self.request(requirements=[self.requirement('sent','signature'),self.requirement('signed','signature',state='pending',owner='sales',depends_on=['sent'])]),'order-confirmation')
        self.assertEqual(r['blocking_ids'],['signed']);self.assertEqual(len(r['next_actions']),1);self.assertEqual(r['signature_authenticity'],'not_verified')
    def test_payment_exact_and_not_bank_live(self):
        r=close_order(self.payment_request(),'payment-verification')
        self.assertEqual(r['matched_amount'],'100.10');self.assertEqual(r['difference'],'0.00');self.assertEqual(r['payment_condition'],'pending_review')
        r=close_order(self.payment_request(expected_due='101.10'),'payment-verification')
        self.assertEqual(r['difference'],'1.00');self.assertEqual(r['status'],'short_payment')
    def test_slip_promise_future_and_mismatches_never_count(self):
        for changes in [dict(kind='remittance_slip'),dict(kind='promise'),dict(kind='bank_credit',evidence=self.ref()),dict(order_id='other'),dict(currency='EUR'),dict(payer='other'),dict(account_id='other'),dict(at='2027-01-01T00:00:00Z')]:
            with self.subTest(changes=changes):
                r=close_order(self.payment_request(payments=[self.payment(**changes)]),'payment-verification')
                self.assertEqual(r['matched_amount'],'0');self.assertTrue(r['entries'][0]['exceptions']);self.assertEqual(r['payment_condition'],'unconfirmed')
    def test_duplicate_payment_and_lc_credit(self):
        with self.assertRaises(ValidationError):self.payment_request(payments=[self.payment(),self.payment()])
        for method in ['lc','credit']:
            r=close_order(self.payment_request(payment_method=method),'payment-verification')
            self.assertEqual(r['status'],'non_cash_conditions_pending_review');self.assertNotIn('arrived',r['payment_condition'])
    def test_handoff_missing_phases_and_terms(self):
        r=close_order(self.request(requirements=[self.requirement('h','handoff')]),'order-handoff')
        self.assertIn('payment',r['missing_rule_phases']);self.assertEqual(r['handoff_status'],'needs_completion')
        req=self.request(requirements=[self.requirement(p,p) for p in ['readiness','signature','payment','handoff']],terms=[self.term(f,'confirmed') for f in ['product','quantity','unit','packaging','inspection','delivery']])
        r=close_order(req,'order-handoff');self.assertEqual(r['handoff_status'],'draft_ready_for_acceptance');self.assertFalse(r['execution_started']);self.assertEqual(r['recipient_acceptance'],'not_recorded')

class DispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_dispatch_catalog_and_skill_gate(self):
        from core.llm.tools import foreign_trade_tool as adapter
        from core.capabilities.catalog.loader import _load_builtin_skill_metadata
        ids={m.id for m in _load_builtin_skill_metadata()}
        required=[];toolkit=[]
        adapter.register_foreign_trade_tools(toolkit,user_id='fixture',chat_id=None,install_id='fixture',require_skill=required.append)
        call=next(t._func for t in toolkit if t.name=='trade_buyer_research')
        with patch.object(adapter,'_assert_available'):
            for stage,slug in STAGES.items():
                result=json.loads((await call(stage,dict(order_id='SO-1',as_of='2026-10-31T00:00:00Z'))).content[0].text)
                self.assertTrue(result['ok'],result);self.assertEqual(required[-1],slug);self.assertIn(slug,ids)
        def deny(slug):raise PermissionError('skill disabled')
        toolkit=[];adapter.register_foreign_trade_tools(toolkit,user_id='fixture',chat_id=None,install_id='fixture',require_skill=deny)
        call=next(t._func for t in toolkit if t.name=='trade_buyer_research')
        with patch.object(adapter,'_assert_available'):
            result=json.loads((await call('closing-readiness',dict(order_id='SO-1',as_of='2026-10-31T00:00:00Z'))).content[0].text)
            self.assertFalse(result['ok'])

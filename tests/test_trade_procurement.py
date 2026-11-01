import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from pydantic import ValidationError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/backend'))
from core.foreign_trade.procurement import ProcurementInput,prepare,STAGES
E=[dict(source_id='s',excerpt='confirmed')]
class ProcurementTests(unittest.TestCase):
    def data(self):
        return dict(case_id='P1',as_of='2026-11-01T00:00:00Z',sources=[dict(id='s',reference='reviewed records',text='confirmed Bottle steel 500ml box')],requirements=[dict(id='l',sku='A',revision='v1',quantity=100,unit='pcs',need_by='2026-11-10T00:00:00Z',destination='Ningbo',available_stock=20,confirmed_inbound=10,safety_stock=5,inventory_confirmed=True,capability_checks=['capacity'],quality_checks=['size'],facts=[dict(field=k,value=v,confirmed=True,evidence=[dict(source_id='s',excerpt=v)]) for k,v in [('name','Bottle'),('material','steel'),('specification','500ml'),('packaging','box')]],evidence=E)],criteria=[dict(name='capacity')],suppliers=[dict(id='v',legal_name='Factory',country='CN',identity_reviewed=True,evidence=E,assessments=[dict(name='capacity',state='met',basis='independent_check',observed_at='2026-10-31T00:00:00Z',valid_until='2026-12-01T00:00:00Z',evidence=E)],capacities=[dict(line_id='l',revision='v1',unit='pcs',total=100,committed=25,available_by='2026-11-09T00:00:00Z',valid_until='2026-12-01T00:00:00Z',independently_checked=True,evidence=E)])],cost_basis='delivered net',required_costs=['freight'],offers=[dict(id='q',line_id='l',supplier_id='v',revision='v1',quantity=75,unit='pcs',currency='CNY',unit_price=10,moq=50,valid_until='2026-12-01T00:00:00Z',cost_basis='delivered net',costs={'freight':20},reviewed=True,evidence=E)])
    def run_stage(self,action,d=None):return prepare(ProcurementInput(**(d or self.data())),action)
    def codes(self,result):return {i['code'] for i in result['items'][0]['issues']}
    def test_net_quantity_and_capacity(self):
        self.assertEqual(self.run_stage('requirements')['items'][0]['net_purchase_quantity'],'75')
        self.assertEqual(self.run_stage('capability')['status'],'review_required')
        d=self.data();d['requirements'][0]['inventory_confirmed']=False
        self.assertIsNone(self.run_stage('requirements',d)['items'][0]['net_purchase_quantity'])
        self.assertFalse(self.run_stage('comparison',d)['items'][0]['offers'][0]['comparable'])
    def test_evidence_ids_time_and_finite(self):
        for change in ['quote','id','time','nan','link']:
            d=self.data()
            if change=='quote':d['sources'][0]['text']='unrelated'
            if change=='id':d['requirements'].append(d['requirements'][0])
            if change=='time':d['as_of']='2026-11-01T00:00:00'
            if change=='nan':d['offers'][0]['unit_price']='NaN'
            if change=='link':d['offers'][0]['supplier_id']='missing'
            with self.subTest(change=change),self.assertRaises(ValidationError):ProcurementInput(**d)
    def test_conflict_and_missing_specs(self):
        d=self.data();d['requirements'][0]['facts'].append(dict(field='material',value='box',confirmed=True,evidence=[dict(source_id='s',excerpt='box')]))
        self.assertIn('conflicting_fact',self.codes(self.run_stage('requirements',d)))
    def test_supplier_claim_and_expiry(self):
        d=self.data();d['suppliers'][0]['assessments'][0]['basis']='supplier_claim'
        self.assertIn('criterion_not_verified',self.codes(self.run_stage('sourcing',d)))
        d=self.data();d['as_of']='2027-01-01T00:00:00Z'
        self.assertIn('capacity_unverified_or_insufficient',self.codes(self.run_stage('capability',d)))
    def test_cost_and_unknown_costs(self):
        x=self.run_stage('comparison')['items'][0]['offers'][0];self.assertEqual(x['normalized_known_cost'],'770');self.assertEqual(x['cost_rank'],1)
        d=self.data();d['offers'][0]['costs']['freight']=None
        x=self.run_stage('comparison',d)['items'][0]['offers'][0];self.assertIsNone(x['cost_rank']);self.assertIn('unknown_costs',x['issues'])
    def test_fx_and_quantity(self):
        d=self.data();d['offers'][0]['currency']='USD';d['fx']=[dict(currency='USD',rate=7,observed_at='2026-10-31T00:00:00Z',valid_until='2026-12-01T00:00:00Z',evidence=E)]
        self.assertEqual(self.run_stage('comparison',d)['items'][0]['offers'][0]['normalized_known_cost'],'5390')
        d['offers'][0]['quantity']=100;self.assertIsNone(self.run_stage('comparison',d)['items'][0]['offers'][0]['cost_rank'])
    def quality(self):return dict(id='qc',line_id='l',revision='v1',name='size',stage='sample',standard='length',method='caliper',owner='QA',state='passed',reviewed=True,sample_version='s1',measured_value=10,lower_limit=9,upper_limit=11,measurement_unit='mm',evidence=E)
    def test_quality_bounds_missing_and_revision(self):
        d=self.data();d['quality_checks']=[self.quality()];self.assertEqual(self.run_stage('quality',d)['status'],'review_required')
        for field,value,code in [('measured_value',12,'measurement_out_of_bounds'),('measured_value',None,'measurement_missing'),('revision','old','stale_quality_revision')]:
            d['quality_checks']=[{**self.quality(),field:value}];self.assertIn(code,self.codes(self.run_stage('quality',d)))
    def milestone(self):return dict(id='m',line_id='l',revision='v1',name='production',owner='buyer',planned_at='2026-10-30T00:00:00Z',observed_at='2026-10-28T00:00:00Z',remaining_hours=300,evidence=E)
    def test_delivery_risk_stale_overdue(self):
        d=self.data();d['milestones']=[self.milestone()];x=self.run_stage('delivery',d)
        self.assertTrue({'overdue','stale_progress','delivery_at_risk'}<=self.codes(x));self.assertFalse(x['items'][0]['monitor_created'])
    def test_dependencies_and_cycles(self):
        d=self.data();d['milestones']=[{**self.milestone(),'depends_on':['m']}]
        with self.assertRaises(ValidationError):ProcurementInput(**d)
        d['milestones']=[self.milestone(),{**self.milestone(),'id':'m2','depends_on':['m'],'actual_at':'2026-10-27T00:00:00Z'}]
        self.assertIn('dependency_unfinished',self.codes(self.run_stage('delivery',d)))
    def settlement(self):
        d=self.data();d['orders']=[dict(line_id='l',order_id='po',supplier_id='v',revision='v1',quantity=75,unit='pcs',currency='CNY',unit_price=10,approved=True,evidence=E)];d['receipts']=[dict(id='r',document_number='R1',line_id='l',order_id='po',revision='v1',unit='pcs',batch='b1',received=75,accepted=75,rejected=0,reviewed=True,evidence=E)];d['invoices']=[dict(id='i',number='I1',line_id='l',order_id='po',supplier_id='v',revision='v1',unit='pcs',currency='CNY',quantity=75,unit_price=10,reviewed=True,evidence=E)];d['adjustments']=[dict(id='a',line_id='l',order_id='po',currency='CNY',kind='payment',amount=100,confirmed=True,evidence=E)];return d
    def test_settlement_balance_and_no_payment(self):
        x=self.run_stage('settlement',self.settlement())['items'][0];self.assertEqual(x['reconciled_balance'],'650');self.assertFalse(x['payment_authorized'])
    def test_settlement_exceptions(self):
        d=self.settlement();d['receipts'][0].update(accepted=70,rejected=5);d['adjustments'][0]['confirmed']=False
        x=self.run_stage('settlement',d);self.assertIsNone(x['items'][0]['reconciled_balance']);self.assertTrue({'quality_exception','invoice_acceptance_difference','adjustment_unconfirmed_or_currency_mismatch'}<=self.codes(x))
    def test_duplicate_business_document_and_order_link(self):
        for kind in ['invoices','receipts']:
            d=self.settlement();d[kind].append({**d[kind][0],'id':'new'})
            with self.assertRaises(ValidationError):ProcurementInput(**d)
        d=self.settlement();d['invoices'][0]['order_id']='wrong'
        with self.assertRaises(ValidationError):ProcurementInput(**d)
    def test_empty_and_stage_hash(self):
        d=dict(case_id='P',as_of='2026-11-01T00:00:00Z')
        for stage in STAGES:
            x=self.run_stage(stage,d);self.assertEqual(x['status'],'needs_input');self.assertFalse(x['executed_external_action'])
        d=self.data();h=self.run_stage('comparison',d)['input_hash'];d['offers'][0]['unit_price']=20;self.assertNotEqual(h,self.run_stage('comparison',d)['input_hash'])

class DispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_catalog_permissions_and_all_stages(self):
        from core.llm.tools import foreign_trade_tool as adapter
        from core.capabilities.catalog.loader import _load_builtin_skill_metadata
        from core.foreign_trade.tool_names import TRADE_TOOL_NAMES
        ids={m.id for m in _load_builtin_skill_metadata()};gates=[];kit=[]
        adapter.register_foreign_trade_tools(kit,user_id='owner',chat_id='chat',install_id='fixture',require_skill=gates.append)
        call=next(t._func for t in kit if t.name=='trade_procurement_prepare');self.assertIn('trade_procurement_prepare',TRADE_TOOL_NAMES)
        with patch.object(adapter,'_assert_available'):
            for stage,slug in STAGES.items():
                result=json.loads((await call(stage,ProcurementTests().data())).content[0].text)
                self.assertTrue(result['ok'],result);self.assertEqual(gates[-1],slug);self.assertIn(slug,ids)
        with patch.object(adapter,'_assert_available',side_effect=PermissionError('denied')):
            self.assertEqual(json.loads((await call('requirements',{})).content[0].text)['status'],403)
        def deny(slug):raise PermissionError('disabled')
        kit=[];adapter.register_foreign_trade_tools(kit,user_id='owner',chat_id='chat',install_id='fixture',require_skill=deny)
        call=next(t._func for t in kit if t.name=='trade_procurement_prepare')
        with patch.object(adapter,'_assert_available'):
            self.assertEqual(json.loads((await call('requirements',ProcurementTests().data())).content[0].text)['status'],403)

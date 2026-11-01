import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from pydantic import ValidationError
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/backend'))
from core.foreign_trade.retrospective import RetrospectiveInput, STAGES, review

class ReviewTests(unittest.TestCase):
    def request(self, **changes):
        data=dict(as_of='2026-03-01T00:00:00Z',sources=[dict(id='s',reference='CRM export v1 / actual correspondence',text='actual record; planned quote; customer budget frozen; action completed')],deals=[dict(id='a',channel='search')])
        data.update(changes)
        return RetrospectiveInput(**data)
    def evidence(self):return [dict(source_id='s',excerpt='actual record')]
    def event(self,id,at,stage='lead',deal_id='a',**changes):
        data=dict(id=id,deal_id=deal_id,at=at,kind='actual',stage=stage,description='actual record',evidence=self.evidence())
        data.update(changes);return data
    def test_timeline_sort_plans_and_version_matching(self):
        req=self.request(events=[self.event('actual','2026-01-03T00:00:00Z','quote',version='v1'),self.event('plan','2026-01-01T00:00:00Z','quote',kind='planned',version='v1'),self.event('future','2026-04-01T00:00:00Z','sample')])
        result=review(req,'deal-timeline')
        self.assertEqual(result['timeline'][0]['id'],'plan')
        self.assertEqual(result['timeline'][-1]['temporal_state'],'future')
        self.assertEqual(result['plan_comparisons'][0]['delay_hours'],48)
        self.assertEqual(result['timeline'][0]['evidence'][0]['reference'],'CRM export v1 / actual correspondence')
        req=self.request(events=[self.event('p','2026-01-01T00:00:00Z','quote',kind='planned',version='v1'),self.event('a','2026-01-03T00:00:00Z','quote',version='v2')])
        self.assertIsNone(review(req,'deal-timeline')['plan_comparisons'][0]['actual_id'])
    def test_dedup_preserves_review_candidates(self):
        req=self.request(events=[self.event('one','2026-01-01T00:00:00Z'),self.event('two','2026-01-01T00:00:00Z')])
        result=review(req,'deal-timeline')
        self.assertEqual(len(result['timeline']),1);self.assertEqual(result['duplicate_candidates'],['two'])
    def funnel(self):
        events=[self.event('a1','2026-01-01T00:00:00Z'),self.event('a2','2026-01-11T00:00:00Z','quote'),self.event('a3','2026-01-12T00:00:00Z','quote'),self.event('a4','2026-01-02T00:00:00Z','quote',kind='planned'),self.event('b1','2026-01-02T00:00:00Z',deal_id='b'),self.event('b2','2026-02-05T00:00:00Z','quote',deal_id='b'),self.event('c1','2026-02-20T00:00:00Z',deal_id='c'),self.event('c2','2026-02-21T00:00:00Z','quote',deal_id='c'),self.event('d1','2026-03-01T00:00:00Z',deal_id='d'),self.event('d2','2026-04-01T00:00:00Z','quote',deal_id='d')]
        return self.request(scope='period',period_start='2026-01-01T00:00:00Z',period_end='2026-03-01T00:00:00Z',observation_days=30,stage_order=['lead','quote'],deals=[dict(id=i,channel='search' if i in 'ab' else 'fair') for i in 'abcd'],events=events)
    def test_mature_denominator_distinct_activity_and_fixed_window(self):
        result=review(self.funnel(),'funnel-analysis');c=result['conversions'][0]
        self.assertEqual((c['cohort_count'],c['denominator'],c['numerator'],c['pending_observation']),(3,2,1,1))
        self.assertEqual(c['rate_pct'],'50.00');self.assertEqual(c['median_days'],10)
        self.assertEqual(result['activity'],dict(lead=3,quote=3))
        self.assertIsNone(result['by_channel']['fair']['conversions'][0]['rate_pct'])
        self.assertEqual(result['outcome_counts']['lost'],0)
    def test_skips_single_and_requires_period(self):
        self.assertEqual(review(self.request(),'funnel-analysis')['status'],'skipped_single_deal')
        self.assertEqual(review(self.request(scope='period'),'funnel-analysis')['status'],'needs_scope')
    def test_reverse_stage_flagged_no_fake_conversion(self):
        result=review(self.request(scope='period',period_start='2026-01-01T00:00:00Z',period_end='2026-02-01T00:00:00Z',stage_order=['lead','quote'],events=[self.event('q','2026-01-01T00:00:00Z','quote'),self.event('l','2026-01-02T00:00:00Z')]),'funnel-analysis')
        self.assertEqual(result['conversions'][0]['out_of_order_ids'],['a']);self.assertEqual(result['conversions'][0]['numerator'],0)
    def test_schema_rejects_invented_evidence_ids_and_naive_time(self):
        for changes in [dict(as_of='2026-03-01'),dict(as_of='2026-03-01T00:00:00'),dict(observation_days=True),dict(stage_order=['lead','lead']),dict(deals=[dict(id='a',outcome='lost')]),dict(period_start='2026-04-01T00:00:00Z',period_end='2026-04-02T00:00:00Z'),dict(events=[self.event('x','2026-01-01T00:00:00Z',deal_id='missing')]),dict(events=[self.event('x','2026-01-01T00:00:00Z',evidence=[dict(source_id='s',excerpt='invented')])]),dict(events=[self.event('x','2026-01-01T00:00:00Z'),self.event('x','2026-01-02T00:00:00Z')])]:
            with self.subTest(changes=changes),self.assertRaises(ValidationError):self.request(**changes)
    def test_reasons_keep_hypothesis_counterevidence_and_open(self):
        result=review(self.request(reasons=[dict(deal_id='a',category='price',explanation='maybe expensive',kind='hypothesis',counterevidence=self.evidence())]),'win-loss-analysis')
        item=result['reasons'][0];self.assertEqual(item['assessment'],'hypothesis_to_verify');self.assertEqual(item['outcome'],'unknown');self.assertTrue(item['counterevidence'])
        with self.assertRaises(ValidationError):self.request(reasons=[dict(deal_id='a',category='price',explanation='price',kind='customer_statement')])
    def test_actions_missing_fields_and_completion_boundaries(self):
        action=dict(id='a',problem='slow response',evidence=self.evidence())
        result=review(self.request(actions=[action]),'improvement-planning')['actions'][0]
        self.assertFalse(result['executable']);self.assertIn('owner',result['missing_fields']);self.assertIsNone(result['business_effect'])
        action.update(owner='sales',due_at='2026-02-01T00:00:00Z',deliverable='new quote template',acceptance='approved',metric='reply rate',baseline='10%',target='15%',check_at='2026-03-01T00:00:00Z')
        result=review(self.request(actions=[action]),'improvement-planning')['actions'][0]
        self.assertTrue(result['executable']);self.assertFalse(result['experiment_ready']);self.assertEqual(result['status'],'overdue')
        for changes in [dict(completed_at='2026-01-20T00:00:00Z'),dict(check_at='2026-01-01T00:00:00Z'),dict(completed_at='2026-04-01T00:00:00Z',completion_evidence=self.evidence())]:
            with self.subTest(changes=changes),self.assertRaises(ValidationError):self.request(actions=[dict(action,**changes)])
    def test_lessons_stay_candidates_not_validated(self):
        lesson=dict(id='one',title='Ask acceptance criteria',content='case only',deal_ids=['a','a'],evidence=self.evidence(),requested_tier='validated')
        result=review(self.request(lessons=[lesson,dict(lesson,id='two')]),'playbook-learning')
        self.assertEqual(result['lessons'][0]['tier'],'case');self.assertIn('multiple_distinct_deals',result['lessons'][0]['validation_missing_fields'])
        self.assertEqual(result['knowledge_base_check'],'not_performed');self.assertEqual(result['duplicate_title_candidates'],[['one','two']]);self.assertFalse(result['saved'])
    def test_all_outputs_are_drafts(self):
        for stage in STAGES:
            result=review(self.request(),stage)
            self.assertFalse(result['sent']);self.assertFalse(result['saved']);self.assertTrue(result['approval_required']);self.assertIsNone(result['metrics']['business_effect'])

class DispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_skill_catalog_guard_and_dispatch(self):
        from core.llm.tools import foreign_trade_tool as adapter
        from core.capabilities.catalog.loader import _load_builtin_skill_metadata
        ids={m.id for m in _load_builtin_skill_metadata()};toolkit=[];required=[]
        adapter.register_foreign_trade_tools(toolkit,user_id='fixture',chat_id=None,install_id='fixture',require_skill=required.append)
        call=next(t._func for t in toolkit if t.name=='trade_buyer_research')
        with patch.object(adapter,'_assert_available'):
            for stage,slug in STAGES.items():
                result=json.loads((await call(stage,dict(as_of='2026-03-01T00:00:00Z'))).content[0].text)
                self.assertTrue(result['ok'],result);self.assertEqual(required[-1],slug);self.assertIn(slug,ids)
        def deny(slug):raise PermissionError('skill not enabled')
        toolkit=[];adapter.register_foreign_trade_tools(toolkit,user_id='fixture',chat_id=None,install_id='fixture',require_skill=deny)
        call=next(t._func for t in toolkit if t.name=='trade_buyer_research')
        with patch.object(adapter,'_assert_available'):
            result=json.loads((await call('deal-timeline',dict(as_of='2026-03-01T00:00:00Z'))).content[0].text)
            self.assertFalse(result['ok'])

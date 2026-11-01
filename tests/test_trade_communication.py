import sys
import json
from unittest.mock import patch
import unittest
from pathlib import Path
from pydantic import ValidationError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/backend'))
from core.foreign_trade.communication import CommunicationInput, communicate

class CommunicationTests(unittest.TestCase):
    def request(self, **changes):
        data=dict(buyer_id='buyer', sources=[dict(id='s',reference='seller catalog v1',text='MOQ 500 units; delivery 30 days')],claims=[dict(field='quantity',source_id='s',excerpt='MOQ 500 units')],questions=['quantity','price'])
        data.update(changes)
        return CommunicationInput(**data)
    def test_missing_requirements_and_no_invented_answer(self):
        r=communicate(self.request(),'clarify')
        self.assertNotIn('quantity',r['missing_fields'])
        self.assertIn('product',r['missing_fields'])
        answers=communicate(self.request(),'grounded-reply')['answers']
        self.assertEqual(answers[0]['draft'],'MOQ 500 units')
        self.assertEqual(answers[1]['status'],'needs_confirmation')
    def test_fabricated_quote_rejected(self):
        with self.assertRaises(ValidationError):self.request(claims=[dict(field='price',source_id='s',excerpt='USD 1')])
    def test_conflicting_sources_not_cherry_picked(self):
        req=self.request(claims=[dict(field='quantity',source_id='s',excerpt='MOQ 500 units'),dict(field='quantity',source_id='s',excerpt='delivery 30 days')])
        self.assertEqual(communicate(req,'grounded-reply')['answers'][0]['status'],'conflicting_sources')
    def test_opt_out_stops_every_branch(self):
        for action in ['clarify','grounded-reply','communication-summary']:
            result=communicate(self.request(do_not_contact=True),action)
            self.assertEqual(result['status'],'stopped')
            self.assertFalse(result['sent'])
            self.assertNotIn('answers',result)
    def test_summary_keeps_original_reference(self):
        result=communicate(self.request(),'communication-summary')
        self.assertEqual(result['summary'][0]['reference'],'seller catalog v1')
        self.assertIsNone(result['metrics']['accuracy'])
        self.assertFalse(result['saved'])

class CommunicationDispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_skill_gate_and_catalog(self):
        from core.llm.tools import foreign_trade_tool as adapter
        from core.foreign_trade.communication import STAGES
        from core.capabilities.catalog.loader import _load_builtin_skill_metadata
        ids={m.id for m in _load_builtin_skill_metadata()}
        toolkit=[];required=[]
        adapter.register_foreign_trade_tools(toolkit,user_id='fixture',chat_id=None,install_id='fixture',require_skill=required.append)
        call=next(t._func for t in toolkit if t.name=='trade_buyer_research')
        with patch.object(adapter,'_assert_available'):
            for stage,slug in STAGES.items():
                result=json.loads((await call(stage,dict(buyer_id='fixture'))).content[0].text)
                self.assertTrue(result['ok']);self.assertEqual(required[-1],slug)
                self.assertIn(slug,ids)

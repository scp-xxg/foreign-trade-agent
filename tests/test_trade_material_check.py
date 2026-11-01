import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/backend'))
from core.foreign_trade.material_check import prepare
class MaterialCheckTests(unittest.TestCase):
    def test_sensitive_real_offsets(self):
        r=prepare('sensitive',{'fields':[{'id':'body','text':'😀 CE certified at best price'}]})
        self.assertEqual(r['document_type'],'trade_material_check')
        h=next(h for h in r['sensitive']['hits'] if h['rule_id']=='S401')
        self.assertEqual(r['fields'][0]['text'][slice(*h['span'])],h['match'])
        self.assertFalse(r['release_authorized'])
    def test_attachment_text_and_missing_ocr(self):
        r=prepare('sensitive',{},[('f','spec.txt',dict(text='FDA approved lamp',warnings=[])),('i','photo.png',dict(text='',warnings=['OCR unavailable']))])
        self.assertEqual(r['fields'][0]['id'],'attachment:f');self.assertTrue(r['notices'])
        self.assertTrue(any(h['rule_id']=='S402' for h in r['sensitive']['hits']))
        r=prepare('sensitive',{},[('i','photo.png',dict(text='',warnings=[]))]);self.assertIsNone(r['sensitive'])
    def test_compliance_and_missing_scope(self):
        r=prepare('compliance',dict(case_id='C',as_of='2026-11-01T00:00:00Z',product=dict(id='p',revision='1'),stage='listing',fields=[dict(id='b',text='Bottle')]))
        self.assertEqual(r['compliance']['status'],'needs_review');self.assertIn('missing_target_market',r['compliance']['coverage_gaps'])
    def test_unread_attachment_keeps_compliance_incomplete(self):
        r=prepare('compliance',dict(case_id='C',as_of='2026-11-01T00:00:00Z',product=dict(id='p',revision='1'),stage='listing'), [('i','image.png',dict(text='',warnings=[]))])
        self.assertEqual(r['compliance']['status'],'needs_review')
        self.assertTrue(any('image.png' in gap for gap in r['compliance']['coverage_gaps']))
    def test_duplicate_field_and_bad_action(self):
        with self.assertRaises(ValueError):prepare('sensitive',dict(fields=[dict(id='x',text='a'),dict(id='x',text='b')]))
        with self.assertRaises(ValueError):prepare('fake',{})
class DispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_permissions_skill_gates_and_attachments(self):
        from core.llm.tools import foreign_trade_tool as adapter
        from core.foreign_trade.tool_names import TRADE_TOOL_NAMES
        kit=[];gates=[]
        adapter.register_foreign_trade_tools(kit,user_id='owner',chat_id='chat',install_id='fixture',require_skill=gates.append)
        call=next(t._func for t in kit if t.name=='trade_material_check');self.assertIn('trade_material_check',TRADE_TOOL_NAMES)
        with patch.object(adapter,'_assert_available'),patch.object(adapter,'SessionLocal'),patch.object(adapter,'_attached_file_bytes',return_value=('a.txt',b'CE certified lamp')) as read:
            r=json.loads((await call('sensitive',{},['f'])).content[0].text)
            self.assertTrue(r['ok'],r);self.assertEqual(gates,['trade-sensitive-word-check'])
            self.assertEqual(read.call_args.kwargs,dict(user_id='owner',chat_id='chat',file_id='f'))
        with patch.object(adapter,'_assert_available',side_effect=PermissionError('denied')):
            self.assertEqual(json.loads((await call('sensitive',{})).content[0].text)['status'],403)
        with patch.object(adapter,'_assert_available'),patch.object(adapter,'SessionLocal'),patch.object(adapter,'_attached_file_bytes',side_effect=adapter.ContentPackError(404,'missing')):
            self.assertEqual(json.loads((await call('sensitive',{},['foreign'])).content[0].text)['status'],404)

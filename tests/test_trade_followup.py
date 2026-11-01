import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock
from datetime import datetime
from pydantic import ValidationError
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/backend'))
from core.foreign_trade.followup import CadenceInput, ReplyInput, plan_cadence, triage_reply

class FollowupTests(unittest.IsolatedAsyncioTestCase):
    def data(self, **changes):
        data=dict(lead=dict(buyer_id='fixture',dossier_version='1',review_version='1',review_decision='suitable',review_reason='Evidence reviewed',has_channel=True,
             assessments=[dict(dimension=d,result='match',excerpt='Evidence',source_url='https://example.com',retrieved_at='2026-10-01T00:00:00Z') for d in ['product','buyer_type','market','supply']]),
             contact=dict(channel='sales@example.com',channel_type='email',source_url='https://example.com/contact',retrieved_at='2026-10-01T00:00:00Z',purpose_confirmed=True),
             timezone='Europe/Berlin',as_of='2026-10-02T12:00:00Z',initial_sent_at='2026-10-01T12:00:00Z')
        data.update(changes);return data
    def reply(self, **changes):
        data=dict(buyer_id='fixture',reply_text='Please send a quote for 500 units.',source_reference='email-123',received_at='2026-10-02T09:00:00Z')
        data.update(changes);return data

    def test_weekends_timezone_and_dst(self):
        r=plan_cadence(CadenceInput(**self.data()))
        self.assertEqual(r['status'],'planned');self.assertEqual(len(r['steps']),3)
        self.assertEqual(r['steps'][0]['due_at'],'2026-10-05T09:30:00+02:00')
        self.assertEqual(r['scheduling_status'],'not_scheduled');self.assertEqual(r['sending_status'],'not_sent')
        r=plan_cadence(CadenceInput(**self.data(initial_sent_at='2026-10-23T12:00:00Z',as_of='2026-10-24T12:00:00Z')))
        self.assertEqual(r['steps'][0]['due_at'],'2026-10-26T09:30:00+01:00')

    def test_history_cap_and_overdue_no_send(self):
        r=plan_cadence(CadenceInput(**self.data(as_of='2026-10-20T12:00:00Z',followup_sent_at=['2026-10-05T07:30:00Z'])))
        self.assertEqual([s['step'] for s in r['steps']],[2,3]);self.assertEqual(r['steps'][0]['status'],'overdue_review')
        self.assertTrue(all(s['approval_required'] for s in r['steps']))
        self.assertEqual(plan_cadence(CadenceInput(**self.data(max_followups=0)))['status'],'exhausted')
        self.assertEqual(plan_cadence(CadenceInput(**self.data(initial_sent_at=None)))['status'],'awaiting_initial_send')

    def test_stop_and_priority_gates(self):
        for key in ['do_not_contact','hard_excluded']:
            data=self.data();data['lead'][key]=True
            self.assertEqual(plan_cadence(CadenceInput(**data))['status'],'stopped')
        self.assertEqual(plan_cadence(CadenceInput(**self.data(bounced=True)))['steps'],[])
        data=self.data();data['lead']['assessments']=[]
        self.assertEqual(plan_cadence(CadenceInput(**data))['status'],'blocked_priority')
        data=self.data();data['contact']['purpose_confirmed']=False
        self.assertEqual(plan_cadence(CadenceInput(**data))['status'],'needs_channel_review')

    def test_reply_always_pauses_and_optout_overrides_label(self):
        r=triage_reply(ReplyInput(**self.reply()))
        self.assertEqual(r['suggested_intent'],'request_quote');self.assertEqual(r['intent'],'unknown');self.assertTrue(r['needs_review'])
        reply=self.reply(confirmed_intent='request_quote',evidence_excerpt='send a quote')
        r=triage_reply(ReplyInput(**reply));self.assertEqual(r['intent'],'request_quote');self.assertFalse(r['needs_review'])
        r=plan_cadence(CadenceInput(**self.data(reply=reply)))
        self.assertEqual(r['status'],'paused_reply');self.assertEqual(r['steps'],[])
        reply=self.reply(reply_text='Unsubscribe. Please quote nothing.',confirmed_intent='request_quote',evidence_excerpt='quote')
        r=plan_cadence(CadenceInput(**self.data(reply=reply)))
        self.assertTrue(r['do_not_contact']);self.assertEqual(r['status'],'stopped');self.assertTrue(r['reply']['needs_review'])
        r=plan_cadence(CadenceInput(**self.data(reply=self.reply(reply_text='不感兴趣',confirmed_intent='not_interested',evidence_excerpt='不感兴趣'))))
        self.assertEqual(r['status'],'stopped')

    def test_unknown_languages_multiple_intents_no_fake_confidence(self):
        for text in ['Bonjour, merci.', 'Please quote and send a sample.', 'I am not interested.']:
            r=triage_reply(ReplyInput(**self.reply(reply_text=text)))
            self.assertEqual(r['intent'],'unknown');self.assertTrue(r['pause_sequence']);self.assertIsNone(r['confidence'])
        for intent,text in [('wrong_contact','Wrong person'),('out_of_office','Out of office'),('request_sample','send a sample'),('interested','interested')]:
            r=triage_reply(ReplyInput(**self.reply(reply_text=text,confirmed_intent=intent,evidence_excerpt=text)))
            self.assertEqual(r['intent'],intent);self.assertTrue(r['pause_sequence'])

    def test_validation_identity_history_and_evidence(self):
        for changes in [dict(timezone='bad'),dict(as_of='2026-10-02T12:00:00'),dict(initial_sent_at='2026-10-03T12:00:00Z'),
                        dict(followup_sent_at=['2026-10-01T12:00:00Z']),dict(max_followups=True),
                        dict(reply=self.reply(buyer_id='other')),dict(reply=self.reply(received_at='2026-10-03T00:00:00Z'))]:
            with self.assertRaises(ValidationError):CadenceInput(**self.data(**changes))
        with self.assertRaises(ValidationError):ReplyInput(**self.reply(confirmed_intent='request_quote',evidence_excerpt='invented'))
        with self.assertRaises(ValidationError):ReplyInput(**self.reply(reply_text=' '))

    def test_api_auth_and_catalog(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.routes.v1 import foreign_trade_buyers as api
        from core.auth import backend as auth
        app=FastAPI();app.include_router(api.router);client=TestClient(app)
        with patch.object(auth,'_auth_mode',return_value='session'),patch.object(auth,'_resolve_host_user',new=AsyncMock(return_value=None)),patch.object(auth,'_resolve_session_user',new=AsyncMock(return_value=None)):
            for action in ['cadence','reply-triage']:self.assertEqual(client.post('/v1/foreign-trade/buyer-search/'+action,json={}).status_code,401)
        app.dependency_overrides[api.get_current_user]=lambda:object()
        for action,req in [('cadence',self.data()),('reply-triage',self.reply())]:
            self.assertEqual(client.post('/v1/foreign-trade/buyer-search/'+action,json=req).status_code,200)
        self.assertEqual(client.post('/v1/foreign-trade/buyer-search/cadence',json=self.data(timezone='bad')).status_code,422)
        from core.capabilities.catalog.loader import _load_builtin_skill_metadata
        ids={m.id for m in _load_builtin_skill_metadata()}
        for slug in ['trade-followup-cadence','trade-reply-triage']:
            self.assertIn(slug,ids)
            root=Path(__file__).resolve().parents[1]
            self.assertEqual((root/'src/backend/extensions/skills/default'/slug/'SKILL.md').read_text(),(root/'extensions/foreign_trade/plugin/skills'/slug/'SKILL.md').read_text())

    async def test_chat_dispatch_and_skill_gate(self):
        from core.llm.tools import foreign_trade_tool as adapter
        from core.llm.foreign_trade_plugin import TradeSkillRequired
        tools=[];required=[]
        adapter.register_foreign_trade_tools(tools,user_id='fixture',chat_id=None,install_id='fixture',require_skill=required.append)
        call=next(t._func for t in tools if t.name=='trade_buyer_research')
        with patch.object(adapter,'_assert_available'):
            for action,data in [('cadence',self.data()),('reply-triage',self.reply())]:
                response=json.loads((await call(action,data)).content[0].text);self.assertTrue(response['ok'])
            self.assertEqual(required,['trade-followup-cadence','trade-reply-triage'])
            self.assertEqual(json.loads((await call('cadence',self.data(timezone='bad'))).content[0].text)['status'],422)
        def blocked(name):raise TradeSkillRequired('read first')
        tools=[];adapter.register_foreign_trade_tools(tools,user_id='fixture',chat_id=None,install_id='fixture',require_skill=blocked)
        with patch.object(adapter,'_assert_available'):
            call=next(t._func for t in tools if t.name=='trade_buyer_research')
            self.assertEqual(json.loads((await call('cadence',self.data())).content[0].text)['status'],409)

if __name__=='__main__':unittest.main()

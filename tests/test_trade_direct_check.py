import sys,unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/backend'))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.routes.v1 import foreign_trade_material_check as route
from core.auth.backend import get_current_user,UserContext
class DirectTests(unittest.TestCase):
    def setUp(self):
        app=FastAPI();app.include_router(route.router)
        self.app=app;self.client=TestClient(app)
        app.dependency_overrides[get_current_user]=lambda:UserContext(user_id='u',user_center_id='c',username='test')
    def test_text_and_local_file(self):
        with patch.object(route,'SessionLocal'):
            r=self.client.post('/material-check',data={'text':'best price'},files=[('files',('spec.txt',b'CE certified lamp','text/plain'))])
        self.assertEqual(r.status_code,200,r.text)
        data=r.json()['data'];self.assertEqual(len(data['fields']),2)
        self.assertTrue({'S301','S401'}<={x['rule_id'] for x in data['sensitive']['hits']})
    def test_empty_and_duplicate_refs(self):
        self.assertEqual(self.client.post('/material-check',data={'text':''}).status_code,422)
        self.assertEqual(self.client.post('/material-check',data={'file_ids':'["a","a"]'}).status_code,422)
    def test_imported_owner_is_enforced(self):
        with patch.object(route,'SessionLocal') as session:
            query=session.return_value.__enter__.return_value.query.return_value
            query.filter_by.return_value.first.return_value=None
            r=self.client.post('/material-check',data={'file_ids':'["foreign"]'})
            self.assertEqual(r.status_code,404)
            self.assertEqual(query.filter_by.call_args.kwargs,{'artifact_id':'foreign','user_id':'u'})
    def test_file_limit(self):
        r=self.client.post('/material-check',files=[('files',('x.txt',b'x','text/plain'))]*11)
        self.assertEqual(r.status_code,422)
    def test_auth_required(self):
        from fastapi import HTTPException
        def deny():raise HTTPException(401,'not signed in')
        self.app.dependency_overrides[get_current_user]=deny
        self.assertEqual(self.client.post('/material-check',data={'text':'best price'}).status_code,401)

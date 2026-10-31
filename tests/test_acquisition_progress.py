"""Refresh recovery must preserve actor isolation and reject lost updates."""
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from core.db.engine import Base
from core.foreign_trade.acquisition_progress import SaveProgress,read_progress,save_progress

@pytest.fixture
def db():
    engine=create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as session: yield session
    engine.dispose()

def test_owner_checkpoint_survives_new_session_and_conflicting_tab(db):
    first=save_progress(db,'alice',SaveProgress(revision=0,payload={'product':'DESK-001','confirmed':False,'dossiers':{}}))
    assert first['revision']==1
    with Session(db.bind) as restored:
        assert read_progress(restored,'alice')['payload']['product']=='DESK-001'
        assert read_progress(restored,'bob')['payload'] is None
        with pytest.raises(HTTPException) as e:
            save_progress(restored,'bob',SaveProgress(revision=1,payload={'product':'changed'}))
        assert e.value.status_code==409
        save_progress(restored,'alice',SaveProgress(revision=1,payload={'product':'second tab'}))
    with pytest.raises(HTTPException) as e:
        save_progress(db,'alice',SaveProgress(revision=1,payload={'product':'stale tab'}))
    assert e.value.status_code==409
    db.expire_all()
    assert read_progress(db,'alice')['payload']['product']=='second tab'

def test_checkpoint_does_not_accept_identity_or_unbounded_content():
    for value in [{'owner_user_id':'bob'}, {'contacts':{'x':None}}, {'product':'x'*100001}, {'run':{'candidates':[{'id':'x','name':'x','discovery_url':'http://127.0.0.1'}]}}]:
        with pytest.raises(ValidationError):SaveProgress(revision=0,payload=value)

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from core.db.engine import Base
from core.db.models import UserAgent,UserShadow
from foreign_trade.core_roles import install_core_roles

def test_three_roles_are_owned_idempotent_and_preserve_human_edits(monkeypatch):
    monkeypatch.setattr('core.capabilities.agents.base.desktop_store',lambda:False)
    monkeypatch.setattr('core.capabilities.agents.base.ensure_ontology_build_valid',lambda *a,**k:None)
    engine=create_engine('sqlite://');Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([UserShadow(user_id=u,username=u,extra_data={'can_add_agent':True}) for u in ['a','b']]);db.commit()
        first=install_core_roles(db,'a','plugin:local:trade-a')
        assert {a['role'] for a in first}=={'sales','procurement','operations'}
        row=db.query(UserAgent).filter_by(agent_id=first[0]['agent_id']).one()
        row.system_prompt='Human-reviewed role';db.commit()
        second=install_core_roles(db,'a','plugin:local:trade-a')
        assert [x['agent_id'] for x in first]==[x['agent_id'] for x in second]
        assert row.system_prompt=='Human-reviewed role'
        other=install_core_roles(db,'b','plugin:local:trade-b')
        assert not {x['agent_id'] for x in first}&{x['agent_id'] for x in other}
        assert db.query(UserAgent).count()==6
        for row in db.query(UserAgent).filter_by(user_id='b'):
            assert row.plugin_ids==['plugin:local:trade-b'] and row.kb_ids==[]
    engine.dispose()


def test_role_install_does_not_escalate_an_unprivileged_account():
    engine=create_engine('sqlite://');Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(UserShadow(user_id='member',username='member',extra_data={}));db.commit()
        result=install_core_roles(db,'member','plugin:local:owned')
        assert len(result)==3 and all(x['action']=='permission_required' for x in result)
        assert db.query(UserAgent).count()==0
        assert db.query(UserShadow).one().extra_data=={}
    engine.dispose()

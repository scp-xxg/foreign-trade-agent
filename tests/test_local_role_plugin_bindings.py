"""Cold custom roles must not depend on prior activation in the parent chat."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from core.db.engine import Base
from core.llm.factory.selection.capabilities import _expand_plugin_bindings

@pytest.fixture
def local_catalog(monkeypatch):
    engine=create_engine('sqlite://');Base.metadata.create_all(engine)
    monkeypatch.setattr('core.db.engine.SessionLocal',sessionmaker(bind=engine))
    monkeypatch.setattr('core.harness.registry.run_capabilities.has_run_capabilities',lambda:True)
    monkeypatch.setattr('core.harness.registry.run_capabilities.cloud_binding_ids',lambda *a,**k:([],[]))
    rows=[{'install_id':'plugin:local:trade-a','slug':'trade-a','enabled':True,'callable':True,'skills':['inquiry-a'],'mcp':['quote-a']},
          {'install_id':'plugin:local:other-a','slug':'other-a','enabled':True,'callable':True,'skills':['other'],'mcp':['other-mcp']}]
    monkeypatch.setattr('core.harness.registry.device_catalog.plugin_entries',lambda uid:rows if uid=='a' else [])
    yield rows
    engine.dispose()

def test_cold_local_role_expands_without_legacy_rows_or_cloud_account(local_catalog):
    assert _expand_plugin_bindings(['plugin:local:trade-a'],user_id='a')==(['inquiry-a'],['quote-a'])
    assert _expand_plugin_bindings(['plugin:local:trade-a'],user_id='b')==([],[])
    assert _expand_plugin_bindings([],user_id='a')==([],[])
    assert _expand_plugin_bindings(['plugin:local:trade-a-extra'],user_id='a')==([],[])

@pytest.mark.parametrize('flag',['enabled','callable'])
def test_disabled_or_unready_plugin_does_not_gain_capabilities(local_catalog,flag):
    local_catalog[0][flag]=False
    assert _expand_plugin_bindings(['plugin:local:trade-a'],user_id='a')==([],[])

@pytest.mark.asyncio
@pytest.mark.parametrize('bound',[None,['plugin:local:trade-a']])
async def test_role_binding_is_eager_but_main_chat_is_not(monkeypatch,bound):
    from types import SimpleNamespace as NS
    from features.desktop.run_capabilities import preparation
    from core.llm.factory.models import RequiredCapabilities,StickyCapabilities
    monkeypatch.setattr(preparation,'capabilities_enabled',lambda:True)
    seen={}
    def resolve(**kwargs):
        seen.update(kwargs)
        raise RuntimeError('stop before runtime materialization')
    monkeypatch.setattr('features.desktop.plugin_resolution.resolve_desktop_progressive_plugins',resolve)
    req=NS(project_environment=None,disable_tools=False,current_user_id='a',enabled_skill_ids=[],enabled_mcp_ids=[],user_agent=NS(plugin_ids=bound) if bound is not None else None,invoked_skill_ids=[],invoked_mcp_ids=[])
    with pytest.raises(RuntimeError,match='stop before'):
        await preparation.device_preparation(req,_api_scope=None,_capability_run_key='test',_caps_skill_ids=[],_elapsed=lambda:0,_eval_scope=None,_log=NS(info=lambda *a:None),_mode_plugin_ids=[],_note_unavailable=lambda *a:None,required=RequiredCapabilities(),sticky=StickyCapabilities(),enabled_mcp_keys=[])
    assert {x for x in seen['activated_ids'] if x}==set(bound or [])

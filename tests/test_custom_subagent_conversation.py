from types import SimpleNamespace
from core.llm.subagents import execution

def test_custom_child_retains_owner_conversation_and_narrow_role_bindings(monkeypatch):
    role=SimpleNamespace(mcp_server_ids=[],skill_ids=[],kb_ids=[],plugin_ids=['only-bound-plugin'],system_prompt='role',model_provider_id=None,max_iters=5,temperature=0,max_tokens=1000,timeout=30)
    async def in_session(fn):return fn(None)
    monkeypatch.setattr(execution,'run_in_session',in_session)
    monkeypatch.setattr('core.capabilities.agents.edition.UserAgentService.get_raw_by_id',lambda self,agent_id,user_id: role if user_id=='owner' else None)
    captured={}
    async def factory(**kwargs):
        captured.update(kwargs)
        raise RuntimeError('test stops before any model/network call')
    monkeypatch.setattr('core.llm.factory.create_agent_executor',factory)
    result=execution._run_subagent_in_thread('custom-role','role','task','','owner',parent_runtime={'chat_id':'owned-chat','sandbox_session_id':'owned-chat'})
    assert result[0] is False
    assert captured['chat_id']=='owned-chat'
    assert captured['current_user_id']=='owner' and captured['isolated'] is True
    assert captured['user_agent'].plugin_ids==['only-bound-plugin']

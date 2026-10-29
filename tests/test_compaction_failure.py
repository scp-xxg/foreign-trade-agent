"""The upstream checkpoint compressor preserves completed foreign-trade work."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest
from agentscope.agent import Agent, ContextConfig
from agentscope.message import Msg, TextBlock, ToolCallBlock, ToolResultBlock

from core.config import settings as settings_module
from core.harness.registry import compaction as compaction_port
from core.llm.context.compacting_agent import CompactingAgent
from core.llm.context.safety import ContextBudgetExceeded, enforce_context_budget, request_admission_scope
from core.llm.runtime.state import AgentRuntimeState
from core.models.admission import check_request_admission


def _agent():
    agent = object.__new__(CompactingAgent)
    agent._jx_observation = None
    agent._jx_compacted_cursor = None
    agent._jx_trigger_ratio = 0.8
    agent._jx_compaction_system_prompt = ""
    agent._jx_compaction_tool_schemas = []
    agent.model = SimpleNamespace(context_size=1000, model="offline-test")
    agent.offloader = None
    agent.context_config = ContextConfig()
    agent.state = AgentRuntimeState(
        chat_id="trade-chat", session_id="trade-session", summary="previous validated summary",
        context=[
            Msg(name="user", role="user", content=[TextBlock(text="保存询盘后计算报价")]),
            Msg(name="assistant", role="assistant", content=[
                ToolCallBlock(id="saved-inquiry", name="trade_save_inquiry", input='{"title":"test"}'),
                ToolResultBlock(id="saved-inquiry", name="trade_save_inquiry",
                                output='{"ok":true,"inquiry_id":"inq-saved","revision":1}'),
            ]),
        ],
    )
    async def threshold():
        return 800, 900
    agent._should_compact = threshold
    return agent


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, ValueError, TimeoutError, RuntimeError])
async def test_failed_summary_preserves_original_task_and_completed_receipt(monkeypatch, failure):
    monkeypatch.setattr(settings_module, "settings", replace(
        settings_module.settings, compaction=replace(settings_module.settings.compaction, enabled=True)))
    seen = []
    async def compact(chat_id, history, **kwargs):
        seen.append(deepcopy(history))
        if failure:
            raise failure("synthetic summary failure")
        return None
    async def forbidden_fallback(*args, **kwargs):
        pytest.fail("A failed checkpoint must not invoke the framework placeholder compressor")
    monkeypatch.setattr(compaction_port, "run_compaction", compact)
    monkeypatch.setattr(Agent, "compress_context", forbidden_fallback)
    agent = _agent()
    original = deepcopy(agent.state.model_dump(mode="json"))
    await agent.compress_context()
    assert seen and "inq-saved" in str(seen)
    assert agent.state.model_dump(mode="json") == original
    assert agent._jx_compacted_cursor is None


@pytest.mark.asyncio
async def test_budget_stop_preserves_receipt_and_blocks_subsequent_provider_calls():
    agent = _agent()
    original = deepcopy(agent.state.model_dump(mode="json"))
    assembly = SimpleNamespace(over_budget=True, manifest={
        "used_tokens": 2000, "total_budget": 1000, "budget_details": {},
    })
    with request_admission_scope() as admission:
        with pytest.raises(ContextBudgetExceeded) as stopped:
            await enforce_context_budget(agent, assembly)
        assert admission.stopped is stopped.value
        assert "inq-saved" in str(stopped.value.context)
        assert stopped.value.summary == original["summary"]
        with pytest.raises(ContextBudgetExceeded) as second:
            check_request_admission()
        assert second.value is stopped.value
        with pytest.raises(ContextBudgetExceeded):
            await agent.compress_context()
    assert agent.state.model_dump(mode="json") == original

"""A failed summary must not erase a task or manufacture a completed answer."""
from copy import deepcopy
from types import SimpleNamespace

import pytest
from agentscope.agent import ContextConfig
from agentscope.message import Msg, TextBlock, ToolCallBlock, ToolResultBlock
from agentscope.model import StructuredResponse

from core.chat.context import resolve_user_facing_error
from core.llm.compacting_agent import CompactingAgent, msg_to_history_dict
from core.llm.compaction_errors import (
    COMPACTION_FAILURE_MESSAGE,
    ContextCompactionError,
    find_context_compaction_error,
)
from core.llm.providers._fallback import StructuredFallbackMixin
from core.services import compaction_service


@pytest.mark.parametrize("failure", [ValueError, TimeoutError, RuntimeError])
async def test_model_adapter_does_not_forge_a_summary(failure):
    original = failure("PRIVATE_UPSTREAM_JSON")

    class Provider:
        async def generate_structured_output(self, *args, **kwargs):
            raise original

    class Model(StructuredFallbackMixin, Provider):
        pass

    with pytest.raises(failure) as caught:
        await Model().generate_structured_output([], {})
    assert caught.value is original


async def test_successful_structured_output_is_unchanged():
    response = StructuredResponse(content={"task_overview": "real summary"})

    class Provider:
        async def generate_structured_output(self, *args, **kwargs):
            return response

    class Model(StructuredFallbackMixin, Provider):
        pass

    assert await Model().generate_structured_output([], {}) is response


def make_agent(monkeypatch, *, enabled, error=None):
    import core.config.settings as settings_mod

    monkeypatch.setattr(settings_mod, "settings", SimpleNamespace(
        compaction=SimpleNamespace(enabled=enabled)))
    calls = []
    agent = object.__new__(CompactingAgent)
    agent.name = "test_agent"
    agent.context_config = ContextConfig()
    agent._jx_observation = None
    agent._jx_compacted_cursor = None
    agent._jx_trigger_ratio = 0.8
    agent.offloader = None
    task = Msg(name="user", role="user", content=[TextBlock(text="继续已保存的任务")])
    receipt = Msg(name="assistant", role="assistant", content=[
        ToolCallBlock(id="call_saved", name="save_record", input='{"title":"demo"}'),
        ToolResultBlock(id="call_saved", name="save_record", output='{"ok":true,"id":"saved_1"}'),
    ])
    agent.state = SimpleNamespace(context=[task, receipt], summary="previous summary",
                                  chat_id="chat_test", session_id="session_test")

    async def count(*args, **kwargs):
        return 950

    async def generate(*args, **kwargs):
        calls.append("summarize")
        if error is not None:
            raise error
        return StructuredResponse(content={key: "validated summary" for key in (
            "task_overview", "current_state", "important_discoveries", "next_steps", "context_to_preserve")})

    agent.model = SimpleNamespace(context_size=1000, count_tokens=count,
                                  generate_structured_output=generate)

    async def prepare():
        return {"messages": agent.state.context, "tools": []}

    async def system():
        return "system"

    async def split(*args):
        return [agent.state.context[0]], [agent.state.context[1]]

    async def engine(*args):
        calls.append("engine")
        return None

    agent._prepare_model_input = prepare
    agent._get_system_prompt = system
    agent._split_context_for_compression = split
    monkeypatch.setattr(compaction_service, "run_mid_turn_compaction", engine)
    return agent, calls


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("failure", [ValueError, TimeoutError, RuntimeError])
async def test_real_framework_failure_preserves_task_and_committed_receipt(monkeypatch, caplog, enabled, failure):
    agent, calls = make_agent(monkeypatch, enabled=enabled,
                              error=failure("PRIVATE_UPSTREAM_JSON"))
    before = [msg_to_history_dict(m) for m in agent.state.context]
    with pytest.raises(ContextCompactionError) as caught:
        await agent.compress_context()
    assert str(caught.value) == COMPACTION_FAILURE_MESSAGE
    assert "PRIVATE_UPSTREAM_JSON" not in str(caught.value)
    assert "PRIVATE_UPSTREAM_JSON" not in caplog.text
    assert agent.state.summary == "previous summary"
    assert [msg_to_history_dict(m) for m in agent.state.context] == before
    assert agent._jx_compacted_cursor is None
    assert calls == (["engine", "summarize"] if enabled else ["summarize"])


@pytest.mark.parametrize("enabled", [False, True])
async def test_successful_framework_compression_keeps_normal_behavior(monkeypatch, enabled):
    agent, calls = make_agent(monkeypatch, enabled=enabled)
    original_receipt = msg_to_history_dict(agent.state.context[1])
    await agent.compress_context()
    assert "validated summary" in agent.state.summary
    assert [msg_to_history_dict(m) for m in agent.state.context] == [original_receipt]
    assert calls == (["engine", "summarize"] if enabled else ["summarize"])


async def test_failure_after_partial_framework_mutation_rolls_back(monkeypatch):
    agent, _ = make_agent(monkeypatch, enabled=True)
    before = deepcopy([msg_to_history_dict(m) for m in agent.state.context])

    async def broken_framework(self, cfg):
        self.state.summary = "uncommitted summary"
        self.state.context[0].content[0].text = "lost task"
        self.state.context.clear()
        raise ValueError("PRIVATE_UPSTREAM_JSON")

    monkeypatch.setattr("agentscope.agent.Agent.compress_context", broken_framework)
    with pytest.raises(ContextCompactionError):
        await agent.compress_context()
    assert agent.state.summary == "previous summary"
    assert [msg_to_history_dict(m) for m in agent.state.context] == before


@pytest.mark.parametrize("wrapper", ["direct", "cause", "group"])
def test_user_error_is_fixed_and_safe_through_wrappers(wrapper):
    error = ContextCompactionError()
    outer = error
    if wrapper == "cause":
        outer = RuntimeError("PRIVATE_UPSTREAM_JSON")
        outer.__cause__ = error
    elif wrapper == "group":
        outer = ExceptionGroup("PRIVATE_UPSTREAM_JSON", [ValueError("other"), error])
    assert find_context_compaction_error(outer) is error
    assert resolve_user_facing_error(outer) == COMPACTION_FAILURE_MESSAGE


def test_unrelated_exception_and_cycles_are_not_compaction_failures():
    error = ValueError("unrelated")
    error.__cause__ = error
    assert find_context_compaction_error(error) is None

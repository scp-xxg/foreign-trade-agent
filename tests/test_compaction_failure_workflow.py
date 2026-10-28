"""Real worker persistence: summary failure cannot erase a completed inquiry."""
from dataclasses import replace
import json

import pytest
from agentscope.message import UserMsg
from core.config import settings as settings_module
from core.db.models import ChatMessage, ChatRun, ForeignTradeInquiry
from core.harness.registry import compaction as compaction_port
from core.chat.compaction.budget_checkpoint import ContextBudgetJournal
from core.llm.context.compacting_agent import CompactingAgent
from core.llm.context.safety import ContextBudgetExceeded
from core.llm.runtime.state import AgentRuntimeState
from core.llm.tools.ontology_toolkit import OntologyFilteredToolkit
from tests.llm.test_context_safety import CaptureModel
from tests.orchestration.test_model_steps_pipeline import _run, _step
from tests.orchestration.test_model_steps_pipeline import run_env as run_env

RECEIPT = {"ok": True, "inquiry_id": "inq-saved-before-summary", "revision": 1}
PARTIAL = "询盘已保存，报价尚未完成。"


@pytest.fixture(autouse=True)
def chat_runtime_contracts(monkeypatch):
    """Compose the real chat ports without relying on another suite's conftest.

    Bind fresh event streams and restore every registry value after each test;
    the fake workflow still runs through the real compaction and worker gates.
    """
    from core.agent_runtime.host import stream_chat_workflow
    from core.harness.registry.chat_execution import chat_execution
    from core.chat.compaction import service
    from core.chat.compaction.budget_checkpoint import ContextStopCheckpoint
    from core.chat.projection.codec import chat_projection_codec
    from core.runs.events import store

    monkeypatch.setattr(chat_execution(), "stream", stream_chat_workflow)
    services = compaction_port.compaction_services()
    for name, value in {
        "run": service.run_compaction,
        "mid_turn": service.run_mid_turn_compaction,
        "token_limit": service.resolve_token_limit,
        "trigger_ratio": service.resolve_trigger_ratio,
        "checkpoint": ContextStopCheckpoint,
    }.items():
        monkeypatch.setattr(services, name, value)
    projection = chat_projection_codec()
    monkeypatch.setattr(store, "_LOCAL_STREAM", store.LocalRunEventStream(projection))
    monkeypatch.setattr(store, "_REDIS_STREAM", store.RedisRunEventStream(projection))


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["empty", "timeout"])
@pytest.mark.parametrize("swallowed", [False, True])
async def test_failed_compaction_preserves_saved_inquiry_and_pauses_run(run_env, monkeypatch, failure, swallowed):
    monkeypatch.setattr(settings_module, "settings", replace(
        settings_module.settings, compaction=replace(settings_module.settings.compaction, enabled=True)))
    monkeypatch.setattr(
        "core.chat.compaction.budget_checkpoint.ContextBudgetJournal",
        lambda *args: ContextBudgetJournal(run_env),
    )
    summary_calls = []
    async def compact(*args, **kwargs):
        summary_calls.append(True)
        if failure == "timeout":
            raise TimeoutError("synthetic summary timeout")
        return None
    monkeypatch.setattr(compaction_port, "run_compaction", compact)
    model = CaptureModel()
    agent = CompactingAgent(
        name="foreign-trade-probe", system_prompt="rules", model=model,
        toolkit=OntologyFilteredToolkit(), state=AgentRuntimeState(chat_id="chat-1"),
    )
    with run_env() as db:
        db.add(ForeignTradeInquiry(
            inquiry_id=RECEIPT["inquiry_id"], owner_user_id="user-1", revision=1,
            payload={"title": "Saved inquiry", "quote": None},
            created_at="2026-10-28T00:00:00+00:00", updated_at="2026-10-28T00:00:00+00:00",
        ))
        db.commit()

    async def workflow(**kwargs):
        yield _step({"type": "tool_call", "id": "saved-call", "name": "trade_save_inquiry", "input": "{}"})
        yield {"type": "model_step", "step": {
            "schema": "harness.steps.v1", "kind": "tool_result", "blocks": [{
                "type": "tool_result", "id": "saved-call", "name": "trade_save_inquiry",
                "output": json.dumps(RECEIPT), "state": "success",
            }],
        }}
        yield {"type": "tool_result", "tool_id": "saved-call", "tool_name": "trade_save_inquiry",
               "result": RECEIPT, "status": "success"}
        yield {"type": "ai_message", "delta": PARTIAL}
        try:
            await agent.reply(UserMsg(name="user", content="Retain completed work. " * 1000))
        except ContextBudgetExceeded:
            if not swallowed:
                raise
        # Even a provider wrapper that swallows the budget stop cannot mark this completed.
        yield {"type": "meta"}

    run = await _run(workflow, monkeypatch)
    with run_env() as db:
        stored = db.get(ChatRun, run.run_id)
        assert stored.status == "needs_attention"
        stop = stored.recovery_snapshot["context_budget_stop"]
        assert stop["assistant_content"] == PARTIAL
        assert json.loads(stop["model_steps"][-1]["blocks"][0]["output"]) == RECEIPT
        message = db.get(ChatMessage, run.message_id)
        assert message.content == PARTIAL
        assert json.loads(message.model_steps[-1]["blocks"][0]["output"]) == RECEIPT
        inquiry = db.get(ForeignTradeInquiry, RECEIPT["inquiry_id"])
        assert inquiry.revision == 1 and inquiry.payload["quote"] is None
    assert summary_calls and model.calls == []

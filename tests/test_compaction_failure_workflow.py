"""Compression failure must not turn partial work into a successful chat turn."""
# Modified by foreign-trade-agent contributors, 2026-10-21; see CHANGES_FOREIGN_TRADE.md.
from __future__ import annotations

import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "backend"))

from core.llm.compaction_errors import COMPACTION_FAILURE_MESSAGE, ContextCompactionError
from orchestration import workflow


PARTIAL = "已保存询盘，接下来准备报价。"
RECEIPT = {"ok": True, "inquiry_id": "inq-test", "revision": 1}
CALL_ID = "save-inquiry-1"
TOOL_NAME = "trade_save_inquiry"


def _failure(wrapped=False):
    error = ContextCompactionError()
    if not wrapped:
        return error
    wrapper = RuntimeError("internal recovery template must not reach the user")
    wrapper.__cause__ = error
    return ExceptionGroup("provider wrapper", [wrapper])


def _step(kind, blocks):
    return {"schema": "harness.steps.v1", "kind": kind, "blocks": blocks}


@pytest.fixture()
def fake_runtime(monkeypatch):
    """Stub model/DB discovery only; execute the real workflow dispatchers."""
    from core.db import engine as db_engine
    from core.llm import builtin_subagents
    from core.services import compaction_service, log_service, user_agent_service, user_service

    state = SimpleNamespace(
        error=ContextCompactionError(), shutdowns=0, stream_calls=0,
        reply_calls=0, closed_clients=0, direct_logs=[],
    )

    class DummySession:
        def __enter__(self):
            return SimpleNamespace()

        def __exit__(self, *_args):
            return False

    class FakeAgent:
        def __init__(self):
            self.model = SimpleNamespace(model="test-model", context_size=32_768)
            self.state = SimpleNamespace(
                ontology_runtime={}, context=[],
                apply_request_context=lambda *_args: None,
            )

        async def reply(self, **_kwargs):
            state.reply_calls += 1
            raise state.error

    class FakeStreamingAgent:
        def __init__(self, agent, _clients):
            self.agent = agent

        async def stream(self, _messages, _context, **_kwargs):
            state.stream_calls += 1
            yield "text_delta", PARTIAL
            yield "model_step", _step("assistant", [{
                "type": "tool_call", "id": CALL_ID, "name": TOOL_NAME,
                "input": '{"title":"test"}',
            }])
            yield "tool_call", {"id": CALL_ID, "name": TOOL_NAME, "args": {"title": "test"}}
            yield "model_step", _step("tool_result", [{
                "type": "tool_result", "id": CALL_ID, "name": TOOL_NAME,
                "output": json.dumps(RECEIPT), "state": "success",
            }])
            yield "tool_result", {
                "id": CALL_ID, "name": TOOL_NAME, "content": json.dumps(RECEIPT),
                "state": "success",
            }
            # The actual streaming adapter sends exceptions as error payloads.
            yield "error", state.error
            pytest.fail("workflow consumed events after the compaction failure")

        async def aget_usage(self):
            return {}

        def get_context_usage(self, _usage):
            return None

        async def shutdown(self):
            state.shutdowns += 1

    async def create_agent(**_kwargs):
        return FakeAgent(), []

    async def no_memory(*_args, **_kwargs):
        return None

    async def no_identity(*_args):
        return ""

    async def no_compaction(_chat_id, messages, **_kwargs):
        return messages, None

    async def close_clients(_clients):
        state.closed_clients += 1

    async def start_log(_payload):
        return "subagent-log-test"

    async def finish_log(_log_id, **kwargs):
        state.direct_logs.append(kwargs)

    monkeypatch.setattr(db_engine, "SessionLocal", lambda: DummySession())
    monkeypatch.setattr(user_agent_service, "UserAgentService", lambda _db: SimpleNamespace(
        list_for_user=lambda _user_id: [],
    ))
    monkeypatch.setattr(user_service, "UserService", lambda _db: SimpleNamespace(
        get_disabled_builtin_subagent_ids=lambda _user_id: set(),
    ))
    monkeypatch.setattr(builtin_subagents, "merge_builtin_subagents", lambda *_a, **_kw: [])
    monkeypatch.setattr(compaction_service, "maybe_run_pre_turn_compaction", no_compaction)
    monkeypatch.setattr(workflow, "create_agent_executor", create_agent)
    monkeypatch.setattr(workflow, "launch_memory_retrieval", no_memory)
    monkeypatch.setattr(workflow, "build_user_identity_block", no_identity)
    monkeypatch.setattr(workflow, "anchor_start_for_chat", lambda _chat_id: 0)
    monkeypatch.setattr(workflow, "enabled_skill_ids_from_context", lambda _ctx: [])
    monkeypatch.setattr(workflow, "enabled_mcp_ids_from_context", lambda _ctx: [])
    monkeypatch.setattr(workflow, "enabled_kb_ids_from_context", lambda _ctx: [])
    monkeypatch.setattr(workflow, "_resolve_mode_spec", lambda _ctx: None)
    monkeypatch.setattr(workflow, "StreamingAgent", FakeStreamingAgent)
    monkeypatch.setattr(workflow, "close_clients", close_clients)
    monkeypatch.setattr(workflow, "_persistent_clients", [])
    monkeypatch.setattr(workflow, "_load_direct_user_agent", lambda *_a, **_kw: SimpleNamespace(
        name="Test subagent", extra_config={},
    ))
    monkeypatch.setattr(log_service, "start_subagent_log", start_log)
    monkeypatch.setattr(log_service, "finish_subagent_log", finish_log)
    return state


def _context():
    return {
        "run_id": "run-test", "journal_owner": "worker-test",
        "chat_id": "chat-test", "user_id": "user-test", "memory_enabled": False,
        "ontology_runtime": {},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("direct", [False, True])
@pytest.mark.parametrize("wrapped", [False, True])
async def test_stream_propagates_failure_after_partial_and_committed_receipt(fake_runtime, direct, wrapped):
    fake_runtime.error = _failure(wrapped)
    kwargs = dict(session_messages=[{"role": "user", "content": "处理询盘"}],
                  user_message="处理询盘", context=_context())
    stream = (workflow._astream_subagent_direct(agent_id="agent-test", **kwargs)
              if direct else workflow.astream_chat_workflow(**kwargs))
    chunks = []
    with pytest.raises(ContextCompactionError, match="本轮未完成"):
        async for event in stream:
            chunks.append(event)
    assert any(event.get("delta") == PARTIAL for event in chunks)
    result = next(event for event in chunks if event["type"] == "tool_result")
    assert result["tool_id"] == CALL_ID and result["result"] == RECEIPT
    assert not any(event["type"] == "meta" for event in chunks)
    assert fake_runtime.stream_calls == 1 and fake_runtime.shutdowns == 1
    if direct:
        assert len(fake_runtime.direct_logs) == 1
        assert fake_runtime.direct_logs[0]["status"] == "failed"
        assert fake_runtime.direct_logs[0]["error_message"] == COMPACTION_FAILURE_MESSAGE


@pytest.mark.parametrize("wrapped", [False, True])
@pytest.mark.parametrize("direct", [False, True])
def test_sync_workflow_propagates_compaction_failure(fake_runtime, wrapped, direct):
    fake_runtime.error = _failure(wrapped)
    context = _context()
    if direct:
        context["agent_id"] = "agent-test"
    with pytest.raises(ContextCompactionError, match="本轮未完成"):
        workflow.run_chat_workflow(
            session_messages=[{"role": "user", "content": "处理询盘"}],
            user_message="处理询盘", context=context,
        )
    assert fake_runtime.reply_calls == 1
    assert fake_runtime.closed_clients == 1


@pytest.mark.asyncio
async def test_main_stream_stops_before_model_when_pre_turn_compaction_fails(fake_runtime, monkeypatch):
    from core.services import compaction_service

    async def fail_compaction(*_args, **_kwargs):
        raise ContextCompactionError()

    monkeypatch.setattr(compaction_service, "maybe_run_pre_turn_compaction", fail_compaction)
    chunks = []
    with pytest.raises(ContextCompactionError, match="本轮未完成"):
        async for event in workflow.astream_chat_workflow(
            session_messages=[{"role": "user", "content": "处理询盘"}],
            user_message="处理询盘", context=_context(),
        ):
            chunks.append(event)
    assert fake_runtime.stream_calls == 0 and fake_runtime.reply_calls == 0
    assert not any(event["type"] in {"meta", "tool_call", "tool_result", "content"}
                   for event in chunks)


def test_sync_stops_before_model_when_pre_turn_compaction_fails(fake_runtime, monkeypatch):
    from core.services import compaction_service

    async def fail_compaction(*_args, **_kwargs):
        raise ContextCompactionError()

    monkeypatch.setattr(compaction_service, "maybe_run_pre_turn_compaction", fail_compaction)
    with pytest.raises(ContextCompactionError, match="本轮未完成"):
        workflow.run_chat_workflow(
            session_messages=[{"role": "user", "content": "处理询盘"}],
            user_message="处理询盘", context=_context(),
        )
    assert fake_runtime.reply_calls == 0 and fake_runtime.stream_calls == 0
    assert fake_runtime.closed_clients == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("direct", [False, True])
async def test_executor_atomically_fails_and_retains_partial_receipt(
    fake_runtime, monkeypatch, tmp_path, direct,
):
    """Run real workflow -> executor -> SQLite journal/message -> replay."""
    from core.db.engine import Base
    from core.db.models import ChatMessage, ChatRun, ChatRunOperation, ChatSession
    from core.services.compaction_service import _normalize_rows
    from core.services.run_journal import RunJournal
    from orchestration import chat_run_executor as executor
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(f"sqlite:///{tmp_path / 'compaction-failure.sqlite'}",
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(executor, "SessionLocal", sessions)
    emitted, background, failure_logs = [], [], []

    async def emit(_run_id, _offset, event):
        emitted.append(event)

    async def expire(_run_id):
        return None

    monkeypatch.setattr(executor, "_xadd_event", emit)
    monkeypatch.setattr(executor, "_expire_stream", expire)
    monkeypatch.setattr(executor.logger, "error", lambda event, **fields: failure_logs.append((event, fields)))
    monkeypatch.setattr(executor, "_spawn_followup_task", lambda **_kw: background.append("followup"))
    monkeypatch.setattr(executor, "_spawn_compaction_task", lambda **_kw: background.append("compaction"))
    fake_runtime.error = _failure(wrapped=True)
    context = _context()
    if direct:
        context["agent_id"] = "agent-test"
    with sessions() as db:
        db.add(ChatSession(chat_id="chat-test", user_id="user-test", title="test"))
        db.add(ChatMessage(message_id="user-msg", chat_id="chat-test", role="user", content="处理询盘"))
        db.add(ChatMessage(message_id="assistant-msg", chat_id="chat-test", role="assistant", content=""))
        db.commit()
    journal = RunJournal(sessions)
    journal.accept(run_id="run-test", message_id="assistant-msg", chat_id="chat-test",
                   user_id="user-test", request_payload={"kind": "chat"},
                   recovery_snapshot={"kind": "chat", "worker_args": {}})
    try:
        await executor._run_workflow(
            run_id="run-test", chat_id="chat-test", user_id="user-test",
            message_id="assistant-msg", session_messages=[{"role": "user", "content": "处理询盘"}],
            effective_user_message="处理询盘", raw_user_message="处理询盘",
            context=context, model_name="test-model", journal_owner="worker-test",
        )
        with sessions() as db:
            run = db.get(ChatRun, "run-test")
            row = db.get(ChatMessage, "assistant-msg")
            assert run.status == "failed" and run.run_phase == "failed"
            assert run.lease_owner is None and run.writer_slot is None
            assert run.failure_reason == COMPACTION_FAILURE_MESSAGE
            assert row.content == PARTIAL
            assert row.error["error"] == COMPACTION_FAILURE_MESSAGE
            assert db.get(ChatMessage, "user-msg").content == "处理询盘"
            assert len(row.tool_calls) == 1
            assert row.tool_calls[0]["tool_id"] == CALL_ID
            assert row.tool_calls[0]["result"] == RECEIPT
            assert row.tool_calls[0]["status"] == "success"
            steps = row.model_steps
            assert [step["kind"] for step in steps] == ["assistant", "tool_result"]
            assert json.loads(steps[1]["blocks"][0]["output"]) == RECEIPT
            assert steps[1]["blocks"][0]["state"] == "success"
            replay = _normalize_rows([row])
            assert any(item["role"] == "tool" and json.loads(item["content"][0]["output"]) == RECEIPT
                       for item in replay)
            operations = db.query(ChatRunOperation).filter_by(run_id="run-test").all()
            assert any(item.operation_type == "run_failed" for item in operations)
            assert not any(item.operation_type == "run_completed" for item in operations)
        errors = [event for event in emitted if event["type"] == "error"]
        assert len(errors) == 1 and errors[0]["error"] == COMPACTION_FAILURE_MESSAGE
        failures = [fields for event, fields in failure_logs if event == "chat_run_failed"]
        assert len(failures) == 1
        assert failures[0]["error"] == COMPACTION_FAILURE_MESSAGE
        assert failures[0]["exc_info"] is False
        assert emitted[-1]["type"] == executor._TERMINAL_TYPE
        assert not background
        assert fake_runtime.stream_calls == 1
        if direct:
            assert fake_runtime.direct_logs[0]["status"] == "failed"
    finally:
        engine.dispose()

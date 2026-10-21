"""Tool-result projections must join by call ID, never by completion order."""
# Modified by foreign-trade-agent contributors, 2026-10-21; see CHANGES_FOREIGN_TRADE.md.
from itertools import permutations
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "backend"))
from core.chat.tool_log import attach_tool_result, build_tool_call_event, build_tool_result_event, upsert_tool_call


def entry(tool_id, action="get", name="trade_inquiry"):
    return {"tool_id": tool_id, "tool_name": name, "tool_args": {"action": action}}


@pytest.mark.parametrize("completion_order", list(permutations(["bad", "guarded", "valid"])))
def test_same_name_calls_keep_their_own_args_results_and_status(completion_order):
    log = []
    actions = {"bad": "invalid_shape", "guarded": "skill_not_loaded", "valid": "create"}
    for tool_id, action in actions.items():
        upsert_tool_call(log, entry(tool_id, action))
    for tool_id in completion_order:
        attach_tool_result(log, tool_id, "trade_inquiry", {"reply_for": tool_id},
                           status="success" if tool_id == "valid" else "error")
    assert len(log) == 3
    for call in log:
        assert call["tool_args"] == {"action": actions[call["tool_id"]]}
        assert call["result"] == {"reply_for": call["tool_id"]}
        assert call["status"] == ("success" if call["tool_id"] == "valid" else "error")


def test_unknown_result_id_does_not_take_an_earlier_same_name_pending_call():
    log = [entry("pending")]
    duration = attach_tool_result(log, "new", "trade_inquiry", {"ok": True})
    assert duration is None
    assert "result" not in log[0]
    assert log[1] == {"tool_name": "trade_inquiry", "tool_id": "new", "result": {"ok": True}, "status": "success"}
    assert "started_at" not in log[1]


def test_new_id_result_preserves_settled_same_name_call():
    previous = {**entry("settled"), "result": {"earlier": True}, "status": "error", "duration_ms": 23}
    log = [previous.copy(), entry("pending")]
    attach_tool_result(log, "new", "trade_inquiry", {"latest": True})
    assert log[0] == previous
    assert "result" not in log[1]
    assert log[2]["tool_id"] == "new"
    assert log[2]["result"] == {"latest": True}


def test_orphan_result_accepts_later_arguments_for_its_exact_id_only():
    log = [entry("pending", "create")]
    attach_tool_result(log, "new", "trade_inquiry", {"reply_for": "new"})
    upsert_tool_call(log, {**entry("new", "get"), "tool_display_name": "Inquiry"})
    assert len(log) == 2
    assert "result" not in log[0]
    assert log[1]["tool_args"] == {"action": "get"}
    assert log[1]["tool_display_name"] == "Inquiry"
    assert log[1]["result"] == {"reply_for": "new"}
    assert "started_at" not in log[1]  # no honest start time was observed


def test_known_new_id_matches_exactly_after_it_is_appended():
    log = [entry("old"), entry("new")]
    attach_tool_result(log, "new", "trade_inquiry", {"version": "new"})
    assert "result" not in log[0]
    assert log[1]["result"] == {"version": "new"}


def test_legacy_result_without_id_can_settle_an_unfinished_same_name_call():
    log = [{**entry("completed"), "result": {"done": True}}, entry("pending")]
    attach_tool_result(log, "", "trade_inquiry", {"legacy": True})
    assert log[0]["result"] == {"done": True}
    assert log[1]["result"] == {"legacy": True}


def test_identity_wins_even_if_result_has_a_different_display_name():
    log = [entry("other", name="alternate_name"), entry("target", name="trade_inquiry")]
    attach_tool_result(log, "target", "alternate_name", {"identity": "target"})
    assert "result" not in log[0]
    assert log[1]["result"] == {"identity": "target"}
    assert log[1]["tool_name"] == "trade_inquiry"


def test_wire_event_and_persisted_projection_agree_on_result_id(monkeypatch):
    monkeypatch.setattr("core.chat.tool_log.now_ms", lambda: 2000)
    log = []
    build_tool_call_event(entry("first", "invalid"), "chat", log)
    build_tool_call_event(entry("second", "create"), "chat", log)
    log[0]["started_at"] = 1000
    log[1]["started_at"] = 1500
    event = build_tool_result_event({"tool_id": "second", "tool_name": "trade_inquiry", "result": {"inquiry": "second"}}, "chat", log)
    assert event["tool_id"] == "second"
    assert event["result"] == log[1]["result"]
    assert event["duration_ms"] == log[1]["duration_ms"] == 500
    assert "result" not in log[0]


def test_result_without_identity_or_name_does_not_change_log():
    log = [entry("pending")]
    assert attach_tool_result(log, "", "", {"orphan": True}) is None
    assert log == [entry("pending")]

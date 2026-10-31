"""A partial SKILL.md preview must not authorize a trade workflow."""
from types import SimpleNamespace

import pytest
from core.llm.factory.tools.definitions import ToolAssembly as ToolCollector
from core.llm.tools import skill_tool


@pytest.mark.parametrize("ranges,full", [([1, 1], False), ([99, 100], False), ([1, 6], True), (None, True), ([], True)])
async def test_only_complete_skill_read_marks_full_state(tmp_path, monkeypatch, ranges, full):
    directory = tmp_path / "foreign-trade-demo-product-content-abcdef"
    directory.mkdir()
    path = directory / "SKILL.md"
    path.write_text("---\nname: product-content\ndescription: product workflow\n---\nConfirm facts first.\nThen generate.\n")
    monkeypatch.setattr(skill_tool, "_build_skill_bash_hint", lambda *args: None)
    loader = SimpleNamespace(load_skill_full=lambda sid: None, get_skill_source=lambda sid: "local")
    from core.harness import log_writer as log_service
    monkeypatch.setattr(log_service, "schedule_skill_call_write", lambda value: None)
    collector, loaded, complete = ToolCollector(), set(), set()
    skill_tool.register_sandboxed_view_text_file(collector, [str(directory)], loader,
        loaded_skill_ids=loaded, fully_loaded_skill_ids=complete)
    await next(tool for tool in collector if tool.name == "view_text_file")._func(file_path=str(path), ranges=ranges)
    assert (directory.name in loaded) is (ranges != [99, 100])
    assert (directory.name in complete) is full


@pytest.mark.parametrize("ranges", [[1], [0, 2], [3, 2], [1, 2, 3]])
async def test_invalid_ranges_do_not_authorize_a_skill(tmp_path, monkeypatch, ranges):
    directory = tmp_path / "skill"
    directory.mkdir()
    path = directory / "SKILL.md"
    path.write_text("Instructions")
    collector, complete = ToolCollector(), set()
    skill_tool.register_sandboxed_view_text_file(
        collector, [str(directory)], SimpleNamespace(), fully_loaded_skill_ids=complete
    )
    result = await collector[0]._func(file_path=str(path), ranges=ranges)
    assert str(result.state) == "error"
    assert not complete


async def test_empty_skill_is_an_error_and_does_not_grant_full_read(tmp_path):
    directory = tmp_path / "skill"
    directory.mkdir()
    path = directory / "SKILL.md"
    path.write_text("")
    collector, loaded, complete = ToolCollector(), set(), set()
    skill_tool.register_sandboxed_view_text_file(
        collector, [str(directory)], SimpleNamespace(),
        loaded_skill_ids=loaded, fully_loaded_skill_ids=complete,
    )
    result = await collector[0]._func(file_path=str(path), ranges=[])
    assert str(result.state) == "error"
    assert not loaded and not complete


async def test_versioned_path_uses_current_binding_and_rejects_old_or_unbound_revision(tmp_path, monkeypatch):
    from core.harness.registry import capability_runtime
    from core.agent_runtime.skills import _extract_skill_id_from_path

    key = "buyer-inquiry-followup-owner"
    root = tmp_path / "skills" / "local" / key
    current, old = root / "abcdef123456", root / "012345abcdef"
    for directory in (current, old):
        directory.mkdir(parents=True)
        (directory / "SKILL.md").write_text("---\nname: buyer-inquiry-followup\ndescription: Test\n---\nRead all facts.")
    prepared = SimpleNamespace(bindings={key: {"profile": "local"}})
    loader = SimpleNamespace(
        capability_run=prepared,
        get_skill_dir=lambda name: str(current) if name == key else None,
        load_skill_full=lambda _: None,
        get_skill_source=lambda _: "local",
    )
    checked = []
    monkeypatch.setattr(capability_runtime, "validate", lambda p, only_skill: checked.append(only_skill))
    monkeypatch.setattr(skill_tool, "_build_skill_bash_hint", lambda *a: None)
    monkeypatch.setattr(skill_tool, "_resolve_skill_path", lambda *a: None)
    from core.harness import log_writer
    monkeypatch.setattr(log_writer, "schedule_skill_call_write", lambda value: None)
    collector, loaded, complete = ToolCollector(), set(), set()
    skill_tool.register_sandboxed_view_text_file(
        collector, [str(root)], loader, loaded_skill_ids=loaded, fully_loaded_skill_ids=complete
    )
    result = await collector[0]._func(file_path=str(current / "SKILL.md"), ranges=[])
    assert str(result.state) == "success"
    assert result.metadata == {"skill_id": key, "fully_read": True}
    assert key in complete and key in loaded
    assert checked == [key]
    assert _extract_skill_id_from_path(str(current / "SKILL.md")) == key
    complete.clear()
    result = await collector[0]._func(file_path=str(old / "SKILL.md"), ranges=[])
    assert str(result.state) == "denied"
    assert not complete
    prepared.bindings = {}
    result = await collector[0]._func(file_path=str(current / "SKILL.md"), ranges=[])
    assert str(result.state) == "denied"
    assert not complete


@pytest.mark.parametrize("mode", ["main", "direct"])
@pytest.mark.parametrize("status", ["denied", "error", "success"])
async def test_skill_result_projection_preserves_failure_and_current_identity(monkeypatch, mode, status):
    from core.agent_runtime.main_state import MainTurn
    from core.agent_runtime.direct_state import DirectTurn
    from core.agent_runtime.stream_main import stream_main
    from core.agent_runtime.stream_direct import stream_direct
    from core.chat import tool_payloads
    from core.llm.citations import allocator

    key = "buyer-inquiry-followup-owner"
    path = f"/authorized/skills/local/{key}/abcdef123456/SKILL.md"
    content = "Complete instructions." if status == "success" else "Error: Access denied; no skill loaded."
    async def source(*args, **kwargs):
        yield "tool_call", {"name": "view_text_file", "id": "read-id", "args": {"file_path": path, "ranges": []}}
        yield "tool_result", {"name": "view_text_file", "id": "read-id", "status": status, "content": content}

    built = []
    def curated(sid):
        built.append(sid)
        return {"kind": "skill_detail", "skill_id": sid, "detail": "Current skill instructions"}
    monkeypatch.setattr(tool_payloads, "_build_skill_load_payload", curated)
    monkeypatch.setattr(allocator, "collect_citation_dicts", lambda *a: [])
    streaming = SimpleNamespace(agent=SimpleNamespace(state=SimpleNamespace(ontology_runtime={})), stream=source)
    if mode == "main":
        turn = MainTurn(context={}, session_messages=[], user_message="test", streaming_agent=streaming)
        output = [event async for event in stream_main(turn)]
    else:
        turn = DirectTurn(context={}, session_messages=[], streaming_agent=streaming, direct_stream=source())
        output = [event async for event in stream_direct(turn)]
    result = next(event for event in output if event["type"] == "tool_result")
    assert result["status"] == status
    if status == "success":
        assert built == [key]
        assert result["result"]["skill_id"] == key
        assert result["result"]["detail"]
    else:
        assert not built
        assert result["result"] == {"result": content}
        assert result["result"].get("kind") != "skill_detail"

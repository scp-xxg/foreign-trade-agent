"""A partial SKILL.md preview must not authorize a trade workflow."""
from types import SimpleNamespace

import pytest
from core.llm.tool_collector import ToolCollector
from core.llm.tools import skill_tool


@pytest.mark.parametrize("ranges,full", [([1, 1], False), ([99, 100], False), ([1, 6], True), (None, True)])
async def test_only_complete_skill_read_marks_full_state(tmp_path, monkeypatch, ranges, full):
    directory = tmp_path / "foreign-trade-demo-product-content-abcdef"
    directory.mkdir()
    path = directory / "SKILL.md"
    path.write_text("---\nname: product-content\ndescription: product workflow\n---\nConfirm facts first.\nThen generate.\n")
    monkeypatch.setattr(skill_tool, "_build_skill_bash_hint", lambda *args: None)
    loader = SimpleNamespace(load_skill_full=lambda sid: None, get_skill_source=lambda sid: "local")
    from core.services import log_service
    monkeypatch.setattr(log_service, "schedule_skill_call_write", lambda value: None)
    collector, loaded, complete = ToolCollector(), set(), set()
    skill_tool.register_sandboxed_view_text_file(collector, [str(directory)], loader,
        loaded_skill_ids=loaded, fully_loaded_skill_ids=complete)
    await collector.get_tool("view_text_file")._func(file_path=str(path), ranges=ranges)
    assert directory.name in loaded
    assert (directory.name in complete) is full

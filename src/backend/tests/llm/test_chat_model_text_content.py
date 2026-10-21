"""Regression coverage for strict upstreams rejecting text arrays and null tool content."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from agentscope.message import Msg, TextBlock, ToolCallBlock, ToolResultBlock

from core.llm.chat_models import (
    _normalize_text_only_content,
    make_chat_model,
)
from core.llm.context_adapter import PROVIDER_CONTEXT_META_KEY


@pytest.mark.parametrize("role", ["system", "user", "assistant", "tool"])
def test_text_blocks_keep_order_newlines_and_other_fields(role):
    original = [{"role": role, "name": "test", "content": [
        {"type": "text", "text": "第一行\n第二行"},
        {"type": "text", "text": ""},
        {"type": "text", "text": "最后"},
    ]}]
    snapshot = deepcopy(original)
    result = _normalize_text_only_content(original)
    assert result == [{"role": role, "name": "test", "content": "第一行\n第二行\n\n最后"}]
    assert original == snapshot
    assert _normalize_text_only_content(result) == result


@pytest.mark.parametrize("content", [None, []])
def test_tool_only_assistant_uses_empty_string_and_keeps_call_and_reasoning(content):
    original = [{"role": "assistant", "content": content,
                 "tool_calls": [{"id": "call_1", "type": "function",
                                 "function": {"name": "multiply", "arguments": "{}"}}],
                 "reasoning_content": "先调用工具"}]
    snapshot = deepcopy(original)
    result = _normalize_text_only_content(original)
    assert result[0] == {**original[0], "content": ""}
    assert original == snapshot


@pytest.mark.parametrize("content", [
    [{"type": "text", "text": "说明"},
     {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}],
    [{"type": "input_audio", "input_audio": {"data": "AAAA", "format": "wav"}}],
    [{"type": "text", "text": "缓存", "cache_control": {"type": "ephemeral"}}],
    [{"type": "text", "text": None}],
    "原始字符串", None, [],
])
def test_media_extensions_and_nonstandard_content_are_preserved(content):
    original = [{"role": "user", "content": content}]
    snapshot = deepcopy(original)
    assert _normalize_text_only_content(original) == snapshot
    assert original == snapshot


def _model():
    return make_chat_model(
        model="test-model", temperature=0.6, max_tokens=32, timeout=5,
        base_url="http://example.invalid/v1", api_key="dummy",
        context_size=4096, stream=False,
    )


@pytest.mark.asyncio
async def test_actual_request_normalizes_plain_chat_and_tool_history(monkeypatch):
    class CapturedRequest(Exception):
        pass

    create = AsyncMock(side_effect=CapturedRequest)
    model = _model()
    monkeypatch.setattr(model, "_build_client", lambda: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    monkeypatch.setattr("core.llm.model_usage.record_provider_failure", AsyncMock())
    messages = [
        Msg(name="user", role="user", content=[TextBlock(type="text", text="计算")]),
        Msg(name="assistant", role="assistant", content=[
            ToolCallBlock(type="tool_call", id="call_1", name="multiply", input="{}")]),
        Msg(name="assistant", role="assistant", content=[
            ToolResultBlock(type="tool_result", id="call_1", name="multiply", output="6")]),
    ]
    try:
        with pytest.raises(CapturedRequest):
            await model._call_api("test-model", messages)
        rows = create.call_args.kwargs["messages"]
        assert [row["role"] for row in rows] == ["user", "assistant", "tool"]
        assert all(isinstance(row["content"], str) for row in rows)
        assert rows[0]["content"] == "计算"
        assert rows[1]["content"] == ""
        assert rows[1]["tool_calls"][0]["id"] == "call_1"
        assert rows[2]["tool_call_id"] == "call_1"
        assert "6" in rows[2]["content"]
    finally:
        await model._http_client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("async_listener", [False, True])
async def test_retry_rewrite_normalizes_after_listener_and_strips_internal_metadata(async_listener):
    model = _model()
    rewritten = [{"role": "user", "content": [{"type": "text", "text": "图片转写结果"}],
                  PROVIDER_CONTEXT_META_KEY: {"private": "context-provenance"}}]
    snapshot = deepcopy(rewritten)
    def listener(rows):
        assert rows == [{"role": "user", "content": "原始输入"}]
        return rewritten

    async def awaited_listener(rows):
        return listener(rows)

    model.set_context_rewrite_listener(awaited_listener if async_listener else listener)
    try:
        result = await model._publish_context_rewrite([
            {"role": "user", "content": [{"type": "text", "text": "原始输入"}]}
        ])
        assert result == [{"role": "user", "content": "图片转写结果"}]
        assert rewritten == snapshot
    finally:
        await model._http_client.aclose()

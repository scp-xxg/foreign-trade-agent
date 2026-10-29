"""Compatible upstreams may recycle tool IDs; later tools must still execute."""
from datetime import datetime
from types import SimpleNamespace

import pytest
from agentscope.state import AgentState
from agentscope.message import Msg, TextBlock, ThinkingBlock, ToolCallBlock, ToolResultBlock
from agentscope.model import ChatResponse, OpenAIChatModel

from core.models.providers.openai_compat import _namespace_response_tool_calls
from core.models.chat_models import make_chat_model


def response(name="calculate_quote", raw_id="call_reused", *, final=True, arguments="{}"):
    return ChatResponse(
        content=[ToolCallBlock(id=raw_id, name=name, input=arguments)],
        is_last=final, metadata={"keep": "metadata"},
    )


def test_reused_upstream_id_does_not_hide_new_tool_behind_old_result():
    first = _namespace_response_tool_calls(response("view_text_file"), {})
    second = _namespace_response_tool_calls(response("calculate_quote"), {})
    first_call, second_call = first.content[0], second.content[0]
    assert first_call.id != second_call.id
    msg = Msg(name="assistant", role="assistant", content=[
        first_call, ToolResultBlock(id=first_call.id, name=first_call.name, output="skill loaded"),
        second_call,
    ])
    pending = AgentState(context=[msg], reply_id=msg.id).get_unfinished_tool_calls("assistant")
    assert [call.name for call in pending] == ["calculate_quote"]


def test_incremental_and_final_blocks_share_id_without_mutating_input():
    mapping = {}
    part = response(final=False, arguments='{"items":')
    final = response(final=True, arguments='{"items":[]}')
    mapped_part = _namespace_response_tool_calls(part, mapping)
    mapped_final = _namespace_response_tool_calls(final, mapping)
    assert mapped_part.content[0].id == mapped_final.content[0].id
    assert mapped_part.content[0].input == '{"items":'
    assert mapped_final.content[0].input == '{"items":[]}'
    assert part.content[0].id == final.content[0].id == "call_reused"
    assert mapped_final.id == final.id
    assert mapped_final.metadata == final.metadata
    assert mapped_final.is_last is True


def test_text_and_reasoning_are_unchanged():
    original = ChatResponse(content=[
        ThinkingBlock(thinking="reasoning"), TextBlock(text="answer")
    ], is_last=True)
    assert _namespace_response_tool_calls(original, {}) is original


def model():
    return make_chat_model(
        model="test-model", temperature=0.6, max_tokens=32, timeout=5,
        base_url="http://example.invalid/v1", api_key="dummy",
        api_protocol="chat_completions", context_size=4096, stream=True,
    )


@pytest.mark.asyncio
async def test_stream_parser_uses_one_scope_per_response(monkeypatch):
    async def fake_parse(self, start, raw):
        yield response(final=False)
        yield response(final=True)

    monkeypatch.setattr(OpenAIChatModel, "_parse_stream_response", fake_parse)
    m = model()
    try:
        first = [r async for r in m._parse_stream_response(datetime.now(), None)]
        second = [r async for r in m._parse_stream_response(datetime.now(), None)]
        assert first[0].content[0].id == first[1].content[0].id
        assert second[0].content[0].id == second[1].content[0].id
        assert first[0].content[0].id != second[0].content[0].id
    finally:
        await m._http_client.aclose()


@pytest.mark.asyncio
async def test_completion_parser_uses_a_new_scope_and_formatter_pairs_result(monkeypatch):
    monkeypatch.setattr(OpenAIChatModel, "_parse_completion_response",
                        lambda self, start, raw, audio: response())
    m = model()
    try:
        first = m._parse_completion_response(datetime.now(), None, "wav")
        second = m._parse_completion_response(datetime.now(), None, "wav")
        call = second.content[0]
        assert first.content[0].id != call.id
        rows = await m.formatter.format([
            Msg(name="assistant", role="assistant", content=[call]),
            Msg(name="assistant", role="assistant", content=[
                ToolResultBlock(id=call.id, name=call.name, output="2400.00")
            ]),
        ])
        assert rows[0]["tool_calls"][0]["id"] == rows[1]["tool_call_id"] == call.id
    finally:
        await m._http_client.aclose()

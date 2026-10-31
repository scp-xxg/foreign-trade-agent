"""Responses terminal states and reasoning replay using the installed SDK, offline."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import openai
import pytest
from agentscope.credential import OpenAICredential
from agentscope.message import Msg, TextBlock, ThinkingBlock, ToolCallBlock, ToolResultBlock
from agentscope.model import OpenAIResponseModel
from openai.types.responses import ResponseReasoningItem

from core.models.responses import (
    OpenAICompatResponsesModel,
    ResponsesIncompleteError,
    WIRE_PROTOCOL,
)


def _event(kind, **fields):
    return SimpleNamespace(type=kind, **fields)


class _Stream:
    def __init__(self, events):
        self.events = events
        self.closed = False
        self.response = httpx.Response(
            200, request=httpx.Request("POST", "https://offline.invalid/v1/responses")
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True
        return False

    def __aiter__(self):
        async def source():
            for event in self.events:
                yield event
        return source()


def _completed(output=()):
    return _event(
        "response.completed",
        response=SimpleNamespace(output=list(output), usage=None, status="completed"),
    )


@asynccontextmanager
async def _model(response, *, stream=True):
    def deny_network(request):
        raise AssertionError("This regression must never access a model service")

    async with httpx.AsyncClient(transport=httpx.MockTransport(deny_network)) as client:
        model = OpenAICompatResponsesModel(
            credential=OpenAICredential(api_key="offline-placeholder", base_url="https://offline.invalid/v1"),
            model="offline-model",
            parameters=OpenAIResponseModel.Parameters(),
            stream=stream,
            http_client=client,
            context_size=8192,
        )
        create = AsyncMock(return_value=response)
        model._openai_client = SimpleNamespace(responses=SimpleNamespace(create=create))
        yield model, create


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["response.failed", "error"])
async def test_sse_failure_retains_native_error_code_and_closes_stream(kind):
    error = SimpleNamespace(
        code="synthetic_failure",
        message="Offline provider failure",
        model_dump=lambda: {"code": "synthetic_failure", "message": "Offline provider failure"},
    )
    event = (
        _event(kind, response=SimpleNamespace(error=error))
        if kind == "response.failed"
        else _event(kind, **vars(error))
    )
    stream = _Stream([event])
    model = object.__new__(OpenAICompatResponsesModel)
    with pytest.raises(openai.APIError) as raised:
        async for _ in model._parse_stream_response(datetime.now(), stream):
            pass
    assert raised.value.code == "synthetic_failure"
    assert raised.value.message == "Offline provider failure"
    assert stream.closed


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", ["incomplete", "eof"])
async def test_partial_output_and_prior_tool_receipt_survive_without_success_or_retry(terminal):
    events = [
        _event("response.output_text.delta", item_id="msg_1", content_index=0, delta="Saved receipt retained."),
        _event(
            "response.output_item.added",
            item=SimpleNamespace(type="function_call", id="fc_next", call_id="call_next", name="read_quote"),
        ),
        _event("response.function_call_arguments.delta", item_id="fc_next", delta='{"quote_id":"q1"}'),
    ]
    if terminal == "incomplete":
        events.append(_event(
            "response.incomplete",
            response=SimpleNamespace(incomplete_details=SimpleNamespace(reason="max_output_tokens")),
        ))
    stream = _Stream(events)
    messages = [
        Msg(name="assistant", role="assistant", content=[ToolCallBlock(id="call_saved", name="save_quote", input="{}")]),
        Msg(name="assistant", role="assistant", content=[ToolResultBlock(id="call_saved", name="save_quote", output="saved:q1")]),
    ]
    before = [message.model_dump() for message in messages]
    seen = []
    async with _model(stream) as (model, create):
        response = await model(messages)
        with pytest.raises(ResponsesIncompleteError) as raised:
            async for chunk in response:
                seen.append(chunk)
        assert create.await_count == 1
    assert raised.value.reason == (
        "max_output_tokens" if terminal == "incomplete" else "stream_ended_before_completed"
    )
    assert [message.model_dump() for message in messages] == before
    assert all(not chunk.is_last for chunk in seen)
    assert [b.text for c in seen for b in c.content if isinstance(b, TextBlock)] == ["Saved receipt retained."]
    assert [b.id for c in seen for b in c.content if isinstance(b, ToolCallBlock)] == ["call_next"]
    assert stream.closed


@pytest.mark.asyncio
async def test_empty_eof_is_an_error_not_an_empty_completed_answer():
    stream = _Stream([])
    async with _model(stream) as (model, create):
        response = await model([Msg(name="user", role="user", content=[TextBlock(text="hello")])])
        with pytest.raises(ResponsesIncompleteError, match="stream_ended_before_completed"):
            _ = [chunk async for chunk in response]
        assert create.await_count == 1
    assert stream.closed


def _reasoning_items():
    return [
        ResponseReasoningItem(
            type="reasoning", id=f"rs_{suffix}", summary=[], encrypted_content=f"OFFLINE_{suffix}"
        )
        for suffix in ("a", "b")
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
async def test_native_multiple_reasoning_items_replay_once_with_tool_call_and_result(streaming):
    items = _reasoning_items()
    call = SimpleNamespace(type="function_call", id="fc_1", call_id="call_1", name="read_quote", arguments="{}")
    if streaming:
        raw = _Stream([
            _event("response.output_item.added", item=call),
            _event("response.function_call_arguments.done", item_id="fc_1", arguments="{}"),
            _completed([*items, call]),
        ])
    else:
        raw = SimpleNamespace(output=[*items, call], usage=None, id="resp_offline", status="completed")
    async with _model(raw, stream=streaming) as (model, create):
        response = await model([Msg(name="user", role="user", content=[TextBlock(text="read quote")])])
        if streaming:
            chunks = [chunk async for chunk in response]
            final = chunks[-1]
            assert final.is_last
        else:
            final = response
        for block in final.content:
            if isinstance(block, ThinkingBlock):
                block.provider = "openai_compatible"
                block.model = "offline-model"
                block.protocol = WIRE_PROTOCOL
        history = [
            Msg(name="assistant", role="assistant", content=final.content),
            Msg(name="assistant", role="assistant", content=[ToolResultBlock(id="call_1", name="read_quote", output="quote:q1")]),
        ]
        rows = await model.formatter.format(history)
        assert create.await_count == 1
    assert [row for row in rows if row.get("type") == "reasoning"] == [
        item.model_dump(exclude_none=True) for item in items
    ]
    assert [row["type"] for row in rows] == [
        "reasoning", "reasoning", "function_call", "function_call_output"
    ]
    assert [row["call_id"] for row in rows if "call_id" in row] == ["call_1", "call_1"]


@pytest.mark.parametrize("status", ["incomplete", "failed", "cancelled", "in_progress"])
def test_nonstream_noncompleted_status_cannot_become_success(status):
    model = object.__new__(OpenAICompatResponsesModel)
    response = SimpleNamespace(
        output=[], usage=None, status=status,
        incomplete_details=SimpleNamespace(reason="max_output_tokens"),
    )
    with pytest.raises(ResponsesIncompleteError):
        model._parse_completion_response(datetime.now(), response)


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_source", ["consumer_task", "provider_iterator"])
async def test_cancellation_keeps_partial_receipt_and_allows_next_turn(cancel_source):
    waiting = asyncio.Event()

    class CancellableStream(_Stream):
        def __aiter__(self):
            async def source():
                for event in self.events:
                    yield event
                waiting.set()
                if cancel_source == "provider_iterator":
                    raise asyncio.CancelledError()
                await asyncio.Event().wait()
            return source()

    raw = CancellableStream([
        _event("response.output_text.delta", item_id="msg_partial", content_index=0, delta="Partial answer."),
        _event(
            "response.output_item.added",
            item=SimpleNamespace(type="function_call", id="fc_pending", call_id="call_pending", name="read_quote"),
        ),
        _event("response.function_call_arguments.delta", item_id="fc_pending", delta='{"quote_id":"q1"}'),
    ])
    messages = [
        Msg(name="assistant", role="assistant", content=[
            ToolCallBlock(id="call_saved", name="save_quote", input="{}"),
            ToolResultBlock(id="call_saved", name="save_quote", output="saved:q1"),
        ]),
        Msg(name="user", role="user", content=[TextBlock(text="continue")]),
    ]
    before = [message.model_dump() for message in messages]
    seen = []
    async with _model(raw) as (model, create):
        response = await model(messages)

        async def consume():
            async for chunk in response:
                seen.append(chunk)

        consumer = asyncio.create_task(consume())
        try:
            await asyncio.wait_for(waiting.wait(), timeout=2)
            if cancel_source == "consumer_task":
                consumer.cancel()
            await asyncio.wait_for(consumer, timeout=2)
        finally:
            if not consumer.done():
                consumer.cancel()
                try:
                    await consumer
                except asyncio.CancelledError:
                    pass

        assert raw.closed
        assert create.await_count == 1
        assert seen[-1].is_last
        assert str(seen[-1].finished_reason) == "interrupted"
        assert [block.text for block in seen[-1].content if isinstance(block, TextBlock)] == ["Partial answer."]
        assert [block.id for block in seen[-1].content if isinstance(block, ToolCallBlock)] == ["call_pending"]
        assert [message.model_dump() for message in messages] == before

        # Reuse the same model after cancellation. The saved result must still
        # reach the provider input, and the next turn must complete normally.
        following = _Stream([
            _event("response.output_text.delta", item_id="msg_next", content_index=0, delta="Next turn completed."),
            _completed(),
        ])
        create.return_value = following
        next_response = await model(messages)
        next_chunks = [chunk async for chunk in next_response]
        assert next_chunks[-1].is_last
        assert str(next_chunks[-1].finished_reason) == "completed"
        assert [block.text for block in next_chunks[-1].content if isinstance(block, TextBlock)] == ["Next turn completed."]
        assert create.await_count == 2
        assert [item for item in create.call_args.kwargs["input"] if item.get("type") == "function_call_output"] == [
            {"type": "function_call_output", "call_id": "call_saved", "output": "saved:q1"}
        ]
        assert following.closed

"""Trade-only transport workaround uses full completions without polluting other calls."""
from copy import deepcopy
from types import SimpleNamespace
import inspect
import json

import pytest
from agentscope.message import Msg, TextBlock, ToolCallBlock
from agentscope.model import ChatResponse

from core.models.chat_models import make_chat_model
from core.llm.foreign_trade_plugin import TRADE_TOOL_NAMES


def tool(name):
    return {"type": "function", "function": {"name": name, "description": "Test tool", "parameters": {
        "type": "object", "properties": {"action": {"type": "string"}}, "required": ["action"]}}}


class FakeStream:
    async def __aenter__(self): return self
    async def __aexit__(self, *args): return False
    def __aiter__(self): return self.events()
    async def events(self):
        yield SimpleNamespace(id="response-stream", usage=None, choices=[SimpleNamespace(
            delta=SimpleNamespace(content="ordinary streamed text", tool_calls=[]), finish_reason=None)])
        yield SimpleNamespace(id="response-stream", usage=None, choices=[SimpleNamespace(
            delta=SimpleNamespace(content="", tool_calls=[]), finish_reason="stop")])


def completion(name="trade_inquiry"):
    return SimpleNamespace(id="response-completion", usage=None, choices=[SimpleNamespace(message=SimpleNamespace(
        content=None, tool_calls=[SimpleNamespace(id="upstream-reused-id", function=SimpleNamespace(
            name=name, arguments='{"action":"create","data":{"title":"完整JSON"}}'))]))])


@pytest.fixture
def model_client(monkeypatch):
    model = make_chat_model(model="offline-dummy", temperature=0.0, max_tokens=1000, timeout=5,
                           base_url="http://example.invalid/v1", api_key="dummy", api_protocol="chat_completions", context_size=4096, stream=True)
    requests, responses = [], []
    async def create(**kwargs):
        requests.append(deepcopy(kwargs))
        if kwargs["stream"]:
            return FakeStream()
        names = [item.get("function", {}).get("name") for item in kwargs.get("tools", [])]
        response = completion(next((name for name in names if name in TRADE_TOOL_NAMES), "other_tool"))
        responses.append(response)
        return response
    monkeypatch.setattr(model, "_build_client", lambda: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    yield model, requests, responses


async def invoke(model, names=None, **kwargs):
    schemas = None if names is None else [tool(name) for name in names]
    # The pinned SDK accumulates wire deltas in ChatModelBase.__call__.
    return await model([Msg(name="user", role="user", content=[TextBlock(text="test")])],
                       tools=schemas, **kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize("name", sorted(TRADE_TOOL_NAMES))
async def test_exact_trade_names_use_completion_parser_and_preserve_model_flag(model_client, name):
    model, requests, _ = model_client
    try:
        result = await invoke(model, [name])
        assert requests[-1]["stream"] is False and "stream_options" not in requests[-1]
        assert isinstance(result, ChatResponse) and result.is_last is True
        assert isinstance(result.content[0], ToolCallBlock)
        assert json.loads(result.content[0].input)["data"]["title"] == "完整JSON"
        assert model.stream is True
    finally:
        await model._http_client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("names", [None, [], ["ordinary_tool"], ["trade_inquiry_extra"], ["mcp__trade_inquiry"],
                                   ["Trade_Inquiry"], ["trade_product_contents"], ["calculate_quote"]])
async def test_other_tool_surfaces_keep_streaming(model_client, names):
    model, requests, _ = model_client
    try:
        result = await invoke(model, names)
        assert requests[-1]["stream"] is True
        assert requests[-1]["stream_options"] == {"include_usage": True}
        assert inspect.isasyncgen(result)
        chunks = [part async for part in result]
        assert chunks[-1].is_last is True and chunks[-1].content[0].text == "ordinary streamed text"
        assert model.stream is True
    finally:
        await model._http_client.aclose()


@pytest.mark.asyncio
async def test_same_model_trade_then_plain_restores_original_stream_per_request(model_client):
    model, requests, _ = model_client
    original_parameters = model.parameters.model_dump()
    try:
        first = await invoke(model, ["trade_inquiry", "ordinary_tool"])
        second = await invoke(model, None)
        chunks = [part async for part in second]
        assert [request["stream"] for request in requests] == [False, True]
        assert isinstance(first, ChatResponse) and chunks[-1].is_last
        assert "stream_options" not in requests[0] and requests[1]["stream_options"]["include_usage"] is True
        assert model.stream is True and model.parameters.model_dump() == original_parameters
    finally:
        await model._http_client.aclose()


@pytest.mark.asyncio
async def test_nonstream_completions_still_namespace_recycled_tool_ids(model_client):
    model, requests, responses = model_client
    try:
        first = await invoke(model, ["trade_calculate_quote"])
        second = await invoke(model, ["trade_calculate_quote"])
        assert isinstance(first, ChatResponse) and isinstance(second, ChatResponse)
        assert first.content[0].id != second.content[0].id
        assert first.content[0].id != "upstream-reused-id"
        assert responses[0].choices[0].message.tool_calls[0].id == "upstream-reused-id"
        assert json.loads(first.content[0].input) == json.loads(second.content[0].input)
        assert [request["stream"] for request in requests] == [False, False]
    finally:
        await model._http_client.aclose()


@pytest.mark.asyncio
async def test_trade_forces_consistent_local_transport_despite_explicit_stream_kwargs(model_client):
    model, requests, _ = model_client
    try:
        result = await invoke(model, ["trade_product_content"], stream=True, stream_options={"include_usage": True})
        assert requests[-1]["stream"] is False and "stream_options" not in requests[-1]
        assert isinstance(result, ChatResponse) and model.stream is True
    finally:
        await model._http_client.aclose()


@pytest.mark.asyncio
async def test_already_nonstream_model_keeps_plain_completion_behavior(model_client):
    model, requests, _ = model_client
    model.stream = False
    try:
        result = await invoke(model, None)
        assert requests[-1]["stream"] is False and isinstance(result, ChatResponse)
        assert model.stream is False
    finally:
        await model._http_client.aclose()

"""Exercise the real SDK Toolkit -> FunctionTool path, before JSON repair can write."""
from types import SimpleNamespace
import json

import pytest
from agentscope.message import TextBlock, ToolCallBlock, ToolResultState
from agentscope.state import AgentState
from agentscope.tool import FunctionTool
from agentscope.tool._response import ToolChunk, ToolResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.db.models import ForeignTradeInquiry
from core.llm.strict_trade_function import StrictTradeToolkit, TRADE_TOOL_NAMES
from core.llm.factory.tools.definitions import ToolAssembly as ToolCollector
from core.llm.tools import foreign_trade_tool as adapter


def text(response):
    return "".join(block.text for block in response.content if hasattr(block, "text"))


async def run(toolkit, name, raw):
    call = ToolCallBlock(id="call-strict-json", name=name, input=raw)
    values = [value async for value in toolkit.call_tool(call, AgentState())]
    assert len(values) >= 2 and isinstance(values[-1], ToolResponse)
    assert values[-1].id == call.id
    assert call.input == raw  # Keep original intent bytes for journaling/permission tickets.
    return values[-1]


BAD_JSON = [
    '{"action":"create","data":{"title":"聊天验收 · LYRECO',
    '{"action":"create","data":{"title":"buyer":"LYRECO","raw_inquiry":"hello"}}',
    '{"action":"get","action":"create","data":{}}',
    '{"action":"create","data":{"title":"first","title":"second"}}',
    '{"action":"create","data":{"nested":{"value":1,"value":2}}}',
    '{"action":"create","data":{"amount":NaN}}',
    '{"action":"create","data":{"amount":Infinity}}',
    '{"action":"create","data":{"amount":-Infinity}}',
    '{"action":"create","data":{"amount":1e999}}',
    '[{"action":"create"}]', 'null', 'true', '42', '"create"',
    '{"action":"create",}', "{'action':'create'}",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("name", sorted(TRADE_TOOL_NAMES))
@pytest.mark.parametrize("raw", BAD_JSON)
async def test_invalid_raw_never_reaches_real_function_tool(name, raw):
    writes = []
    async def write_operation(action: str = "create", data: dict | None = None):
        writes.append((action, data))
        return ToolChunk(content=[TextBlock(text="wrote")])
    toolkit = StrictTradeToolkit(tools=[FunctionTool(write_operation, name=name)])
    result = await run(toolkit, name, raw)
    assert result.state == ToolResultState.ERROR and writes == []
    payload = json.loads(text(result))
    assert payload["executed"] is False and payload["retryable"] is True
    assert payload["errors"][0]["code"] == "invalid_tool_json"
    assert "未执行任何操作" in payload["errors"][0]["message"]
    assert "LYRECO" not in text(result)


@pytest.mark.asyncio
async def test_valid_json_reaches_real_function_tool_exactly_once():
    writes = []
    async def write_operation(action: str, data: dict):
        writes.append((action, data))
        return ToolChunk(content=[TextBlock(text=json.dumps({"ok": True}))])
    toolkit = StrictTradeToolkit(tools=[FunctionTool(write_operation, name="trade_inquiry")])
    result = await run(toolkit, "trade_inquiry", '{"action":"create","data":{"title":"合法标题","value":1.25}}')
    assert result.state == ToolResultState.SUCCESS
    assert writes == [("create", {"title": "合法标题", "value": 1.25})]


@pytest.mark.asyncio
async def test_unrelated_tool_retains_sdk_repair_behavior():
    calls = []
    async def ordinary_tool(action: str):
        calls.append(action)
        return ToolChunk(content=[TextBlock(text="ok")])
    toolkit = StrictTradeToolkit(tools=[FunctionTool(ordinary_tool)])
    result = await run(toolkit, "ordinary_tool", '{"action":"read"')
    assert result.state == ToolResultState.SUCCESS and calls == ["read"]


@pytest.mark.asyncio
async def test_hidden_trade_tool_remains_hidden_with_valid_json():
    calls = []
    async def write_operation(action: str):
        calls.append(action)
        return ToolChunk(content=[TextBlock(text="wrong")])
    toolkit = StrictTradeToolkit(tools=[FunctionTool(write_operation, name="trade_inquiry")], hidden_tools={"trade_inquiry"})
    result = await run(toolkit, "trade_inquiry", '{"action":"create"}')
    assert result.state == ToolResultState.ERROR and calls == []
    schemas = await toolkit.get_tool_schemas()
    assert not any(schema.get("function", {}).get("name") == "trade_inquiry" for schema in schemas)


@pytest.mark.asyncio
async def test_inherited_permission_ticket_check_is_preserved():
    calls = []
    async def write_operation(action: str):
        calls.append(action)
        return ToolChunk(content=[TextBlock(text="wrong")])
    toolkit = StrictTradeToolkit(tools=[FunctionTool(write_operation, name="trade_inquiry")])
    toolkit.set_tool_permission_service(SimpleNamespace(registry=SimpleNamespace(contains=lambda name: True)))
    result = await run(toolkit, "trade_inquiry", '{"action":"create"}')
    assert result.state == ToolResultState.ERROR and calls == []
    assert "PermissionEnforcementError" in text(result)


@pytest.mark.asyncio
async def test_real_native_creation_is_not_repaired_into_empty_or_corrupt_records(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    ForeignTradeInquiry.__table__.create(bind=engine)
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(adapter, "SessionLocal", sessions)
    monkeypatch.setattr(adapter, "_assert_available", lambda *args: None)
    collector = ToolCollector()
    adapter.register_foreign_trade_tools(collector, user_id="alice", chat_id="chat", install_id="trade@alice")
    toolkit = StrictTradeToolkit(tools=collector)
    for raw in BAD_JSON[:5]:
        result = await run(toolkit, "trade_inquiry", raw)
        assert result.state == ToolResultState.ERROR
    with sessions() as db:
        assert db.query(ForeignTradeInquiry).count() == 0
    result = await run(toolkit, "trade_inquiry", json.dumps({"action": "create", "data": {
        "title": "A valid inquiry", "buyer": {"company_name": "Lyreco"}, "raw_inquiry": "Please send product facts"}}))
    assert json.loads(text(result))["ok"] is True
    with sessions() as db:
        rows = db.query(ForeignTradeInquiry).all()
        assert len(rows) == 1 and rows[0].payload["title"] == "A valid inquiry"
        assert rows[0].payload["buyer"]["company_name"] == "Lyreco"
    engine.dispose()

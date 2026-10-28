"""Real MCP 2.x HTTP acceptance using only this checkout's synthetic catalog."""
from contextlib import asynccontextmanager
import asyncio
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time

import httpx
import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = {"search_products", "get_product", "calculate_quote"}


@pytest.fixture(scope="module")
def trade_mcp_url(tmp_path_factory):
    """Start the production MCP object in a disposable subprocess, never port 9120."""
    directory = tmp_path_factory.mktemp("trade-mcp-protocol")
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    assert port not in {3001, 9120}
    env = os.environ.copy()
    env.update({
        "PYTHONPATH": os.pathsep.join((str(ROOT / "extensions"), str(ROOT / "src/backend"))),
        "HUGAGENT_SKIP_ENV_FILES": "1",
        "HUGAGENT_HOME": str(directory / "home"),
        "HUGAGENT_CAPS_ROOT": str(directory / "caps"),
        "DATABASE_URL": "sqlite:///" + str(directory / "unused.db"),
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    # Exercise the real MCPServer.run options used by mcp_server.__main__.
    script = (
        "import sys; from foreign_trade.mcp_server import mcp; "
        "mcp.run(transport='streamable-http', host='127.0.0.1', port=int(sys.argv[1]), "
        "stateless_http=True, json_response=True)"
    )
    log_path = directory / "server.log"
    with log_path.open("w+b") as log:
        process = subprocess.Popen(
            [sys.executable, "-c", script, str(port)], cwd=ROOT, env=env,
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 15
            ready = False
            with httpx.Client(trust_env=False, timeout=0.5) as client:
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        pytest.fail("MCP server exited during startup: " +
                                    log_path.read_text(errors="replace")[-4000:])
                    try:
                        health = client.get(f"http://127.0.0.1:{port}/health")
                        if health.status_code == 200:
                            body = health.json()
                            assert body["service"] == "foreign-trade-demo"
                            assert body["ok"] is True and body["is_simulated"] is True
                            ready = True
                            break
                    except httpx.TransportError:
                        pass
                    time.sleep(0.05)
            assert ready, "Disposable MCP server did not become ready: " + log_path.read_text(errors="replace")[-4000:]
            yield f"http://127.0.0.1:{port}/mcp"
        finally:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            assert process.poll() is not None, "Disposable MCP subprocess was not reaped"


@asynccontextmanager
async def protocol_session(url):
    async with asyncio.timeout(20), httpx2.AsyncClient(timeout=10, trust_env=False) as client:
        # MCP 2.x yields two streams and exposes snake_case result fields.
        async with streamable_http_client(url, http_client=client) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                yield session


async def call_data(session, name, arguments):
    result = await session.call_tool(name, arguments)
    assert result.is_error is False, result
    if result.structured_content is not None:
        value = result.structured_content
    else:
        value = json.loads(next(block.text for block in result.content if block.type == "text"))
    assert isinstance(value, dict)
    return value


@pytest.mark.asyncio
async def test_real_http_catalog_tools_and_product_queries(trade_mcp_url):
    async with protocol_session(trade_mcp_url) as session:
        listed = await session.list_tools()
        assert {tool.name for tool in listed.tools} == TOOLS
        assert len(listed.tools) == 3
        search = await call_data(session, "search_products", {"query": "DESK-001", "limit": 5})
        assert search["ok"] is True and search["is_simulated"] is True
        assert [product["sku"] for product in search["data"]["products"]] == ["DESK-001"]
        product = await call_data(session, "get_product", {"sku": "DESK-001"})
        assert product["ok"] is True and product["data"]["moq"] == 100
        assert product["data"]["packaging"]["custom"]["unit_surcharge"] == "0.30"
        assert product["source"]["record_refs"]


@pytest.mark.asyncio
async def test_real_http_quotes_keep_exact_amounts_and_demo_boundaries(trade_mcp_url):
    async with protocol_session(trade_mcp_url) as session:
        identifiers = set()
        for quantity, custom, amount in [(500, False, "2400.00"), (2000, False, "8400.00"), (1000, True, "5100.00")]:
            request = {
                "items": [{"sku": "DESK-001", "quantity": quantity, "custom_packaging": custom}],
                "destination_country": "Spain",
            }
            quote = await call_data(session, "calculate_quote", request)
            assert quote["ok"] is True and quote["is_simulated"] is True
            data = quote["data"]
            assert data["subtotal"] == amount and data["currency"] == "USD"
            assert data["document_type"] == "foreign_trade_quote" and data["document_version"] == 1
            assert re.fullmatch(r"DEMO-[A-F0-9]{16}", data["quote_id"])
            assert data["freight"]["amount"] is None and data["subtotal_excludes_freight"] is True
            assert quote["source"]["record_refs"]
            repeated = await call_data(session, "calculate_quote", request)
            assert repeated["data"]["quote_id"] == data["quote_id"]
            identifiers.add(data["quote_id"])
        assert len(identifiers) == 3


@pytest.mark.asyncio
async def test_real_http_rejects_strict_and_business_invalid_arguments(trade_mcp_url):
    async with protocol_session(trade_mcp_url) as session:
        # The transport must not coerce boolean, fractional or string integers.
        for value in (True, 1.5, "5"):
            for name, arguments in [
                ("search_products", {"limit": value}),
                ("calculate_quote", {"items": [{"sku": "DESK-001", "quantity": 500}],
                                     "requested_lead_days": value}),
            ]:
                result = await session.call_tool(name, arguments)
                assert result.is_error is True, (name, value, result)
                assert result.structured_content is None
        for item in [
            {"sku": "DESK-001", "quantity": 99},
            {"sku": "DESK-001", "quantity": True},
            {"sku": "DESK-001", "quantity": 500.0},
            {"sku": "DESK-001", "quantity": "500"},
            {"sku": "UNKNOWN", "quantity": 500},
            {"sku": "DESK-001", "quantity": 500, "discount": 0.5},
            {"sku": "DESK-001", "quantity": 500, "custom_packaging": "false"},
        ]:
            invalid = await call_data(session, "calculate_quote", {"items": [item]})
            assert invalid["ok"] is False and invalid["data"] is None
            assert invalid["errors"] and "quote_id" not in invalid and "document_type" not in invalid

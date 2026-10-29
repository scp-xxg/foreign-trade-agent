"""Model-independent end-to-end contract through real SDK dispatch and business services.

All state lives in isolated SQLite/in-memory artifact storage. The fixture models
an already-authorized plugin installation; product generation mocks only the
translation provider, never the generator, quote engine, file parser or exporter.
"""
import csv
from io import BytesIO, StringIO
import json
from uuid import uuid4
from unittest.mock import AsyncMock
import zipfile

import pytest
from PIL import Image
from agentscope.message import ToolCallBlock
from agentscope.state import AgentState
from agentscope.tool._response import ToolResponse

from core.db.models import ForeignTradeInquiry
from core.llm.strict_trade_function import StrictTradeToolkit
from core.llm.factory.tools.definitions import ToolAssembly, function_tool
from core.foreign_trade.tool_names import TRADE_TOOL_NAMES
from core.foreign_trade.content import ContentPackError, ContentPackService
from core.foreign_trade import content_generation as generation
from test_trade_plugin_tools import ctx, add_file


@pytest.fixture
def dispatched(ctx):
    functions, sessions, storage = ctx
    collector = ToolAssembly()
    for function in functions.values():
        collector.append(function_tool(function))
    assert len(collector) == len(TRADE_TOOL_NAMES)
    toolkit = StrictTradeToolkit(tools=collector)
    state = AgentState()
    calls = []
    async def call(name, **kwargs):
        block = ToolCallBlock(id="call_e2e_" + uuid4().hex, name=name,
                              input=json.dumps(kwargs, ensure_ascii=False))
        results = [result async for result in toolkit.call_tool(block, state)]
        assert isinstance(results[-1], ToolResponse) and results[-1].id == block.id
        calls.append(name)
        payload = "".join(item.text for item in results[-1].content if hasattr(item, "text"))
        return json.loads(payload)
    return call, sessions, storage, calls


@pytest.mark.asyncio
async def test_chat_inquiry_complete_revision_and_followup_lifecycle(dispatched):
    call, sessions, _, calls = dispatched
    saved = await call("trade_save_inquiry", title="Integration inquiry", company_name="Test buyer",
        website="https://example.com", raw_inquiry="DESK-001, 500 units, standard packaging, Spain",
        sku="DESK-001", quantity=500, custom_packaging=False, destination_country="Spain")
    assert saved["ok"] is True
    record = saved["data"]
    assert record["workflow_status"]["quote_present"] is False
    quoted = await call("trade_calculate_quote", inquiry_id=record["id"], revision=record["revision"])
    assert quoted["ok"] is True and quoted["data"]["subtotal"] == "2400.00"
    initial_quote_id = quoted["data"]["quote_id"]
    draft = await call("trade_inquiry", action="draft", inquiry_id=quoted["inquiry_id"], revision=quoted["revision"])
    record = draft["data"]
    assert record["drafts"]["not_sent"] is True and "USD 2400.00" in record["drafts"]["en"]
    followed = await call("trade_inquiry", action="add_followup", inquiry_id=record["id"], revision=record["revision"],
        data={"title": "Review customer reply", "due_at": "2026-10-24T09:00:00+08:00", "timezone": "Asia/Shanghai"})
    record = followed["data"]
    assert record["followups"][0]["due_at"] == "2026-10-24T01:00:00+00:00"
    assert record["workflow_status"]["pending_followups"] == 1

    changed = await call("trade_save_inquiry", inquiry_id=record["id"], revision=record["revision"],
                         quantity=1000, custom_packaging=True)
    record = changed["data"]
    assert record["quote"] is None and record["drafts"]["stale"] is True
    assert record["workflow_status"]["drafts_present"] is False
    assert any(event["event"] == "quote_superseded" for event in record["history"])
    repriced = await call("trade_calculate_quote", inquiry_id=record["id"], revision=record["revision"])
    assert repriced["ok"] is True
    assert repriced["data"]["merchandise_subtotal"] == "4800.00"
    assert repriced["data"]["packaging_subtotal"] == "300.00"
    assert repriced["data"]["subtotal"] == "5100.00"
    assert repriced["data"]["quote_id"] != initial_quote_id
    assert repriced["data"]["production_lead_days"] == 18
    renewed = await call("trade_inquiry", action="draft", inquiry_id=repriced["inquiry_id"], revision=repriced["revision"])
    record = renewed["data"]
    assert "USD 5100.00" in record["drafts"]["zh"] and "USD 5100.00" in record["drafts"]["en"]
    assert record["drafts"]["stale"] is False and record["drafts"]["quote_revision"] == record["quote_revision"]
    replied = await call("trade_inquiry", action="mark_replied", inquiry_id=record["id"], revision=record["revision"])
    record = replied["data"]
    assert record["replied_at"] is not None
    assert record["followups"][0]["status"] == "cancelled"
    assert record["followups"][0]["cancellation_reason"] == "buyer_replied"
    assert record["workflow_status"]["pending_followups"] == 0
    blocked = await call("trade_inquiry", action="add_followup", inquiry_id=record["id"], revision=record["revision"],
        data={"title": "Should be blocked", "due_at": "2026-10-25T09:00:00+08:00", "timezone": "Asia/Shanghai"})
    assert blocked["ok"] is False and blocked["status"] == 409
    with sessions() as db:
        rows = db.query(ForeignTradeInquiry).all()
        assert len(rows) == 1 and rows[0].owner_user_id == "alice"
        assert rows[0].payload["quote"]["data"]["subtotal"] == "5100.00"
    assert set(calls) == {"trade_save_inquiry", "trade_calculate_quote", "trade_inquiry"}


@pytest.mark.asyncio
async def test_chat_product_import_confirm_generate_real_exports_and_access(dispatched, monkeypatch):
    call, sessions, _, calls = dispatched
    facts_file = add_file(sessions, name="facts.csv", data=(
        "label,value,source_url\nProcessor,2.4 GHz CPU,https://example.com/product\n"
        "USB ports,2 USB 3.0,https://example.com/product\n").encode())
    photo_stream = BytesIO()
    Image.new("RGB", (120, 80), "#267b52").save(photo_stream, format="PNG")
    photo_file = add_file(sessions, name="original-photo.png", data=photo_stream.getvalue())
    imported = await call("trade_import_product", file_ids=[facts_file, photo_file], title="Content integration",
        product_name="Test Board", brand="Test", model="T-1", source_url="https://example.com/product",
        image_credit="Original test illustration created for this integration test; authorized for test use.")
    assert imported["ok"] is True
    record = imported["data"]
    assert len(record["documents"]) == 2 and len(record["suggested_facts"]) == 2
    assert record["facts"] == [] and record["outputs"] is None
    candidates = record["suggested_facts"]

    async def translate_only(facts):
        return {"facts": [{"index": index + 1, "label": fact["label"], "value": fact["value"]}
                           for index, fact in enumerate(facts)]}
    translator = AsyncMock(side_effect=translate_only)
    monkeypatch.setattr(generation, "_translate", translator)
    premature = await call("trade_product_content", action="generate", pack_id=record["pack_id"],
                           revision=record["revision"], confirmed=True)
    assert premature["ok"] is False and premature["status"] == 422
    translator.assert_not_awaited()
    confirmed = await call("trade_confirm_product_facts", pack_id=record["pack_id"], revision=record["revision"],
                           confirmed=True, fact_indices=[2, 1])
    record = confirmed["data"]
    assert record["facts"] == [candidates[1], candidates[0]] and record["outputs"] is None
    assert record["facts_confirmation"]["generated"] is False
    generated = await call("trade_product_content", action="generate", pack_id=record["pack_id"],
                           revision=record["revision"], confirmed=True)
    assert generated["ok"] is True
    receipt = generated["data"]
    assert receipt["document_type"] == "foreign_trade_content_pack" and receipt["not_published"] is True
    assert {asset["kind"] for asset in receipt["assets"]} == {"square", "landscape", "spec"}
    translator.assert_awaited_once()
    assert translator.await_args.args[0] == record["facts"]

    with sessions() as db:
        service = ContentPackService(db)
        zip_data, zip_mime, zip_name = service.download("alice", receipt["pack_id"], "zip", receipt["revision"])
        png_data, png_mime, _ = service.download("alice", receipt["pack_id"], "square", receipt["revision"])
        faq_data, faq_mime, _ = service.download("alice", receipt["pack_id"], "faq", receipt["revision"])
        assert zip_mime == "application/zip" and zip_name.endswith(".zip")
        assert png_mime == "image/png" and faq_mime.startswith("text/csv")
        with zipfile.ZipFile(BytesIO(zip_data)) as archive:
            assert {"english-listing.md", "customer-faq.csv", "facts.json", "provenance.txt", "uploaded-sources.json",
                    "product-square.png", "product-landscape.png", "product-spec.png"} <= set(archive.namelist())
            saved_facts = json.loads(archive.read("facts.json"))
            assert saved_facts["facts"] == [candidates[1], candidates[0]]
            assert saved_facts["revision"] == receipt["revision"]
            assert archive.read("customer-faq.csv") == faq_data
            assert archive.read("product-square.png") == png_data
            listing = archive.read("english-listing.md").decode()
            assert "2.4 GHz CPU" in listing and "2 USB 3.0" in listing and "Powered by HugAgentOS" in listing
            assert "https://example.com/product" in listing and "DRAFT" in listing
            provenance = archive.read("provenance.txt").decode()
            assert "Original test illustration" in provenance and "not a quotation" in provenance
            original_sources = json.loads(archive.read("uploaded-sources.json"))
            assert len(original_sources) == 2 and all(source["sha256"] for source in original_sources)
            for kind, expected_size in [("square", (1200,1200)), ("landscape", (1600,900)), ("spec", (1200,1600))]:
                with Image.open(BytesIO(archive.read(f"product-{kind}.png"))) as image:
                    image.load()
                    assert image.size == expected_size and image.format == "PNG"
                    assert image.info["Attribution"] == record["image_credit"]
                    assert image.info["Source"] == "https://example.com/product"
        faq = list(csv.DictReader(StringIO(faq_data.decode("utf-8-sig"))))
        assert faq[0]["Answer"] == "2 USB 3.0" and faq[0]["Source fact numbers"] == "1"
        assert faq[1]["Answer"] == "2.4 GHz CPU" and faq[1]["Source fact numbers"] == "2"
        assert all("Draft" in item["Status"] for item in faq)
        with pytest.raises(ContentPackError) as denied:
            service.download("bob", receipt["pack_id"], "zip", receipt["revision"])
        assert denied.value.status == 404
        with pytest.raises(ContentPackError) as stale:
            service.download("alice", receipt["pack_id"], "zip", receipt["revision"] - 1)
        assert stale.value.status == 409

    changed = await call("trade_product_content", action="update", pack_id=receipt["pack_id"], revision=receipt["revision"],
                         data={"product_name": "Changed product name"})
    assert changed["ok"] is True and changed["data"]["outputs"] is None
    with sessions() as db:
        with pytest.raises(ContentPackError) as stale:
            ContentPackService(db).download("alice", receipt["pack_id"], "zip")
        assert stale.value.status == 409
    assert set(calls) == {"trade_import_product", "trade_confirm_product_facts", "trade_product_content"}

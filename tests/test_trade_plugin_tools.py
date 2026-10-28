"""Chat plugin adapters exercise real services with captured identity and isolated storage."""
from copy import deepcopy
from io import BytesIO
import inspect
import json
from unittest.mock import AsyncMock

import pytest
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from core.db.models import Artifact, ChatMessage, ChatSession, ForeignTradeInquiry, ForeignTradeContentPack, ForeignTradeCollaboration, UserFolder, UserShadow
from core.llm.tools import foreign_trade_tool as adapter
from core.foreign_trade import content as content
from core.foreign_trade import content_generation as generation
from core.files.artifacts.service import store_bytes_as_artifact


class Collector(list):
    def __init__(self): super().__init__(); self.tools = {}
    def append(self, tool):
        super().append(tool)
        self.tools[tool.name] = tool._func


class Storage:
    def __init__(self): self.files = {}
    def upload_bytes(self, data, key): self.files[key] = data; return "memory:" + key
    def download_bytes(self, key): return self.files[key]
    def delete(self, key): self.files.pop(key, None)


def read(response):
    first = response.content[0]
    return json.loads(first["text"] if isinstance(first, dict) else first.text)


@pytest.fixture
def ctx(monkeypatch):
    import core.files.storage
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    for cls in [ChatSession, ChatMessage, Artifact, ForeignTradeInquiry, ForeignTradeContentPack, ForeignTradeCollaboration, UserFolder, UserShadow]:
        cls.__table__.create(bind=engine)
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(adapter, "SessionLocal", sessions)
    monkeypatch.setattr(adapter, "_assert_available", lambda user, install: None)
    storage = Storage()
    for module in (adapter, content, core.files.storage): monkeypatch.setattr(module, "get_storage", lambda: storage)
    with sessions() as db:
        db.add_all([ChatSession(chat_id="alice-chat", user_id="alice"), ChatSession(chat_id="bob-chat", user_id="bob")])
        db.commit()
    collector = Collector()
    adapter.register_foreign_trade_tools(collector, user_id="alice", chat_id="alice-chat", install_id="trade@alice")
    yield collector.tools, sessions, storage
    engine.dispose()


def inquiry_data(**extra):
    return {"title": "Chat inquiry", "raw_inquiry": "DESK-001 500 units standard packaging to Spain",
            "items": [{"sku": "DESK-001", "quantity": 500, "custom_packaging": False}],
            "destination_country": "Spain", **extra}


async def new_inquiry(tools):
    return read(await tools["trade_inquiry"]("create", data=inquiry_data()))["data"]


async def new_pack(tools):
    return read(await tools["trade_product_content"]("create", data={"title": "Test pack"}))["data"]


def add_file(sessions, *, owner="alice", chat="alice-chat", name="facts.csv", data=None):
    with sessions() as db:
        artifact = store_bytes_as_artifact(db, user_id=owner, chat_id=chat, filename=name,
                                          content=data or b"label,value,source_url\nProcessor,2.4 GHz CPU,https://example.com\n")
        return artifact.artifact_id


def test_only_registered_trade_tools_and_no_identity_arguments(ctx):
    tools, _, _ = ctx
    from core.llm.foreign_trade_plugin import TRADE_TOOL_NAMES
    assert set(tools) == TRADE_TOOL_NAMES
    for function in tools.values():
        params = inspect.signature(function).parameters
        assert not {"user_id", "chat_id", "install_id", "headers", "token", "api_key"}.intersection(params)
    empty = Collector()
    assert adapter.register_foreign_trade_tools(empty, user_id="", chat_id=None, install_id="x") == []
    assert empty.tools == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["user_id", "owner_user_id", "chat_id", "headers", "api_key"])
async def test_identity_forgery_in_data_is_rejected(ctx, field):
    tools, _, _ = ctx
    result = read(await tools["trade_inquiry"]("create", data=inquiry_data(**{field: "victim-secret-value"})))
    assert result["ok"] is False and result["status"] == 422
    assert "victim-secret-value" not in json.dumps(result)
    result = read(await tools["trade_product_content"]("create", data={"title": "bad", field: "victim-secret-value"}))
    assert result["ok"] is False and result["status"] == 422


@pytest.mark.asyncio
async def test_plugin_revocation_checked_each_call(ctx, monkeypatch):
    tools, _, _ = ctx
    item = await new_inquiry(tools)
    def revoked(*args): raise PermissionError("internal installation detail")
    monkeypatch.setattr(adapter, "_assert_available", revoked)
    for call in [tools["trade_inquiry"]("get", inquiry_id=item["id"]),
                 tools["trade_calculate_quote"](item["id"], item["revision"]),
                 tools["trade_product_content"]("list")]:
        result = read(await call)
        assert result["status"] == 403 and "internal installation detail" not in str(result)


@pytest.mark.asyncio
async def test_owner_and_revision_are_enforced_by_real_services(ctx):
    tools, sessions, _ = ctx
    item = await new_inquiry(tools)
    with sessions() as db:
        row = db.query(ForeignTradeInquiry).first()
        assert row.owner_user_id == "alice"
        row.owner_user_id = "bob"; db.commit()
    assert read(await tools["trade_inquiry"]("get", inquiry_id=item["id"]))["status"] == 404
    assert read(await tools["trade_calculate_quote"](item["id"], 1))["status"] == 404
    item = await new_inquiry(tools)
    updated = read(await tools["trade_inquiry"]("update", inquiry_id=item["id"], revision=1, data={"title": "new"}))
    assert updated["data"]["revision"] == 2
    assert read(await tools["trade_calculate_quote"](item["id"], 1))["status"] == 409


@pytest.mark.asyncio
async def test_quote_receipt_reuses_exact_engine_envelope(ctx):
    tools, _, _ = ctx
    item = await new_inquiry(tools)
    result = read(await tools["trade_calculate_quote"](item["id"], 1))
    assert result["ok"] is True and result["is_simulated"] is True
    assert result["data"]["document_type"] == "foreign_trade_quote"
    assert result["data"]["subtotal"] == "2400.00"
    assert result["inquiry_id"] == item["id"] and result["revision"] == 2
    assert "quote" not in result["data"]
    draft = read(await tools["trade_inquiry"]("draft", inquiry_id=item["id"], revision=2))
    assert "USD 2400.00" in draft["data"]["drafts"]["en"]
    assert draft["data"]["drafts"]["not_sent"] is True


@pytest.mark.asyncio
async def test_moq_rejection_and_missing_packaging_not_defaulted(ctx):
    tools, _, _ = ctx
    result = read(await tools["trade_inquiry"]("create", data=inquiry_data(items=[{"sku": "DESK-001", "quantity": 500}])))
    assert result["status"] == 422
    item = read(await tools["trade_inquiry"]("create", data=inquiry_data(items=[{"sku": "DESK-001", "quantity": 1, "custom_packaging": False}])))["data"]
    result = read(await tools["trade_calculate_quote"](item["id"], 1))
    assert result["status"] == 422 and result["ok"] is False


@pytest.mark.asyncio
async def test_followup_flow_uses_latest_revision_and_reply_stops_tasks(ctx):
    tools, _, _ = ctx
    item = await new_inquiry(tools)
    item = read(await tools["trade_inquiry"]("add_followup", inquiry_id=item["id"], revision=item["revision"],
        data={"title": "Follow up", "due_at": "2026-10-24T09:00:00+08:00", "timezone": "Asia/Shanghai"}))["data"]
    assert item["followups"][0]["due_at"] == "2026-10-24T01:00:00+00:00"
    item = read(await tools["trade_inquiry"]("mark_replied", inquiry_id=item["id"], revision=item["revision"]))["data"]
    assert item["followups"][0]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_current_chat_file_import_keeps_facts_unconfirmed(ctx):
    tools, sessions, _ = ctx
    file_id = add_file(sessions)
    pack = await new_pack(tools)
    result = read(await tools["trade_product_content"]("import_files", pack_id=pack["pack_id"], revision=1, file_ids=[file_id]))
    assert result["ok"] is True
    pack = result["data"]
    assert pack["facts"] == [] and pack["suggested_facts"][0]["value"] == "2.4 GHz CPU"
    assert "text" not in pack["documents"][0] and "sha256" not in pack["documents"][0]


@pytest.mark.asyncio
@pytest.mark.parametrize("owner,chat", [("bob", "bob-chat"), ("alice", None)])
async def test_other_owner_and_unreferenced_files_rejected(ctx, owner, chat):
    tools, sessions, _ = ctx
    file_id = add_file(sessions, owner=owner, chat=chat)
    pack = await new_pack(tools)
    result = read(await tools["trade_product_content"]("import_files", pack_id=pack["pack_id"], revision=1, file_ids=[file_id]))
    assert result["status"] == 404
    with sessions() as db: assert db.query(ForeignTradeContentPack).first().payload["documents"] == []


@pytest.mark.asyncio
async def test_explicit_current_chat_reference_allows_own_myspace_file(ctx):
    tools, sessions, _ = ctx
    file_id = add_file(sessions, chat=None)
    with sessions() as db:
        db.add(ChatMessage(message_id="ref", chat_id="alice-chat", chat_seq=1, role="user", content="Use attached file",
                           extra_data={"attachments": [{"file_id": file_id}]})); db.commit()
    pack = await new_pack(tools)
    result = read(await tools["trade_product_content"]("import_files", pack_id=pack["pack_id"], revision=1, file_ids=[file_id]))
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_files_reject_path_url_and_preflight_all_before_writes(ctx):
    tools, sessions, _ = ctx
    good = add_file(sessions)
    bad = add_file(sessions, name="evil.svg", data=b"<svg/>")
    pack = await new_pack(tools)
    for ids in [["/etc/passwd"], ["https://example.com/file.csv"], [good, bad], [good, good]]:
        result = read(await tools["trade_product_content"]("import_files", pack_id=pack["pack_id"], revision=1, file_ids=ids))
        assert result["ok"] is False
    with sessions() as db: assert db.query(ForeignTradeContentPack).first().payload["documents"] == []


@pytest.mark.asyncio
async def test_demo_load_imports_real_files_but_does_not_confirm_facts(ctx):
    tools, _, _ = ctx
    result = read(await tools["trade_product_content"]("load_demo"))
    assert result["ok"] is True
    pack = result["data"]
    assert pack["product_name"] == "Raspberry Pi 5"
    assert len(pack["suggested_facts"]) == 8 and pack["facts"] == []
    assert len(pack["documents"]) == 2 and pack["outputs"] is None
    assert "CC BY 4.0" in pack["image_credit"]
    again = read(await tools["trade_product_content"]("load_demo", pack_id=pack["pack_id"], revision=pack["revision"]))
    assert again["status"] == 409
    generated = read(await tools["trade_product_content"]("generate", pack_id=pack["pack_id"], revision=pack["revision"], confirmed=True))
    assert generated["status"] == 422


@pytest.mark.asyncio
async def test_content_generate_confirmation_receipt_and_stale_outputs(ctx, monkeypatch):
    tools, _, _ = ctx
    pack = await new_pack(tools)
    pack = read(await tools["trade_product_content"]("update", pack_id=pack["pack_id"], revision=1,
        data={"product_name": "Board", "facts": [{"label": "Processor", "value": "2.4 GHz CPU", "source_url": "https://example.com"}]}))["data"]
    call = AsyncMock(return_value={"listing": {"title": "Board", "bullets": ["2.4 GHz CPU"], "description": "Specs"},
        "faq": [], "translated_facts": [], "method": "ai_grounded", "warnings": [], "assets": [],
        "generated_at": "2026-10-21T01:00:00Z", "not_published": True})
    monkeypatch.setattr(generation, "generate_pack", call)
    assert read(await tools["trade_product_content"]("generate", pack_id=pack["pack_id"], revision=2, confirmed=False))["status"] == 422
    call.assert_not_awaited()
    receipt = read(await tools["trade_product_content"]("generate", pack_id=pack["pack_id"], revision=2, confirmed=True))
    assert receipt["data"]["document_type"] == "foreign_trade_content_pack"
    assert receipt["data"]["document_version"] == 1 and receipt["data"]["revision"] == 3
    assert receipt["data"]["not_published"] is True
    got = read(await tools["trade_product_content"]("get", pack_id=pack["pack_id"]))
    assert got["data"]["document_type"] == "foreign_trade_content_pack"
    changed = read(await tools["trade_product_content"]("update", pack_id=pack["pack_id"], revision=3, data={"title": "New title"}))
    assert "document_type" not in changed["data"] and changed["data"]["outputs"] is None


@pytest.mark.asyncio
async def test_native_explicit_template_mode_and_strict_generate_data(ctx, monkeypatch):
    tools, _, _ = ctx
    model = AsyncMock(side_effect=AssertionError("Offline template must not call a model"))
    monkeypatch.setattr(generation, "_translate", model)
    pack = await new_pack(tools)
    pack = read(await tools["trade_product_content"]("update", pack_id=pack["pack_id"], revision=1,
        data={"product_name": "Board", "facts": [{"label": "USB", "value": "2 USB 3.0 ports", "source_url": ""}]}))["data"]
    for invalid in ({"generation_mode": "unknown"}, {"generation_mode": "template", "confirmed": True},
                    {"generation_mode": "template", "revision": 2}, {"generation_mode": "template", "user_id": "bob"}):
        result = read(await tools["trade_product_content"]("generate", pack_id=pack["pack_id"], revision=2,
                                                          confirmed=True, data=invalid))
        assert result["status"] == 422
    result = read(await tools["trade_product_content"]("generate", pack_id=pack["pack_id"], revision=2,
                                                      confirmed=True, data={"generation_mode": "template"}))
    assert result["ok"] and result["data"]["method"] == "template"
    assert result["data"]["generation_mode"] == "template"
    assert result["warnings"][0] == generation.LOCAL_TEMPLATE_NOTICE
    model.assert_not_awaited()


@pytest.mark.asyncio
async def test_internal_errors_do_not_expose_exception_details(ctx, monkeypatch):
    tools, _, _ = ctx
    def fail(*args): raise RuntimeError("SQL credential private-provider-endpoint")
    monkeypatch.setattr(adapter, "SessionLocal", fail)
    result = read(await tools["trade_inquiry"]("list"))
    assert result["status"] == 500
    assert "credential" not in str(result) and "SQL" not in str(result)


@pytest.mark.asyncio
async def test_user_identity_is_not_an_accepted_top_level_argument(ctx):
    tools, _, _ = ctx
    with pytest.raises(TypeError):
        await tools["trade_inquiry"]("list", user_id="bob")


def test_real_tool_collector_exports_valid_identity_free_schemas():
    from core.llm.factory.tools.definitions import ToolAssembly
    from core.foreign_trade.tool_names import TRADE_TOOL_NAMES
    collector = ToolAssembly()
    names = adapter.register_foreign_trade_tools(collector, user_id="alice", chat_id="alice-chat", install_id="trade@alice")
    assert len(collector) == len(TRADE_TOOL_NAMES)
    for name in names:
        schema = next(tool for tool in collector if tool.name == name).input_schema
        assert schema["type"] == "object"
        assert not {"user_id", "chat_id", "install_id", "headers", "api_key"}.intersection(schema["properties"])


@pytest.mark.asyncio
async def test_partial_import_returns_receipt_and_retry_deduplicates(ctx, monkeypatch):
    tools, sessions, _ = ctx
    first = add_file(sessions, name="one.csv", data=b"label,value\nProcessor,2.4 GHz CPU\n")
    second = add_file(sessions, name="two.csv", data=b"label,value\nPort,USB 3.0\n")
    pack = await new_pack(tools)
    original = content.ContentPackService.upload
    count = 0
    def fail_second(self, *args):
        nonlocal count
        count += 1
        if count == 2: raise content.ContentPackError(409, "changed during import")
        return original(self, *args)
    monkeypatch.setattr(content.ContentPackService, "upload", fail_second)
    result = read(await tools["trade_product_content"]("import_files", pack_id=pack["pack_id"], revision=1, file_ids=[first, second]))
    assert result["ok"] is False and result["status"] == 409
    assert result["data"]["imported_source_file_ids"] == [first]
    assert len(result["data"]["imported_file_ids"]) == 1
    assert result["data"]["revision"] == 2
    assert any(item["code"] == "check_partial_import" for item in result["errors"])
    monkeypatch.setattr(content.ContentPackService, "upload", original)
    retried = read(await tools["trade_product_content"]("import_files", pack_id=pack["pack_id"], revision=2, file_ids=[first, second]))
    assert retried["ok"] is True and len(retried["data"]["documents"]) == 2
    assert retried["data"]["import_summary"]["skipped_source_file_ids"] == [first]
    assert retried["data"]["import_summary"]["imported_source_file_ids"] == [second]


@pytest.mark.asyncio
async def test_followup_list_exposes_count_and_truncation_without_fake_links(ctx):
    tools, sessions, _ = ctx
    item = await new_inquiry(tools)
    with sessions() as db:
        from core.foreign_trade.inquiry import InquiryService
        service = InquiryService(db)
        for index in range(25):
            item = service.create_followup("alice", item["id"], item["revision"], f"Follow {index}", "2026-10-24T09:00:00Z", "UTC")
    result = read(await tools["trade_inquiry"]("list"))["data"][0]
    assert len(result["pending_followups"]) == 20
    assert result["pending_followups_total"] == 25 and result["pending_followups_truncated"] is True
    assert set(result["pending_followups"][0]) == {"id", "title", "due_at", "timezone", "is_due"}
    fetched = read(await tools["trade_inquiry"]("get", inquiry_id=item["id"]))["data"]
    assert "workbench_url" not in fetched and fetched["auxiliary_view"] == "询盘工作台"


@pytest.mark.asyncio
async def test_required_skill_gate_precedes_any_business_write(ctx):
    _, sessions, _ = ctx
    from core.llm.foreign_trade_plugin import TradeSkillRequired
    loaded = set()
    def require_skill(name):
        if name not in loaded:
            raise TradeSkillRequired('先用 view_text_file(file_path="/workspace/skills/' + name + '/SKILL.md") 读取技能；未执行。')
    collector = Collector()
    adapter.register_foreign_trade_tools(collector, user_id="alice", chat_id="alice-chat", install_id="trade@alice", require_skill=require_skill)
    for call in [collector.tools["trade_inquiry"]("create", data=inquiry_data()),
                 collector.tools["trade_calculate_quote"]("missing", 1),
                 collector.tools["trade_product_content"]("create", data={"title": "blocked"})]:
        result = read(await call)
        assert result["status"] == 409 and result["errors"][0]["code"] == "skill_not_loaded"
        assert "view_text_file" in result["errors"][0]["message"]
    with sessions() as db:
        assert db.query(ForeignTradeInquiry).count() == 0
        assert db.query(ForeignTradeContentPack).count() == 0
    loaded.add("buyer-inquiry-followup")
    result = read(await collector.tools["trade_inquiry"]("create", data=inquiry_data()))
    assert result["ok"] is True
    assert result["data"]["workflow_status"] == {"buyer_verification": "not_checked", "quote_present": False,
            "drafts_present": False, "drafts_stale": False, "pending_followups": 0}
    result = read(await collector.tools["trade_calculate_quote"](result["data"]["id"], 1))
    assert result["workflow_status"]["quote_present"] is True
    assert result["workflow_status"]["drafts_present"] is False


@pytest.mark.asyncio
async def test_flat_save_preserves_unspecified_buyer_and_item_fields(ctx):
    tools, _, _ = ctx
    saved = read(await tools["trade_save_inquiry"](title="Flat inquiry", company_name="LYRECO",
        website="https://www.lyreco.com/group/", email="test@example.com", country="FR",
        raw_inquiry="DESK-001 500 standard to Spain", sku="DESK-001", quantity=500,
        custom_packaging=False, destination_country="Spain", requested_lead_days=20))
    assert saved["ok"] is True
    record = saved["data"]
    assert record["buyer"]["company_name"] == "LYRECO" and record["quote"] is None
    changed = read(await tools["trade_save_inquiry"](inquiry_id=record["id"], revision=record["revision"], quantity=1000))
    assert changed["ok"] is True
    result = changed["data"]
    assert result["buyer"] == record["buyer"] and result["requested_lead_days"] == 20
    assert result["items"] == [{"sku": "DESK-001", "quantity": 1000, "custom_packaging": False}]
    assert result["workflow_status"]["quote_present"] is False
    cleared = read(await tools["trade_save_inquiry"](inquiry_id=result["id"], revision=result["revision"], company_name=""))
    assert cleared["data"]["buyer"]["company_name"] == ""
    assert cleared["data"]["buyer"]["website"] == record["buyer"]["website"]


@pytest.mark.asyncio
@pytest.mark.parametrize("fields", [{"sku":"DESK-001"}, {"sku":"DESK-001","quantity":500},
    {"sku":"DESK-001","quantity":True,"custom_packaging":False},
    {"sku":"DESK-001","quantity":500,"custom_packaging":0}])
async def test_flat_save_never_defaults_missing_or_coerces_item_conditions(ctx, fields):
    tools, sessions, _ = ctx
    result = read(await tools["trade_save_inquiry"](title="Incomplete", **fields))
    assert result["ok"] is False and result["status"] == 422
    with sessions() as db: assert db.query(ForeignTradeInquiry).count() == 0


@pytest.mark.asyncio
async def test_flat_save_does_not_overwrite_multisku_and_rejects_stale_revision(ctx):
    tools, _, _ = ctx
    record = read(await tools["trade_inquiry"]("create", data=inquiry_data(items=[
        {"sku":"DESK-001","quantity":500,"custom_packaging":False},
        {"sku":"OTHER-SKU","quantity":100,"custom_packaging":False}])))["data"]
    result = read(await tools["trade_save_inquiry"](inquiry_id=record["id"], revision=1, quantity=1000))
    assert result["status"] == 422
    changed = read(await tools["trade_save_inquiry"](inquiry_id=record["id"], revision=1, title="Renamed only"))
    assert changed["ok"] is True and changed["data"]["items"] == record["items"]
    assert read(await tools["trade_save_inquiry"](inquiry_id=record["id"], revision=1, title="stale"))["status"] == 409


@pytest.mark.asyncio
async def test_flat_save_can_keep_unknown_draft_without_product_line(ctx):
    tools, _, _ = ctx
    result = read(await tools["trade_save_inquiry"](raw_inquiry="Please send a catalog"))
    assert result["ok"] is True and result["data"]["items"] == []
    assert result["data"]["workflow_status"]["buyer_verification"] == "not_checked"


@pytest.mark.asyncio
async def test_flat_import_and_exact_fact_confirmation_preserve_sources(ctx):
    tools, sessions, _ = ctx
    fid = add_file(sessions, data=b"label,value,source_url\nProcessor,2.4 GHz CPU,https://example.com/specs\nPorts,2 USB 3.0,https://example.com/specs\n")
    imported = read(await tools["trade_import_product"](file_ids=[fid], title="Chat product", product_name="Board",
                    brand="Test brand", model="Board-1", source_url="https://example.com/specs", image_credit="User original"))
    assert imported["ok"] is True
    record = imported["data"]
    assert record["facts"] == [] and record["outputs"] is None and len(record["suggested_facts"]) == 2
    assert record["product_name"] == "Board"
    confirmed = read(await tools["trade_confirm_product_facts"](record["pack_id"], record["revision"], True, fact_indices=[2,1]))
    assert confirmed["ok"] is True
    result = confirmed["data"]
    assert result["facts"] == [record["suggested_facts"][1], record["suggested_facts"][0]]
    assert result["facts_confirmation"] == {"confirmed": True, "selected_indices": [2,1], "generated": False}
    assert result["outputs"] is None and result["brand"] == "Test brand"
    duplicate = read(await tools["trade_import_product"](file_ids=[fid], pack_id=result["pack_id"], revision=result["revision"]))
    assert duplicate["ok"] is True and len(duplicate["data"]["documents"]) == 1
    assert duplicate["data"]["product_name"] == "Board"
    assert duplicate["data"]["import_summary"]["skipped_source_file_ids"] == [fid]


@pytest.mark.asyncio
async def test_flat_import_rejects_foreign_file_before_creating_pack(ctx):
    tools, sessions, _ = ctx
    fid = add_file(sessions, owner="bob", chat="bob-chat")
    result = read(await tools["trade_import_product"](file_ids=[fid], title="Should not exist"))
    assert result["status"] == 404
    with sessions() as db: assert db.query(ForeignTradeContentPack).count() == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("indices", [[], [0], [-1], [2], [1,1], [True], [1.0]])
async def test_fact_confirmation_rejects_bad_indices_without_writes(ctx, indices):
    tools, sessions, _ = ctx
    fid = add_file(sessions)
    record = read(await tools["trade_import_product"](file_ids=[fid], product_name="Board"))["data"]
    result = read(await tools["trade_confirm_product_facts"](record["pack_id"], record["revision"], True, fact_indices=indices))
    assert result["status"] == 422
    with sessions() as db:
        row = db.query(ForeignTradeContentPack).first()
        assert row.revision == record["revision"] and row.payload["facts"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("confirmation", [False, 1, "true"])
async def test_fact_confirmation_requires_explicit_strict_boolean_true(ctx, confirmation):
    tools, sessions, _ = ctx
    fid = add_file(sessions)
    record = read(await tools["trade_import_product"](file_ids=[fid], product_name="Board"))["data"]
    result = read(await tools["trade_confirm_product_facts"](record["pack_id"], record["revision"], confirmation))
    assert result["status"] == 422
    with sessions() as db: assert db.query(ForeignTradeContentPack).first().payload["facts"] == []


@pytest.mark.asyncio
async def test_fact_confirmation_all_over_limit_requires_selection(ctx):
    tools, sessions, _ = ctx
    data = "label,value,source_url\n" + "".join(f"Fact {index},Value {index},https://example.com\n" for index in range(21))
    fid = add_file(sessions, data=data.encode())
    record = read(await tools["trade_import_product"](file_ids=[fid], product_name="Board"))["data"]
    assert record["suggested_facts_total"] == 21 and record["suggested_facts_truncated"] is True
    result = read(await tools["trade_confirm_product_facts"](record["pack_id"], record["revision"], True))
    assert result["status"] == 422
    result = read(await tools["trade_confirm_product_facts"](record["pack_id"], record["revision"], True, fact_indices=list(range(1,21))))
    assert result["ok"] is True and len(result["data"]["facts"]) == 20


@pytest.mark.asyncio
async def test_flat_helpers_obey_skill_gate_before_read_or_write(ctx):
    _, sessions, _ = ctx
    from core.llm.foreign_trade_plugin import TradeSkillRequired
    def missing(name): raise TradeSkillRequired("Read required skill: " + name)
    collector = Collector()
    adapter.register_foreign_trade_tools(collector, user_id="alice", chat_id="alice-chat", install_id="trade@alice", require_skill=missing)
    for call in [collector.tools["trade_save_inquiry"](title="blocked"),
                 collector.tools["trade_import_product"](file_ids=[]),
                 collector.tools["trade_confirm_product_facts"]("missing", 1, True)]:
        result = read(await call)
        assert result["errors"][0]["code"] == "skill_not_loaded"
    with sessions() as db:
        assert db.query(ForeignTradeInquiry).count() == 0
        assert db.query(ForeignTradeContentPack).count() == 0


@pytest.mark.asyncio
async def test_flat_import_preserves_partial_receipt_and_retry_deduplication(ctx, monkeypatch):
    tools, sessions, _ = ctx
    first = add_file(sessions, name="one.csv", data=b"label,value\nProcessor,2.4 GHz CPU\n")
    second = add_file(sessions, name="two.csv", data=b"label,value\nPorts,2 USB 3.0\n")
    original = content.ContentPackService.upload
    calls = 0
    def fail_second(self, *args):
        nonlocal calls
        calls += 1
        if calls == 2: raise content.ContentPackError(409, "concurrent change")
        return original(self, *args)
    monkeypatch.setattr(content.ContentPackService, "upload", fail_second)
    partial = read(await tools["trade_import_product"](file_ids=[first, second], title="Prepared pack", product_name="Board"))
    assert partial["ok"] is False and partial["status"] == 409
    assert partial["data"]["imported_source_file_ids"] == [first]
    assert partial["data"]["revision"] == 3
    monkeypatch.setattr(content.ContentPackService, "upload", original)
    finished = read(await tools["trade_import_product"](file_ids=[first, second],
                    pack_id=partial["data"]["pack_id"], revision=partial["data"]["revision"]))
    assert finished["ok"] is True and len(finished["data"]["documents"]) == 2
    assert finished["data"]["import_summary"]["skipped_source_file_ids"] == [first]
    record = finished["data"]
    confirmed = read(await tools["trade_confirm_product_facts"](record["pack_id"], record["revision"], True))
    assert confirmed["data"]["facts"] == record["suggested_facts"]
    assert confirmed["data"]["outputs"] is None

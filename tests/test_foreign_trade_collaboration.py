"""Offline, real-service cross-role workflow; no production DB, network or model."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
import json
import socket

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from core.db.models import Artifact, ForeignTradeInquiry, ForeignTradeContentPack, ForeignTradeCollaboration, UserFolder, UserShadow
from core.foreign_trade.inquiry import InquiryService
from core.foreign_trade.content import ContentPackService
from core.foreign_trade.collaboration import CollaborationService, CollaborationError, TASKS
from core.foreign_trade import content, content_generation, public_data, catalog_content, collaboration
from api.routes.v1 import foreign_trade_collaboration as api


class Storage:
    def __init__(self): self.files = {}
    def upload_bytes(self, value, key): self.files[key] = value; return "memory:" + key
    def download_bytes(self, key): return self.files[key]
    def delete(self, key): self.files.pop(key, None)


@pytest.fixture
def env(monkeypatch):
    import core.files.storage
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    for model in (Artifact, UserFolder, UserShadow, ForeignTradeInquiry, ForeignTradeContentPack, ForeignTradeCollaboration):
        model.__table__.create(engine)
    sessions = sessionmaker(bind=engine)
    storage = Storage()
    for module in (core.files.storage, content, catalog_content, collaboration):
        monkeypatch.setattr(module, "get_storage", lambda: storage)
    monkeypatch.setattr(socket, "create_connection", lambda *a, **kw: pytest.fail("Network is forbidden"))
    monkeypatch.setattr(content_generation, "_translate", AsyncMock(side_effect=RuntimeError("offline translation stub")))
    monkeypatch.setattr(public_data, "verify_buyer", AsyncMock(return_value={
        "status": "partial", "facts": [{"label": "Company", "value": "LYRECO", "source_url": "https://www.lyreco.com/group/"}],
        "sources": [{"url": "https://www.lyreco.com/group/", "retrieved_at": "2026-10-21T00:00:00Z"}],
        "warnings": ["公开网站不能证明来信身份、付款能力或采购意愿"], "checked_at": "2026-10-21T00:00:00Z"}))
    yield sessions, storage
    engine.dispose()


async def create_case(db, **extra):
    inquiry = InquiryService(db)
    record = inquiry.create("alice", {"title": "LYRECO 公开资料 + 模拟订单", "raw_inquiry": "DESK-001, 500 units, standard packaging, Spain",
        "buyer": {"company_name": "LYRECO", "website": "https://www.lyreco.com/group/", "country": "FR"},
        "items": [{"sku": "DESK-001", "quantity": 500, "custom_packaging": False}],
        "destination_country": "Spain", "is_demo_inquiry": True})
    record = await inquiry.verify("alice", record["id"], record["revision"])
    record = inquiry.quote("alice", record["id"], record["revision"])
    return CollaborationService(db).create("alice", {"title": "模拟订单岗位协同", "inquiry_id": record["id"],
        "assignees": {role: role + " operator" for role in {task[2] for task in TASKS}}, **extra})


async def prepare_outputs(db, case):
    packs = ContentPackService(db)
    pack = packs.get("alice", case["content_pack_id"])
    assert pack["facts"] == [] and pack["outputs"] is None
    pack = packs.update("alice", pack["pack_id"], pack["revision"], {"facts": deepcopy(pack["suggested_facts"])})
    pack = await packs.generate("alice", pack["pack_id"], pack["revision"], True)
    assert pack["outputs"]["assets"]
    return CollaborationService(db).refresh_sources("alice", case["collaboration_id"], case["revision"])


def accept_all(db, case):
    service = CollaborationService(db)
    for task in case["tasks"]:
        case = service.update_task("alice", case["collaboration_id"], case["revision"], task["id"], {
            "status": "in_review", "result_note": "已核对本版本来源与验收条件；此处为模拟业务验收记录",
            "unresolved_items": ["实际运费、供货、认证仍待供应商确认"], "risks": ["不能作为实际采购或交期承诺"]})
        case = service.review("alice", case["collaboration_id"], case["revision"], task["id"], True,
                              "测试用户明确确认当前验收条件和未确认事项；非对外承诺")
    return case


@pytest.mark.asyncio
async def test_real_services_prepare_review_export_and_invalidate(env, tmp_path):
    sessions, storage = env
    with sessions() as db:
        svc = CollaborationService(db)
        case = await create_case(db)
        assert case["content_preparation"] == {"created": True, "pack_id": case["content_pack_id"],
            "facts_confirmed": False, "generated": False, "note": "仅导入模拟目录候选事实和几何示意图；请人工确认后生成"}
        assert case["scope"] == "current_user_role_coordination" and len(case["tasks"]) == 6
        assert len(storage.files) == 2 and all(t["status"] == "todo" for t in case["tasks"])
        with pytest.raises(CollaborationError) as error:
            svc.handoff("alice", case["collaboration_id"], case["revision"], "md")
        assert error.value.status == 409
        case = accept_all(db, await prepare_outputs(db, case))
        assert case["workflow_status"]["ready_for_handoff"] is True
        assert case["content_preparation"]["facts_confirmed"] is True
        assert case["content_preparation"]["generated"] is True
        for kind in ("md", "json"):
            output, mime, name = svc.handoff("alice", case["collaboration_id"], case["revision"], kind)
            assert output and name.endswith("." + kind)
            (tmp_path / name).write_bytes(output)
        assert json.loads(svc.handoff("alice", case["collaboration_id"], case["revision"], "json")[0])["external_actions"] == {
            "messages_sent": False, "published": False}
        # This optional fixture is solely a test artifact for the frontend contract check.
        import os
        if os.environ.get("TRADE_COLLABORATION_FIXTURE"):
            from pathlib import Path
            Path(os.environ["TRADE_COLLABORATION_FIXTURE"]).write_text(json.dumps(case, ensure_ascii=False))
        inquiry = InquiryService(db).get("alice", case["inquiry_id"])
        inquiry = InquiryService(db).create_followup("alice", inquiry["id"], inquiry["revision"], "站内跟进",
                                                    "2030-01-01T09:00:00+08:00", "Asia/Shanghai")
        assert svc.get("alice", case["collaboration_id"])["workflow_status"]["ready_for_handoff"] is True
        inquiry = InquiryService(db).update("alice", inquiry["id"], inquiry["revision"], {
            "items": [{"sku": "DESK-001", "quantity": 1000, "custom_packaging": True}]})
        stale = svc.get("alice", case["collaboration_id"])
        assert stale["workflow_status"]["stale_tasks"] == 6
        with pytest.raises(CollaborationError, match="当前依据"):
            svc.handoff("alice", case["collaboration_id"], case["revision"], "json")
        fresh = svc.refresh_sources("alice", case["collaboration_id"], case["revision"])
        assert fresh["workflow_status"]["done_tasks"] == 0
        assert all(t["review"] is None for t in fresh["tasks"])
        assert any(h["event"] == "acceptance_superseded" for h in fresh["history"])


@pytest.mark.asyncio
async def test_source_and_record_owner_isolation_and_cas(env):
    sessions, _ = env
    with sessions() as db, sessions() as other:
        svc, svc2 = CollaborationService(db), CollaborationService(other)
        case = await create_case(db)
        for operation in (lambda: svc.get("bob", case["collaboration_id"]),
                          lambda: svc.create("bob", {"inquiry_id": case["inquiry_id"]}),
                          lambda: svc.update_task("bob", case["collaboration_id"], 1, "sales_requirements", {})):
            with pytest.raises(CollaborationError) as caught:
                operation()
            assert caught.value.status == 404
        assert svc.list("bob") == []
        waiting = svc._load("alice", case["collaboration_id"], 1)
        svc2.update_task("alice", case["collaboration_id"], 1, "sales_requirements", {"assignee_label": "new owner label"})
        with pytest.raises(CollaborationError) as caught:
            svc._save("alice", case["collaboration_id"], 1, waiting, "race")
        assert caught.value.status == 409
        assert svc.get("alice", case["collaboration_id"])["tasks"][0]["assignee_label"] == "new owner label"


@pytest.mark.asyncio
async def test_dependencies_human_acceptance_and_source_refresh(env):
    sessions, _ = env
    with sessions() as db:
        svc = CollaborationService(db)
        case = await create_case(db)
        for deps in (["sales_requirements"], ["sales_handoff"], ["missing"], ["procurement_quote", "procurement_quote"]):
            with pytest.raises(CollaborationError) as caught:
                svc.update_task("alice", case["collaboration_id"], 1, "sales_requirements", {"depends_on": deps})
            assert caught.value.status == 422
        with pytest.raises(CollaborationError, match="人工审核"):
            svc.update_task("alice", case["collaboration_id"], 1, "sales_requirements", {"status": "done"})
        with pytest.raises(CollaborationError, match="必需的前置任务"):
            svc.update_task("alice", case["collaboration_id"], 1, "compliance_review", {"depends_on": []})
        with pytest.raises(CollaborationError) as caught:
            svc.review("alice", case["collaboration_id"], 1, "sales_handoff", True, "skip dependency")
        assert caught.value.status == 409
        with pytest.raises(CollaborationError, match="人工核对"):
            svc.review("alice", case["collaboration_id"], 1, "sales_requirements", False, "unconfirmed")
        case = accept_all(db, await prepare_outputs(db, case))
        pack = ContentPackService(db).get("alice", case["content_pack_id"])
        ContentPackService(db).update("alice", pack["pack_id"], pack["revision"], {"facts": pack["facts"][:-1]})
        stale = svc.get("alice", case["collaboration_id"])
        assert [t["id"] for t in stale["tasks"] if t["stale"]] == ["design_assets", "operations_content", "compliance_review", "sales_handoff"]
        refreshed = svc.refresh_sources("alice", case["collaboration_id"], case["revision"])
        assert refreshed["workflow_status"]["done_tasks"] == 2
        assert not refreshed["workflow_status"]["ready_for_handoff"]


@pytest.mark.asyncio
async def test_pi_cannot_be_bound_to_desk_and_external_sources_are_private(env):
    sessions, _ = env
    with sessions() as db:
        pack = ContentPackService(db).create("alice", "Raspberry Pi 5 independent public-product example")
        pack = ContentPackService(db).update("alice", pack["pack_id"], 1, {"product_name": "Raspberry Pi 5", "model": "Raspberry Pi 5"})
        with pytest.raises(CollaborationError, match="同一模拟 SKU"):
            await create_case(db, content_pack_id=pack["pack_id"], content_relationship="transaction")
        case = await create_case(db, content_pack_id=pack["pack_id"], content_relationship="independent_reference")
        assert "不构成本询盘" in case["source_note"]
        assert case["source_refs"][-1]["relationship"] == "independent_reference"
        inquiry = InquiryService(db).get("alice", case["inquiry_id"])
        assert inquiry["items"][0]["sku"] == "DESK-001" and "Raspberry" not in json.dumps(inquiry["quote"])
        secret = ContentPackService(db).create("bob", "Private pack")
        with pytest.raises(CollaborationError) as caught:
            CollaborationService(db).create("alice", {"inquiry_id": inquiry["id"], "content_pack_id": secret["pack_id"]})
        assert caught.value.status == 404


@pytest.mark.asyncio
async def test_api_contract_and_stale_download(env):
    sessions, _ = env
    with sessions() as db:
        case = await create_case(db)
        case = accept_all(db, await prepare_outputs(db, case))
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.get_current_user] = lambda: SimpleNamespace(user_id="alice")
    def session():
        with sessions() as db:
            yield db
    app.dependency_overrides[api.get_db] = session
    client = TestClient(app)
    path = "/v1/foreign-trade/collaborations/" + case["collaboration_id"]
    assert client.get(path).json()["data"]["workflow_status"]["ready_for_handoff"]
    assert client.get(path + "/handoff", params={"revision": case["revision"], "kind": "md"}).status_code == 200
    assert client.get(path + "/handoff", params={"revision": 1, "kind": "json"}).status_code == 409
    assert client.patch(path + "/tasks/sales_requirements", json={"revision": case["revision"], "status": "done"}).status_code == 422
    assert client.post("/v1/foreign-trade/collaborations", json={"inquiry_id": case["inquiry_id"], "owner_user_id": "bob"}).status_code == 422
    app.dependency_overrides[api.get_current_user] = lambda: SimpleNamespace(user_id="bob")
    assert client.get(path).status_code == 404


@pytest.mark.asyncio
async def test_native_adapter_identity_skill_and_revocation(env, monkeypatch):
    from core.llm.tools import foreign_trade_collaboration_tool as adapter
    from core.llm import foreign_trade_plugin as plugin
    from core.llm.factory.tools.definitions import ToolAssembly
    sessions, _ = env
    monkeypatch.setattr(adapter, "SessionLocal", sessions)
    monkeypatch.setattr(plugin, "assert_trade_plugin_available", lambda *a: None)
    with sessions() as db:
        case = await create_case(db)
    assembly = ToolAssembly()
    reads = []
    adapter.register_collaboration_tools(assembly, user_id="alice", chat_id="alice-chat", install_id="demo", require_skill=reads.append)
    fn = assembly[0]._func
    def unpack(response):
        item = response.content[0]
        return json.loads(item["text"] if isinstance(item, dict) else item.text)
    result = unpack(await fn("get", collaboration_id=case["collaboration_id"]))
    assert result["ok"] and not reads
    result = unpack(await fn("update_task", collaboration_id=case["collaboration_id"], revision=1,
        task_id="sales_requirements", data={"owner_user_id": "bob"}))
    assert result["status"] == 422 and reads == ["cross-role-collaboration"]
    def revoked(*args): raise PermissionError("private installation detail")
    monkeypatch.setattr(plugin, "assert_trade_plugin_available", revoked)
    result = unpack(await fn("get", collaboration_id=case["collaboration_id"]))
    assert result["status"] == 403 and "private" not in json.dumps(result)


@pytest.mark.asyncio
async def test_handoff_rechecks_original_bytes_and_escapes_user_markdown(env):
    sessions, storage = env
    with sessions() as db:
        svc = CollaborationService(db)
        case = accept_all(db, await prepare_outputs(db, await create_case(db)))
        # Notes cannot turn into active HTML or a clickable external link on render.
        last = case["tasks"][-1]
        case = svc.update_task("alice", case["collaboration_id"], case["revision"], last["id"], {
            "status": "in_review", "result_note": '<script>alert(1)</script> [link](https://invalid.example/) '})
        case = svc.review("alice", case["collaboration_id"], case["revision"], last["id"], True, "Explicit acceptance of a text fixture")
        body = svc.handoff("alice", case["collaboration_id"], case["revision"], "md")[0].decode()
        assert "<script>" not in body and "\\[link\\]" in body
        pack = ContentPackService(db).get("alice", case["content_pack_id"])
        file_id = pack["documents"][0]["file_id"]
        artifact = db.query(Artifact).filter_by(artifact_id=file_id).one()
        storage.files[artifact.storage_key] = b"Changed outside the content pack"
        with pytest.raises(CollaborationError) as caught:
            svc.handoff("alice", case["collaboration_id"], case["revision"], "json")
        assert caught.value.status == 409


@pytest.mark.asyncio
async def test_missing_content_can_be_linked_later_without_accepting_it(env):
    sessions, _ = env
    with sessions() as db:
        svc = CollaborationService(db)
        case = await create_case(db, prepare_catalog_content=False)
        assert not case["content_pack_id"]
        another = await create_case(db)
        linked = svc.link_content("alice", case["collaboration_id"], case["revision"], another["content_pack_id"], "transaction")
        assert linked["content_pack_id"] == another["content_pack_id"]
        assert not linked["workflow_status"]["ready_for_handoff"]
        assert all(task["review"] is None for task in linked["tasks"])


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["md", "json"])
@pytest.mark.parametrize("mutation_point", ["after_load", "during_file_check"])
async def test_handoff_never_substitutes_a_concurrent_new_review(env, monkeypatch, kind, mutation_point):
    sessions, _ = env
    with sessions() as db, sessions() as other:
        svc, writer = CollaborationService(db), CollaborationService(other)
        case = accept_all(db, await prepare_outputs(db, await create_case(db)))
        requested_revision = case["revision"]
        changed = False

        def replace_review():
            nonlocal changed
            if changed:
                return
            changed = True
            updated = writer.update_task("alice", case["collaboration_id"], requested_revision, "sales_handoff", {
                "status": "in_review", "result_note": "CONCURRENT_NEW_HANDOFF_CONTENT"})
            updated = writer.review("alice", case["collaboration_id"], updated["revision"], "sales_handoff", True,
                                    "CONCURRENT NEW HUMAN ACCEPTANCE")
            assert updated["revision"] == requested_revision + 2
            assert updated["workflow_status"]["ready_for_handoff"]

        if mutation_point == "after_load":
            original = svc._load
            def load_then_change(*args):
                snapshot = original(*args)
                replace_review()
                return snapshot
            monkeypatch.setattr(svc, "_load", load_then_change)
        else:
            original = svc._verify_files
            def verify_then_change(*args):
                original(*args)
                replace_review()
            monkeypatch.setattr(svc, "_verify_files", verify_then_change)

        with pytest.raises(CollaborationError) as caught:
            svc.handoff("alice", case["collaboration_id"], requested_revision, kind)
        assert caught.value.status == 409
        # Only a request carrying the new revision may export its new acceptance.
        payload = svc.handoff("alice", case["collaboration_id"], requested_revision + 2, kind)[0]
        assert b"CONCURRENT NEW HUMAN ACCEPTANCE" in payload
        if kind == "json":
            assert json.loads(payload)["revision"] == requested_revision + 2

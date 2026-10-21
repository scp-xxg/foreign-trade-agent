"""Scenario-one service/API contracts against isolated SQLite, never the live DB."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from core.db.models.foreign_trade import ForeignTradeInquiry
from core.services.foreign_trade_inquiry import InquiryError, InquiryService
from api.routes.v1 import foreign_trade as routes


@pytest.fixture
def db_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    ForeignTradeInquiry.__table__.create(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture
def svc(db_engine):
    with Session(db_engine) as db:
        yield InquiryService(db)


def values(**updates):
    return {"title": "真实企业公开资料 + 模拟询盘", "buyer": {"company_name": "Lyreco Group",
            "website": "https://www.lyreco.com/group/", "email": "", "country": ""},
            "raw_inquiry": "Please quote DESK-001, 500 units, standard packaging, destination Spain.",
            "items": [{"sku": "DESK-001", "quantity": 500, "custom_packaging": False}],
            "destination_country": "Spain", "is_demo_inquiry": True, **updates}


def test_end_to_end_quote_draft_followup_and_reply(svc):
    item = svc.create("alice", values())
    assert item["revision"] == 1
    assert item["is_demo_inquiry"] and "不代表" in item["source_note"]
    item = svc.quote("alice", item["id"], item["revision"])
    assert item["quote"]["data"]["subtotal"] == "2400.00"
    quote_revision = item["quote_revision"]
    item = svc.draft("alice", item["id"], item["revision"])
    assert item["drafts"]["quote_revision"] == quote_revision
    assert "USD 2400.00" in item["drafts"]["en"]
    assert "演示" in item["drafts"]["zh"]
    assert item["drafts"]["not_sent"] is True
    assert item["drafts"]["method"] == "deterministic_template"
    item = svc.create_followup("alice", item["id"], item["revision"], "核对客户反馈",
                               "2026-10-24T09:30:00+08:00", "Asia/Shanghai")
    assert item["followups"][0]["due_at"] == "2026-10-24T01:30:00+00:00"
    item = svc.mark_replied("alice", item["id"], item["revision"])
    assert item["followups"][0]["status"] == "cancelled"
    assert item["followups"][0]["cancellation_reason"] == "buyer_replied"
    with pytest.raises(InquiryError, match="已回复"):
        svc.create_followup("alice", item["id"], item["revision"], "new", "2026-10-25T12:00:00Z", "UTC")


def test_owner_isolation_get_update_quote_followup(svc):
    item = svc.create("alice", values())
    assert svc.list("mallory") == []
    for operation in [lambda: svc.get("mallory", item["id"]),
                      lambda: svc.update("mallory", item["id"], 1, {"title": "oops"}),
                      lambda: svc.quote("mallory", item["id"], 1),
                      lambda: svc.draft("mallory", item["id"], 1),
                      lambda: svc.mark_replied("mallory", item["id"], 1),
                      lambda: svc.create_followup("mallory", item["id"], 1, "x", "2026-10-21T12:00:00Z", "UTC")]:
        with pytest.raises(InquiryError) as caught:
            operation()
        assert caught.value.status == 404
    assert svc.get("alice", item["id"])["revision"] == 1


def test_stale_revision_does_not_overwrite(svc):
    item = svc.create("alice", values())
    svc.update("alice", item["id"], 1, {"title": "new title"})
    with pytest.raises(InquiryError) as caught:
        svc.update("alice", item["id"], 1, {"title": "old tab overwrite"})
    assert caught.value.status == 409
    assert svc.get("alice", item["id"])["title"] == "new title"


def test_atomic_compare_and_swap_across_sessions(db_engine):
    with Session(db_engine) as one, Session(db_engine) as two:
        svc1, svc2 = InquiryService(one), InquiryService(two)
        item = svc1.create("alice", values())
        pending = svc1._load("alice", item["id"], 1)
        svc2.update("alice", item["id"], 1, {"title": "other writer"})
        pending["title"] = "lost update"
        with pytest.raises(InquiryError) as caught:
            svc1._save("alice", item["id"], 1, pending, "test")
        assert caught.value.status == 409
        assert svc1.get("alice", item["id"])["title"] == "other writer"


def test_revise_retires_old_quote_and_requires_new_draft(svc):
    item = svc.create("alice", values())
    item = svc.quote("alice", item["id"], item["revision"])
    old_quote_id = item["quote"]["data"]["quote_id"]
    item = svc.draft("alice", item["id"], item["revision"])
    item = svc.update("alice", item["id"], item["revision"], {
        "items": [{"sku": "DESK-001", "quantity": 1000, "custom_packaging": True}],
        "requested_lead_days": 15,
    })
    assert item["quote"] is None and item["quote_revision"] is None
    assert item["drafts"]["stale"] is True
    historical = next(event for event in item["history"] if event["event"] == "quote_superseded")
    assert historical["quote"]["data"]["quote_id"] == old_quote_id
    item = svc.quote("alice", item["id"], item["revision"])
    assert item["quote"]["data"]["subtotal"] == "5100.00"
    assert item["quote"]["data"]["production_lead_days"] == 18
    assert item["quote"]["data"]["quote_id"] != old_quote_id
    assert item["drafts"]["stale"] is True
    item = svc.draft("alice", item["id"], item["revision"])
    assert item["drafts"]["stale"] is False
    assert "cannot be promised" in item["drafts"]["en"]
    assert "USD 5100.00" in item["drafts"]["zh"]


@pytest.mark.parametrize("item", [
    {"sku": "DESK-001", "quantity": 1, "custom_packaging": False},
    {"sku": "DESK-001", "quantity": 100, "custom_packaging": True},
    {"sku": "UNKNOWN", "quantity": 100, "custom_packaging": False},
])
def test_invalid_quote_does_not_persist_partial_or_fake_total(svc, item):
    inquiry = svc.create("alice", values(items=[item]))
    with pytest.raises(InquiryError) as caught:
        svc.quote("alice", inquiry["id"], 1)
    assert caught.value.status == 422
    assert caught.value.details["ok"] is False
    saved = svc.get("alice", inquiry["id"])
    assert saved["quote"] is None and saved["revision"] == 1


def test_buyer_country_not_inferred_as_destination(svc):
    item = svc.create("alice", values(destination_country="", buyer={"country": "France"}))
    with pytest.raises(InquiryError, match="目的国"):
        svc.quote("alice", item["id"], 1)


@pytest.mark.parametrize("date,zone", [("2026-10-24T09:00:00", "Asia/Shanghai"),
                                        ("invalid", "UTC"), ("2026-10-24T09:00:00Z", "Fake/Zone")])
def test_invalid_datetime_rejected_without_partial_task(svc, date, zone):
    item = svc.create("alice", values())
    with pytest.raises(InquiryError) as caught:
        svc.create_followup("alice", item["id"], 1, "follow", date, zone)
    assert caught.value.status == 422
    assert svc.get("alice", item["id"])["followups"] == []


def test_due_state_is_derived_and_completion_not_reverted_by_reply(svc):
    item = svc.create("alice", values())
    item = svc.create_followup("alice", item["id"], item["revision"], "follow", "2020-01-01T00:00:00Z", "UTC")
    task_id = item["followups"][0]["id"]
    assert item["followups"][0]["is_due"] is True
    item = svc.update_followup("alice", item["id"], item["revision"], task_id, "completed")
    assert item["followups"][0]["is_due"] is False
    item = svc.mark_replied("alice", item["id"], item["revision"])
    assert item["followups"][0]["status"] == "completed"
    item = svc.resume_followups("alice", item["id"], item["revision"])
    assert item["followups"][0]["status"] == "completed"
    assert item["replied_at"] is None


def test_clarification_draft_does_not_invent_quote(svc):
    item = svc.create("alice", values(items=[]))
    item = svc.draft("alice", item["id"], 1)
    assert item["drafts"]["kind"] == "clarification"
    assert "2400" not in item["drafts"]["en"]
    assert item["quote"] is None


@pytest.mark.asyncio
async def test_public_fetch_failure_stays_unknown(monkeypatch, svc):
    import core.services.foreign_trade_public_data as public_data
    monkeypatch.setattr(public_data, "verify_buyer", AsyncMock(side_effect=RuntimeError("sensitive detail")))
    item = svc.create("alice", values())
    item = await svc.verify("alice", item["id"], 1)
    assert item["buyer_card"]["status"] == "unknown"
    assert "sensitive detail" not in str(item["buyer_card"])
    assert "不能据此判定" in item["buyer_card"]["warnings"][0]


@pytest.mark.asyncio
async def test_public_result_provenance_persisted_and_buyer_edit_invalidates(monkeypatch, svc):
    import core.services.foreign_trade_public_data as public_data
    card = {"status": "public_evidence", "checked_at": "2026-10-21T01:00:00Z", "facts": [
        {"key": "title", "label": "Website title", "value": "Lyreco", "status": "self_reported",
         "source_url": "https://www.lyreco.com/group/", "evidence": "Lyreco"}],
        "sources": [{"url": "https://www.lyreco.com/group/", "status": "available"}], "warnings": []}
    monkeypatch.setattr(public_data, "verify_buyer", AsyncMock(return_value=card))
    item = svc.create("alice", values())
    item = await svc.verify("alice", item["id"], 1)
    assert item["buyer_card"] == card
    item = svc.update("alice", item["id"], item["revision"], {"buyer": {"company_name": "Changed"}})
    assert item["buyer_card"] is None


@pytest.fixture
def client(db_engine):
    app = FastAPI()
    app.include_router(routes.router, prefix="/api")
    def get_test_db():
        with Session(db_engine) as session:
            yield session
    app.dependency_overrides[routes.get_db] = get_test_db
    app.dependency_overrides[routes.get_current_user] = lambda: SimpleNamespace(user_id="alice")
    with TestClient(app) as test_client:
        yield test_client, app


def test_api_owner_isolation_and_error_shape(client):
    browser, app = client
    response = browser.post("/api/v1/foreign-trade/inquiries", json=values())
    assert response.status_code == 200
    inquiry = response.json()["data"]
    app.dependency_overrides[routes.get_current_user] = lambda: SimpleNamespace(user_id="bob")
    response = browser.get(f"/api/v1/foreign-trade/inquiries/{inquiry['id']}")
    assert response.status_code == 404
    assert "无权" in response.json()["detail"]["message"]
    assert browser.get("/api/v1/foreign-trade/inquiries").json()["data"] == []


@pytest.mark.parametrize("quantity", [True, 1.5, "500", 0])
def test_api_rejects_coerced_quantities(client, quantity):
    browser, _ = client
    response = browser.post("/api/v1/foreign-trade/inquiries", json=values(
        items=[{"sku": "DESK-001", "quantity": quantity, "custom_packaging": False}]))
    assert response.status_code == 422


def test_api_products_and_patch_explicit_null_contract(client):
    browser, _ = client
    response = browser.get("/api/v1/foreign-trade/products", params={"query": "DESK-001"})
    assert response.status_code == 200 and response.json()["data"]["ok"] is True
    item = browser.post("/api/v1/foreign-trade/inquiries", json=values(requested_lead_days=15)).json()["data"]
    response = browser.patch(f"/api/v1/foreign-trade/inquiries/{item['id']}", json={"revision": 1, "items": None})
    assert response.status_code == 422
    response = browser.patch(f"/api/v1/foreign-trade/inquiries/{item['id']}", json={"revision": 1, "requested_lead_days": None})
    assert response.status_code == 200 and response.json()["data"]["requested_lead_days"] is None


def test_api_requires_authentication(db_engine, monkeypatch):
    import core.auth.backend as auth_backend
    monkeypatch.setattr(auth_backend, "_auth_mode", lambda: "session")
    app = FastAPI()
    app.include_router(routes.router, prefix="/api")
    def get_test_db():
        with Session(db_engine) as session:
            yield session
    app.dependency_overrides[routes.get_db] = get_test_db
    with TestClient(app) as browser:
        assert browser.get("/api/v1/foreign-trade/inquiries").status_code in (401, 403)


@pytest.mark.asyncio
async def test_slow_public_fetch_does_not_overwrite_concurrent_edit(monkeypatch, db_engine):
    import core.services.foreign_trade_public_data as public_data
    with Session(db_engine) as one, Session(db_engine) as two:
        first, second = InquiryService(one), InquiryService(two)
        item = first.create("alice", values())
        async def fake_verify(*args):
            second.update("alice", item["id"], 1, {"title": "edited during network call"})
            return {"status": "unknown", "checked_at": "2026-10-21T00:00:00Z", "facts": [], "sources": [], "warnings": []}
        monkeypatch.setattr(public_data, "verify_buyer", fake_verify)
        with pytest.raises(InquiryError) as caught:
            await first.verify("alice", item["id"], 1)
        assert caught.value.status == 409
        assert first.get("alice", item["id"])["title"] == "edited during network call"


def test_followup_task_id_cannot_cross_inquiry(svc):
    one, two = svc.create("alice", values()), svc.create("alice", values())
    one = svc.create_followup("alice", one["id"], 1, "follow", "2026-10-24T09:00:00Z", "UTC")
    with pytest.raises(InquiryError) as caught:
        svc.update_followup("alice", two["id"], 1, one["followups"][0]["id"], "completed")
    assert caught.value.status == 404


def test_multiple_items_keep_exact_engine_totals(svc):
    from foreign_trade.engine import search_products
    products = search_products(limit=20)["data"]["products"]
    second = next(product for product in products if product["sku"] != "DESK-001")
    items = [{"sku": "DESK-001", "quantity": 1000, "custom_packaging": True},
             {"sku": second["sku"], "quantity": second["moq"], "custom_packaging": False}]
    item = svc.create("alice", values(items=items))
    item = svc.quote("alice", item["id"], 1)
    assert len(item["quote"]["data"]["items"]) == 2
    from decimal import Decimal
    line_sum = sum(Decimal(line["line_subtotal"]) for line in item["quote"]["data"]["items"])
    assert line_sum == Decimal(item["quote"]["data"]["subtotal"])

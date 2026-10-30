"""Offline knowledge/review API and real-service round trips; no model/provider calls."""
from copy import deepcopy
from types import SimpleNamespace
import json
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from core.db.models.foreign_trade_review import ForeignTradeKnowledgeRule, ForeignTradeReview
from core.foreign_trade import review as module
from core.foreign_trade.review import KnowledgeService, ReviewService, ReviewError
from core.foreign_trade.inquiry import InquiryService
from core.foreign_trade.content import ContentPackService
from api.routes.v1 import foreign_trade_review as api
from test_foreign_trade_collaboration import env


@pytest.fixture
def review_env(env):
    sessions, storage = env
    with sessions() as db:
        ForeignTradeKnowledgeRule.__table__.create(db.get_bind())
        ForeignTradeReview.__table__.create(db.get_bind())
    return sessions, storage


def inquiry(db, owner="alice"):
    svc = InquiryService(db)
    row = svc.create(owner, {"title": "Public test fixture: fictional RFQ", "buyer": {"company_name": "Test buyer"},
        "raw_inquiry": "DEMO DESK-001 1000 units custom packaging delivery to Spain",
        "items": [{"sku": "DESK-001", "quantity": 1000, "custom_packaging": True}],
        "destination_country": "Spain", "is_demo_inquiry": True})
    return svc.quote(owner, row["id"], row["revision"])


async def pack(db, *, brand="Example brand"):
    svc = ContentPackService(db)
    row = svc.create("alice", "Public test fixture: product information")
    row = svc.upload("alice", row["pack_id"], row["revision"], "facts.csv", b"label,value,source_url\nUSB,2 USB 3.0 ports,https://example.test/spec\n")
    row = svc.update("alice", row["pack_id"], row["revision"], {"product_name": "Example USB Hub", "brand": brand,
        "facts": row["suggested_facts"]})
    return await svc.generate("alice", row["pack_id"], row["revision"], True, "template")


def rfq_values(source, **extra):
    return {"source_type": "inquiry", "source_id": source["id"], "source_revision": source["revision"],
        "channel": "alibaba_rfq", "draft": {"title": "DEMO RFQ reply", "body": "DEMO DESK-001 1000 units custom packaging. Total USD 5100.00. Freight and taxes excluded; payment terms and validity pending confirmation.",
        "bullets": [], "language": "en", "locale": "en_US"}, **extra}


def listing_values(source, **extra):
    return {"source_type": "content_pack", "source_id": source["pack_id"], "source_revision": source["revision"],
        "channel": "amazon_listing", "draft": {"title": "Example USB Hub", "item_highlights": "2 USB 3.0 ports",
        "body": "Verify the exact variant and commercial terms before purchase.", "bullets": ["USB: 2 USB 3.0 ports"], "language": "en", "locale": "en_US"}, **extra}


def findings(record, rule_id):
    return [item for item in record["text_annotations"] if item["rule_id"] == rule_id]


def test_knowledge_is_persisted_versioned_and_old_200_is_history(review_env):
    sessions, _ = review_env
    with sessions() as db:
        svc = KnowledgeService(db)
        result = svc.search("alice", channel="amazon_listing", category="platform_rules")
        assert result["knowledge_version"] == "2026-10-31.1"
        rules = {rule["rule_id"]: rule for rule in result["rules"]}
        assert rules["amazon.title_length"]["max_chars"] == 75
        assert rules["amazon.item_highlights_length"]["max_chars"] == 125
        assert rules["amazon.combined_length"]["max_chars"] == 200
        assert "amazon.title_length_200_historical" not in rules
        assert all(rule["source_url"].startswith("https://sellercentral.amazon.com/") and rule["verified_at"] and rule["scope_note"] for rule in rules.values())
        count = db.query(ForeignTradeKnowledgeRule).count()
        svc.search("bob", include_superseded=True)
        assert db.query(ForeignTradeKnowledgeRule).count() == count
        old = svc.search("alice", query="200", include_superseded=True)
        assert any(rule["status"] == "superseded" for rule in old["rules"])
        with pytest.raises(ReviewError) as caught:
            svc.search("")
        assert caught.value.status == 403


def test_rfq_two_rounds_are_immutable_and_preserve_confirmation_gaps(review_env):
    sessions, _ = review_env
    with sessions() as db:
        source = inquiry(db)
        svc = ReviewService(db)
        bad = rfq_values(source)
        bad["draft"]["body"] = "DEMO DESK-001 500 units. Total USD 6000.00. Free shipping, taxes included. Production within 2 days. CE certified."
        first = svc.create("alice", bad)
        stored_first = deepcopy(db.query(ForeignTradeReview).filter_by(review_id=first["review_id"]).one().payload)
        assert findings(first, "quote.amount_consistency") and findings(first, "quote.unknown_freight_tax")
        assert findings(first, "alibaba.rfq_alignment") and findings(first, "quote.unsubstantiated_claims")
        second = svc.create("alice", rfq_values(source, previous_review_id=first["review_id"]))
        assert second["review_id"] != first["review_id"] and second["previous_review_id"] == first["review_id"]
        assert first["summary"]["issue_count"] > second["summary"]["issue_count"] == 0
        assert second["summary"]["needs_confirmation_count"] == 3
        assert second["summary"]["review_status"] == "needs_confirmation"
        assert "quote.amount_consistency" in second["comparison"]["resolved_rule_ids"]
        assert not second["comparison"]["source_changed"] and not second["comparison"]["rules_changed"]
        assert db.query(ForeignTradeReview).filter_by(review_id=first["review_id"]).one().payload == stored_first
        assert second["not_sent"] and second["not_published"]
        assert svc.download("alice", second["review_id"], "json")[0]
        assert "与前一轮比较" in svc.download("alice", second["review_id"], "md")[0].decode()
        import os
        if os.environ.get("TRADE_REVIEW_FIXTURE"):
            Path(os.environ["TRADE_REVIEW_FIXTURE"]).write_text(json.dumps(second, ensure_ascii=False))


def test_repeated_risk_occurrences_have_stable_unique_ids_and_parser_fixture(review_env):
    """The frontend consumes this same real-service result in its parser test."""
    sessions, _ = review_env
    with sessions() as db:
        values = rfq_values(inquiry(db))
        values['draft']['body'] += ' Free shipping. Free shipping.'
        service = ReviewService(db)
        first = service.create('alice', values)
        second = service.create('alice', values)
        annotations = first['text_annotations']
        assert len(annotations) == len({row['annotation_id'] for row in annotations}) == 5
        assert annotations == second['text_annotations']
        repeats = findings(first, 'quote.unknown_freight_tax')
        assert len(repeats) == 2 and {row['quote'] for row in repeats} == {'Free shipping'}
        assert first['summary'] == {'issue_count': 2, 'needs_confirmation_count': 3, 'review_status': 'needs_revision'}
        assert json.loads(service.download('alice', first['review_id'], 'json')[0])['text_annotations'] == annotations
        # Keep opaque identities/timestamps deterministic, never actor details.
        fixture = deepcopy(first)
        fixture['review_id'] = 'review_' + 'f' * 32
        fixture['created_at'] = '2026-10-31T00:00:00+00:00'
        fixture['source'].update(id='inq_' + 'c' * 32, fingerprint='b' * 64)
        path = Path(__file__).parent / 'fixtures/review_repeated_annotations.json'
        import os
        if os.environ.get('UPDATE_TRADE_REVIEW_CONTRACT_FIXTURE') == '1':
            path.write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        assert fixture == json.loads(path.read_text(encoding='utf-8'))


@pytest.mark.parametrize("body", [
    "DEMO DESK-001 1000 units. Goods total USD 4800.00; packaging total USD 300.00; subtotal USD 5100.00.",
    "DEMO DESK-001 1000 units. Goods USD 4800.00. Packaging USD 300.00. Total USD 5100.00.",
    "DEMO DESK-001 1000 units. Goods unit price USD 4.80; packaging per unit USD 0.30; total USD 5100.00.",
])
def test_quote_components_are_matched_to_their_own_labels(review_env, body):
    sessions, _ = review_env
    with sessions() as db:
        values = rfq_values(inquiry(db))
        values["draft"]["body"] = body
        assert not findings(ReviewService(db).create("alice", values), "quote.amount_consistency")


def test_spanish_quote_feedback_and_fee_negation(review_env):
    sessions, _ = review_env
    with sessions() as db:
        values = rfq_values(inquiry(db))
        values["draft"].update(language="es", locale="es_ES", title="Cotización de demostración",
            body="DEMO DESK-001 1000 unidades. Total 5.100,00 USD. Envío gratuito e impuestos incluidos. Distribuidor autorizado.")
        result = ReviewService(db).create("alice", values)
        assert not findings(result, "quote.amount_consistency")
        assert len(findings(result, "quote.unknown_freight_tax")) == 2
        assert findings(result, "quote.unsubstantiated_claims")[0]["status"] == "needs_confirmation"
        values["draft"]["body"] = "DEMO DESK-001 1000 unidades. Total 5.100,00 USD. No incluye envío. Impuestos pendientes de confirmación."
        result = ReviewService(db).create("alice", values)
        assert not findings(result, "quote.unknown_freight_tax")


@pytest.mark.parametrize('clause,expected', [
    ('Freight not included, taxes included.', ['taxes included']),
    ('No discounts, free shipping.', ['free shipping']),
    ('Freight not included; taxes included.', ['taxes included']),
    ('Freight not included and taxes included.', ['taxes included']),
    ('Freight not included or taxes included.', ['taxes included']),
    ('Freight not included but taxes included.', ['taxes included']),
    ('No discounts and free shipping.', ['free shipping']),
    ('No discounts or free shipping.', ['free shipping']),
    ('No discounts but free shipping.', ['free shipping']),
    ('No free shipping. Taxes included.', ['Taxes included']),
    ('Free shipping is not available, taxes included.', ['taxes included']),
    ('Not only free shipping but also taxes included.', ['free shipping', 'taxes included']),
    ('No free shipping.', []),
    ('We do not provide free shipping.', []),
    ('Free shipping is not available.', []),
    ('Free shipping is pending confirmation.', []),
    ('Taxes included is unconfirmed.', []),
    ('No free shipping or taxes included.', []),
    ('No shipping and taxes included.', []),
    ('Without shipping and/or taxes included.', []),
    ('We do not offer free shipping or taxes included.', []),
    ('No incluye envío, impuestos incluidos.', ['impuestos incluidos']),
])
def test_fee_negation_stays_with_its_clause_and_preserves_explicit_negative_lists(review_env, clause, expected):
    sessions, _ = review_env
    with sessions() as db:
        values = rfq_values(inquiry(db))
        values['draft']['body'] = 'DEMO DESK-001 1000 units custom packaging. Total USD 5100.00. ' + clause
        result = ReviewService(db).create('alice', values)
        annotations = findings(result, 'quote.unknown_freight_tax')
        assert [row['quote'] for row in annotations] == expected
        assert all(row['status'] == 'issue' for row in annotations)
        # This bounded language check never removes the independent missing
        # payment/validity/Incoterm confirmations or approves external sending.
        assert len(findings(result, 'quote.commercial_terms')) == 3
        assert result['not_sent'] and result['not_published']


def test_unlabelled_wrong_money_and_unconfirmed_delivery_are_flagged(review_env):
    sessions, _ = review_env
    with sessions() as db:
        values = rfq_values(inquiry(db))
        values["draft"]["body"] = "DEMO DESK-001 1000 units. USD 6000.00. Delivery within 7 days."
        result = ReviewService(db).create("alice", values)
        assert findings(result, "quote.amount_consistency")[0]["status"] == "issue"
        assert any("到货时限" in item["message"] and item["status"] == "needs_confirmation" for item in findings(result, "alibaba.rfq_alignment"))


def test_same_knowledge_version_cannot_silently_change_content(review_env, monkeypatch):
    sessions, _ = review_env
    with sessions() as db:
        svc = KnowledgeService(db)
        svc.search("alice")
        bundle = module._bundle()
        bundle["rules"][0]["max_chars"] = 200
        monkeypatch.setattr(module, "_bundle", lambda: deepcopy(bundle))
        with pytest.raises(ReviewError, match="不能覆盖历史规则") as caught:
            svc.search("alice")
        assert caught.value.status == 409
        assert db.query(ForeignTradeKnowledgeRule).filter_by(rule_id="amazon.title_length").one().payload["max_chars"] == 75


@pytest.mark.asyncio
async def test_amazon_current_limits_repetition_and_unknown_scope(review_env):
    sessions, _ = review_env
    with sessions() as db:
        source = await pack(db)
        values = listing_values(source)
        values["draft"].update(title="USB " * 20 + "!", item_highlights="H" * 126)
        result = ReviewService(db).create("alice", values)
        for rule_id in ("amazon.title_length", "amazon.item_highlights_length", "amazon.combined_length", "amazon.title_characters", "amazon.title_repetition"):
            assert findings(result, rule_id)
        assert all(rule["status"] == "active" for rule in result["rule_evidence"])
        values["draft"].update(locale="de_DE")
        outside = ReviewService(db).create("alice", values)
        assert not findings(outside, "amazon.title_length")
        assert findings(outside, "amazon.scope_confirmation")[0]["status"] == "needs_confirmation"


@pytest.mark.asyncio
async def test_brand_character_exception_does_not_cover_other_occurrences(review_env):
    sessions, _ = review_env
    with sessions() as db:
        source = await pack(db, brand="Brand!")
        values = listing_values(source)
        values["draft"]["title"] = "Brand! USB Hub"
        result = ReviewService(db).create("alice", values)
        assert findings(result, "amazon.title_characters")[0]["status"] == "needs_confirmation"
        values["draft"]["title"] += "!"
        result = ReviewService(db).create("alice", values)
        assert findings(result, "amazon.title_characters")[0]["status"] == "issue"


@pytest.mark.asyncio
async def test_spanish_amazon_draft_and_unconfirmed_pack_gate(review_env):
    sessions, _ = review_env
    with sessions() as db:
        svc = ContentPackService(db)
        unconfirmed = svc.create("alice", "Unconfirmed product source")
        with pytest.raises(ReviewError) as caught:
            ReviewService(db).create("alice", listing_values(unconfirmed))
        assert caught.value.status == 422
        source = await pack(db)
        values = listing_values(source)
        values["draft"].update(language="es", locale="es_US", title="Concentrador USB", item_highlights="2 puertos USB 3.0",
                              body="El pago, la vigencia y el transporte requieren confirmación.", bullets=["2 puertos USB 3.0"])
        result = ReviewService(db).create("alice", values)
        assert result["draft"]["language"] == "es" and result["role"] == "operations"
        assert not findings(result, "amazon.title_length")
        assert findings(result, "amazon.scope_confirmation")
        import os
        if os.environ.get("TRADE_REVIEW_FIXTURE"):
            path = Path(os.environ["TRADE_REVIEW_FIXTURE"])
            path.with_name(path.stem + "-amazon.json").write_text(json.dumps(result, ensure_ascii=False))


def test_owner_source_previous_and_request_validation(review_env):
    sessions, _ = review_env
    with sessions() as db:
        source = inquiry(db)
        svc = ReviewService(db)
        first = svc.create("alice", rfq_values(source))
        for operation in (lambda: svc.get("bob", first["review_id"]), lambda: svc.download("bob", first["review_id"], "json"),
                          lambda: svc.create("bob", rfq_values(source))):
            with pytest.raises(ReviewError) as caught:
                operation()
            assert caught.value.status == 404
        assert svc.list("bob") == []
        bob_source = inquiry(db, "bob")
        with pytest.raises(ReviewError) as caught:
            svc.create("bob", rfq_values(bob_source, previous_review_id=first["review_id"]))
        assert caught.value.status == 404
        with pytest.raises(ReviewError) as caught:
            svc.create("alice", rfq_values(inquiry(db), previous_review_id=first["review_id"]))
        assert caught.value.status == 422
        for invalid in ({"owner_user_id": "bob"}, {"source_revision": True}, {"channel": "arbitrary_platform"}):
            with pytest.raises(ReviewError) as caught:
                svc.create("alice", rfq_values(source, **invalid))
            assert caught.value.status == 422


def test_stale_source_and_immutable_rule_evidence(review_env, monkeypatch):
    sessions, _ = review_env
    with sessions() as db:
        source = inquiry(db)
        svc = ReviewService(db)
        first = svc.create("alice", rfq_values(source))
        bundle = module._bundle()
        bundle["knowledge_version"] = "test-next-version"
        monkeypatch.setattr(module, "_bundle", lambda: deepcopy(bundle))
        second = svc.create("alice", rfq_values(source, previous_review_id=first["review_id"]))
        assert second["comparison"]["rules_changed"]
        assert svc.get("alice", first["review_id"])["rule_version"] == first["rule_version"]
        assert db.query(ForeignTradeKnowledgeRule).count() == len(bundle["rules"]) * 2
        InquiryService(db).update("alice", source["id"], source["revision"], {"title": "Changed source revision"})
        assert svc.get("alice", first["review_id"])["source"]["stale"]
        with pytest.raises(ReviewError) as caught:
            svc.download("alice", first["review_id"], "md")
        assert caught.value.status == 409
        with pytest.raises(ReviewError) as caught:
            svc.create("alice", rfq_values(source))
        assert caught.value.status == 409


@pytest.mark.parametrize("kind", ["md", "json"])
def test_download_rechecks_source_after_rendering(review_env, monkeypatch, kind):
    sessions, _ = review_env
    with sessions() as db:
        source = inquiry(db)
        svc = ReviewService(db)
        result = svc.create("alice", rfq_values(source))
        original, calls = svc._fresh, 0
        def source_changes_after_first_read(*args):
            nonlocal calls
            calls += 1
            if calls == 2:
                with sessions() as other:
                    InquiryService(other).update("alice", source["id"], source["revision"], {"title": "Concurrent change"})
            return original(*args)
        monkeypatch.setattr(svc, "_fresh", source_changes_after_first_read)
        with pytest.raises(ReviewError) as caught:
            svc.download("alice", result["review_id"], kind)
        assert caught.value.status == 409


def test_create_does_not_save_a_review_for_a_concurrently_changed_source(review_env, monkeypatch):
    sessions, _ = review_env
    with sessions() as db:
        source = inquiry(db)
        original = module._evaluate
        def change_during_evaluation(*args):
            result = original(*args)
            with sessions() as other:
                InquiryService(other).update("alice", source["id"], source["revision"], {"title": "Concurrent source edit"})
            return result
        monkeypatch.setattr(module, "_evaluate", change_during_evaluation)
        with pytest.raises(ReviewError) as caught:
            ReviewService(db).create("alice", rfq_values(source))
        assert caught.value.status == 409 and db.query(ForeignTradeReview).count() == 0


@pytest.mark.asyncio
async def test_content_source_file_integrity_is_checked_before_review_download(review_env):
    from core.db.models import Artifact
    sessions, storage = review_env
    with sessions() as db:
        source = await pack(db)
        result = ReviewService(db).create("alice", listing_values(source))
        artifact = db.query(Artifact).filter_by(artifact_id=source["documents"][0]["file_id"]).one()
        storage.files[artifact.storage_key] = b"source changed"
        with pytest.raises(ReviewError) as caught:
            ReviewService(db).download("alice", result["review_id"], "json")
        assert caught.value.status == 409


def test_authenticated_api_has_no_review_update_endpoint(review_env):
    sessions, _ = review_env
    with sessions() as db:
        source = inquiry(db)
    app = FastAPI()
    app.include_router(api.router)
    def session():
        with sessions() as db:
            yield db
    app.dependency_overrides[api.get_db] = session
    app.dependency_overrides[api.get_current_user] = lambda: SimpleNamespace(user_id="alice")
    client = TestClient(app)
    assert client.get("/v1/foreign-trade/knowledge?channel=alibaba_rfq").status_code == 200
    response = client.post("/v1/foreign-trade/reviews", json=rfq_values(source))
    assert response.status_code in {200, 201}
    identifier = response.json()["data"]["review_id"]
    path = "/v1/foreign-trade/reviews/" + identifier
    assert client.get(path).json()["data"]["not_sent"] is True
    assert client.patch(path, json={"draft": {}}).status_code == 405
    assert client.get(path + "/download?kind=md").headers["cache-control"] == "no-store"
    def denied():
        raise HTTPException(401, "Authentication required")
    app.dependency_overrides[api.get_current_user] = denied
    assert client.get("/v1/foreign-trade/knowledge").status_code == 401
    assert client.get(path).status_code == 401

"""One source-linked sales -> operations journey, with real services and exports.

Only public web research is replaced by the existing explicit offline fixture.
No live account, production database or model provider is used. Browser PDF/XLSX
exports are tested separately by the frontend suite and the live demo checklist.
"""
from copy import deepcopy
from io import BytesIO
import json
import zipfile

from PIL import Image
import pytest

from foreign_trade.engine import get_product
from core.foreign_trade.inquiry import InquiryService, InquiryError
from core.foreign_trade.collaboration import CollaborationService
from core.foreign_trade.content import ContentPackService, ContentPackError
from core.foreign_trade.review import ReviewService, ReviewError
from test_foreign_trade_review import review_env
from test_foreign_trade_collaboration import env


def rfq(source, body, previous=None):
    return {"source_type": "inquiry", "source_id": source["id"],
            "source_revision": source["revision"], "channel": "alibaba_rfq",
            "previous_review_id": previous,
            "draft": {"title": "DEMO quotation DESK-001", "body": body,
                      "bullets": [], "language": "en", "locale": "en_GB"}}


def listing(source, title, previous=None):
    return {"source_type": "content_pack", "source_id": source["pack_id"],
            "source_revision": source["revision"], "channel": "amazon_listing",
            "previous_review_id": previous,
            "draft": {"title": title, "item_highlights": "PP; 24 x 15 x 12 cm; gray or white",
                      "body": "DEMO only. Simulated Modular Desk Organizer DESK-001. Material: PP. Dimensions: 24 x 15 x 12 cm. Colors: gray, white.",
                      "bullets": ["Material: PP", "Dimensions: 24 x 15 x 12 cm", "Colors: gray, white"],
                      "language": "en", "locale": "en_US"}}


@pytest.mark.asyncio
async def test_sales_to_operations_two_iterations_and_downloads(review_env):
    sessions, _ = review_env
    with sessions() as db:
        sales, packs = InquiryService(db), ContentPackService(db)
        collaboration, reviews = CollaborationService(db), ReviewService(db)
        product = get_product("DESK-001")
        assert product["ok"] and product["is_simulated"]
        inquiry = sales.create("alice", {
            "title": "Two linked workflows - fictional inquiry",
            "buyer": {"company_name": "LYRECO", "website": "https://www.lyreco.com/group/", "country": "FR"},
            "raw_inquiry": "DEMO DESK-001, 500 units, standard packaging, Spain",
            "items": [{"sku": "DESK-001", "quantity": 500, "custom_packaging": False}],
            "destination_country": "Spain", "is_demo_inquiry": True,
        })
        inquiry = await sales.verify("alice", inquiry["id"], inquiry["revision"])
        assert inquiry["buyer_card"]["status"] == "partial"
        assert inquiry["buyer_card"]["sources"][0]["url"] == "https://www.lyreco.com/group/"
        inquiry = sales.quote("alice", inquiry["id"], inquiry["revision"])
        first_quote_id = inquiry["quote"]["data"]["quote_id"]
        assert inquiry["quote"]["data"]["subtotal"] == "2400.00"
        inquiry = sales.draft("alice", inquiry["id"], inquiry["revision"])
        assert "2400.00" in inquiry["drafts"]["en"] and inquiry["drafts"]["not_sent"]

        # Round two uses the same saved inquiry; the old quotation is invalidated.
        inquiry = sales.update("alice", inquiry["id"], inquiry["revision"], {
            "items": [{"sku": "DESK-001", "quantity": 1000, "custom_packaging": True}]})
        assert inquiry["quote"] is None and inquiry["drafts"]["stale"]
        inquiry = sales.quote("alice", inquiry["id"], inquiry["revision"])
        quote = deepcopy(inquiry["quote"]["data"])
        assert quote["quote_id"] != first_quote_id
        assert (quote["merchandise_subtotal"], quote["packaging_subtotal"], quote["subtotal"]) == ("4800.00", "300.00", "5100.00")
        inquiry = sales.draft("alice", inquiry["id"], inquiry["revision"])
        assert "5100.00" in inquiry["drafts"]["en"] and "5100.00" in inquiry["drafts"]["zh"]
        inquiry = sales.create_followup("alice", inquiry["id"], inquiry["revision"],
            "Confirm packaging artwork and freight", "2030-01-02T09:00:00+01:00", "Europe/Madrid")
        assert inquiry["followups"][0]["status"] == "pending"
        bad = reviews.create("alice", rfq(inquiry, "DEMO DESK-001 1000 units custom packaging. Total USD 6000.00. Free shipping, taxes included."))
        good_text = "DEMO DESK-001 1000 units custom packaging. Goods USD 4800.00. Packaging USD 300.00. Total USD 5100.00. Freight and taxes excluded. Payment, validity and Incoterms pending confirmation."
        good = reviews.create("alice", rfq(inquiry, good_text, bad["review_id"]))
        assert {"quote.amount_consistency", "quote.unknown_freight_tax"} <= set(good["comparison"]["resolved_rule_ids"])
        assert good["not_sent"] and good["not_published"]
        inquiry = sales.update_drafts("alice", inquiry["id"], inquiry["revision"], {"en": good_text, "zh": inquiry["drafts"]["zh"]})

        # The second workflow is bound to the same SKU and inquiry, not a second demo.
        case = collaboration.create("alice", {"title": "Sales to operations handoff", "inquiry_id": inquiry["id"],
            "assignees": {"sales": "Sales agent", "procurement": "Procurement agent", "design": "Operations agent",
                          "operations": "Operations agent", "compliance": "Human reviewer"}})
        assert case["content_relationship"] == "transaction"
        pack = packs.get("alice", case["content_pack_id"])
        assert pack["catalog_binding"]["sku"] == "DESK-001" and not pack["facts"] and pack["outputs"] is None
        assert any(t["id"] == "operations_content" and t["status"] == "todo" for t in case["tasks"])
        pack = packs.update("alice", pack["pack_id"], pack["revision"], {"facts": deepcopy(pack["suggested_facts"])})
        pack = await packs.generate("alice", pack["pack_id"], pack["revision"], True, "template")
        assert pack["outputs"]["method"] == "template"  # Explicitly not claimed as a model call.
        assert {a["kind"] for a in pack["outputs"]["assets"]} == {"square", "landscape", "spec"}
        case = collaboration.refresh_sources("alice", case["collaboration_id"], case["revision"])
        assert case["content_preparation"]["facts_confirmed"] and case["content_preparation"]["generated"]
        assert {ref["id"] for ref in case["source_refs"] if ref["key"] == "content_pack"} == {pack["pack_id"]}

        listing_bad = reviews.create("alice", listing(pack, "DEMO " + "Modular Desk Organizer " * 8))
        listing_good = reviews.create("alice", listing(pack, "DEMO Modular Desk Organizer DESK-001", listing_bad["review_id"]))
        assert "amazon.title_length" in listing_good["comparison"]["resolved_rule_ids"]
        assert listing_good["draft"]["locale"] == "en_US"
        assert listing_good["source"]["id"] == case["content_pack_id"]
        md, _, _ = reviews.download("alice", listing_good["review_id"], "md")
        raw, _, _ = reviews.download("alice", listing_good["review_id"], "json")
        assert "与前一轮比较" in md.decode() and json.loads(raw)["previous_review_id"] == listing_bad["review_id"]
        blob, mime, name = packs.download("alice", pack["pack_id"], "zip", pack["revision"])
        assert mime == "application/zip" and name.endswith(".zip")
        with zipfile.ZipFile(BytesIO(blob)) as archive:
            assert "DESK-001" in archive.read("english-listing.md").decode()
            assert "Question,Answer" in archive.read("customer-faq.csv").decode("utf-8-sig")
            assert "fictional schematic" in archive.read("provenance.txt").decode().lower()
            assert "Simulated catalog" in archive.read("english-listing.md").decode()
            facts = json.loads(archive.read("facts.json"))
            assert facts["facts"] == pack["facts"]
            for kind, size in (("square", (1200, 1200)), ("landscape", (1600, 900)), ("spec", (1200, 1600))):
                with Image.open(BytesIO(archive.read(f"product-{kind}.png"))) as image:
                    image.load()
                    assert image.size == size and image.format == "PNG"
        assert sales.get("alice", inquiry["id"])["quote"]["data"] == quote
        assert case["external_actions"] == {"messages_sent": False, "published": False}
        with pytest.raises(ContentPackError):
            packs.download("bob", pack["pack_id"], "zip", pack["revision"])
        with pytest.raises(ReviewError):
            reviews.download("bob", listing_good["review_id"], "json")
        with pytest.raises(InquiryError):
            sales.get("bob", inquiry["id"])
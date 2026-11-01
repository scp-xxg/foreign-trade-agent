"""Country-specific warnings and real offline KB seed, without network/model."""
from copy import deepcopy
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.db.engine import Base
from core.db.models import UserShadow, UserAgent
from core.foreign_trade.market_compliance import bundle, market_context, evaluate, render_case
from core.foreign_trade.review import _positive_claim, KnowledgeService
from features.knowledge.models import KBSpace, KBDocument, KBChunk, KBWikiPage
from foreign_trade.import_compliance import seed_compliance_knowledge

RULES = {r["rule_id"]:r for r in bundle()["rules"]}


def inspect(rule_id, body, *, country="US", channel="alibaba_rfq", locale="en_US", facts=None):
    findings=[]
    context=market_context(channel, {"destination_country":country}, {"locale":locale})
    applies=evaluate(RULES[rule_id], context, [("body",body)], {"facts":facts or []},
                     lambda *args:findings.append(args), _positive_claim)
    return applies,findings


@pytest.mark.parametrize("rid", [
    "market.us.origin","market.us.environment","market.eu.ce_scope",
    "market.uk.environment","market.uk.marking","market.ca.environment",
])
def test_six_claim_cases_warn_then_resolve_without_fabricated_facts(rid):
    rule=RULES[rid]
    countries={"US":"USA","EU":"Spain","UK":"United Kingdom","CA":"Canada"}
    applies,findings=inspect(rid,rule["bad_draft"],country=countries[rule["market"]])
    assert applies and findings
    assert all(item[-1]=="needs_confirmation" for item in findings)
    assert not inspect(rid,rule["revised_draft"],country=countries[rule["market"]])[1]


@pytest.mark.parametrize("body", ["Not made in USA.","CE certified is unconfirmed.","No eco-friendly claim is made."])
def test_explicit_negations_are_not_positive_claims(body):
    rid="market.us.origin" if "USA" in body else "market.eu.ce_scope" if "CE" in body else "market.us.environment"
    country="Spain" if "CE" in body else "USA"
    assert not inspect(rid,body,country=country)[1]


def test_market_selection_does_not_infer_us_from_english_rfq():
    assert market_context("alibaba_rfq",{"destination_country":"Spain"},{"locale":"en_US"})["market"]=="EU"
    assert market_context("alibaba_rfq",{"destination_country":"unknown"},{"locale":"en_US"})["market"] is None
    assert market_context("amazon_listing",{"destination_country":"Spain"},{"locale":"en_CA"})["market"]=="CA"
    assert market_context("amazon_listing",{},{"locale":"en"})["market"] is None
    assert market_context("alibaba_rfq",{"destination_country":"Northern Ireland"},{"locale":"en_GB"})["market"] is None
    assert inspect("market.ca.environment","Biodegradable organizer",country="USA")== (False,[])


def test_gpsr_and_canadian_packaging_are_conditional_document_hints():
    applies,findings=inspect("market.eu.gpsr","Desk organizer",country="Spain")
    assert applies and len(findings)==1 and "不判定B2B RFQ" in findings[0][2]
    assert findings[0][-1]=="needs_confirmation"
    assert "CE" not in findings[0][2]
    assert not inspect("market.eu.ce_scope","PP organizer",country="Spain")[1]
    _,canada=inspect("market.ca.packaging","An English product listing",country="Canada")
    assert "不判定英文Listing本身违法" in canada[0][2]
    labels=["Packaging scope","Package identity EN","Package identity FR","Package net quantity","Package dealer"]
    facts=[{"label":x,"value":"confirmed source record"} for x in labels]
    complete = inspect("market.ca.packaging","Desk organizer",country="Canada",facts=facts)[1]
    assert complete and complete[0][-1] == "needs_confirmation"
    assert "相关字段已提供" in complete[0][2]
    facts[0]["value"]="pending confirmation"
    assert inspect("market.ca.packaging","Desk organizer",country="Canada",facts=facts)[1]


def test_public_bundle_has_official_sources_scope_and_simulated_before_after():
    hosts={"www.ftc.gov","europa.eu","eur-lex.europa.eu","www.gov.uk","competition-bureau.canada.ca"}
    assert {r["market"] for r in RULES.values()}=={"US","EU","UK","CA"}
    for rule in RULES.values():
        assert urlparse(rule["source_url"]).hostname in hosts
        assert rule["verified_at"]=="2026-11-01"
        assert rule["scope_note"] and rule["unknowns"] and rule["scenario"]
        assert rule["bad_draft"]!=rule["revised_draft"]
        assert rule["source_url"] in render_case(rule)


@pytest.fixture
def database(tmp_path,monkeypatch):
    engine=create_engine("sqlite:///"+str(tmp_path/"cases.db"))
    Base.metadata.create_all(engine)
    sessions=sessionmaker(bind=engine)
    saved={}
    storage=SimpleNamespace(upload_bytes=lambda data,key:saved.__setitem__(key,data),
                            download_bytes=lambda key:saved[key])
    monkeypatch.setattr("core.files.storage.get_storage",lambda:storage)
    monkeypatch.setattr("core.capabilities.agents.edition.UserAgentService._project_to_store",lambda self,role:None)
    with sessions() as db:
        db.add_all([UserShadow(user_id="alice",username="alice"),UserShadow(user_id="bob",username="bob")])
        db.add(UserAgent(agent_id="a",user_id="alice",owner_type="user",name="Renamed sales role",
                         extra_config={"sailagent_core_role":"sales"},
                         kb_ids=["previous"],system_prompt="preserve prompt"))
        db.add(UserAgent(agent_id="custom",user_id="alice",owner_type="user",name="外贸业务员",kb_ids=[],system_prompt="custom"))
        db.commit()
    yield sessions,saved
    engine.dispose()


def test_seed_is_account_scoped_idempotent_and_preserves_human_wiki_edits(database,monkeypatch):
    sessions,saved=database
    with sessions() as db:
        first=seed_compliance_knowledge(db,"alice")
        assert first["document_count"]==8 and first["page_count"]==9
        assert db.query(KBDocument).count()==db.query(KBChunk).count()==8
        assert db.query(KBWikiPage).count()==9
        assert all(doc.indexing_status=="completed" for doc in db.query(KBDocument).all())
        assert len(saved)==8
        page=db.query(KBWikiPage).filter(KBWikiPage.page_type=="concept").first()
        page.content="Keep my careful edit";db.commit()
        before=page.page_id
        second=seed_compliance_knowledge(db,"alice")
        assert first==second
        assert db.get(KBWikiPage,before).content=="Keep my careful edit"
        role=db.get(UserAgent,"a")
        assert role.kb_ids==["previous",first["kb_id"]] and role.system_prompt=="preserve prompt"
        assert db.get(UserAgent,"custom").kb_ids==[]
        other=seed_compliance_knowledge(db,"bob")
        assert other["kb_id"]!=first["kb_id"] and not other["bound_agents"]
        assert db.query(KBDocument).count()==16
        assert db.get(KBSpace,first["kb_id"]).user_id=="alice"
        # Real Wiki retrieval reads the seeded source, rather than a mocked result.
        monkeypatch.setattr("features.knowledge.wiki.local_provider.SessionLocal",sessions)
        from features.knowledge.wiki.local_provider import wiki_search, wiki_read_page
        result=wiki_search(other["kb_id"],"加拿大")
        assert len(result["pages"])==2
        read=wiki_read_page(other["kb_id"],other["documents"][0]["slug"])
        assert read and "source_refs" in read
        lookup=KnowledgeService(db).search("alice",category="market_compliance",query="美国")
        assert len(lookup["rules"])==2
        assert len(KnowledgeService(db).search("alice",category="market_compliance",query="Spain GPSR")["rules"])==1
        assert all(rule["category"]=="market_compliance" for rule in lookup["rules"])


def test_seed_refuses_changed_source_and_unknown_account(database):
    sessions,saved=database
    with sessions() as db:
        with pytest.raises(ValueError):seed_compliance_knowledge(db,"missing")
        first=seed_compliance_knowledge(db,"alice")
        doc=db.get(KBDocument,first["documents"][0]["document_id"])
        saved[doc.storage_key]=b"modified source"
        with pytest.raises(ValueError,match="no longer matches"):seed_compliance_knowledge(db,"alice")


def test_repeated_claims_respect_receipt_limit_without_false_pass():
    from core.foreign_trade.review import _evaluate, _bundle
    draft={"title":"Demo","item_highlights":"","body":"CE certified. "*900,"bullets":[],"language":"en","locale":"en_US"}
    rules=[r for r in _bundle()["rules"] if r["rule_id"] in {"market.eu.ce_scope","quote.unsubstantiated_claims"}]
    result=_evaluate(draft,"alibaba_rfq",{"destination_country":"Spain"},rules)
    assert len(result["text_annotations"])==500
    assert result["annotation_overflow_count"]>0
    assert all(c["status"]=="needs_confirmation" for c in result["checks"])
    assert any("未展开" in label["label"] for label in result["risk_labels"])


def test_seed_preserves_deleted_pages_documents_and_space_without_restart_failure(database):
    from core.infra.time import utc_now
    sessions,_=database
    with sessions() as db:
        first=seed_compliance_knowledge(db,"alice")
        page=db.query(KBWikiPage).filter_by(kb_id=first["kb_id"],slug=first["documents"][0]["slug"]).one()
        page.deleted_at=utc_now()
        document=db.get(KBDocument,first["documents"][1]["document_id"])
        document.deleted_at=utc_now()
        index=db.query(KBWikiPage).filter_by(kb_id=first["kb_id"],slug="index").one()
        index.deleted_at=utc_now()
        db.commit()
        result=seed_compliance_knowledge(db,"alice")
        assert result["skipped_documents"]==[document.document_id]
        assert set(result["skipped_pages"])=={page.slug,"index"}
        assert result["document_count"]==7 and result["page_count"]==7
        assert db.query(KBDocument).count()==8 and db.query(KBWikiPage).count()==9
        assert db.get(KBDocument,document.document_id).deleted_at is not None
        assert db.get(KBWikiPage,page.page_id).deleted_at is not None
        assert seed_compliance_knowledge(db,"alice")==result
        space=db.get(KBSpace,first["kb_id"])
        space.deleted_at=utc_now();db.commit()
        deleted=seed_compliance_knowledge(db,"alice")
        assert deleted["ok"] and deleted["skipped_space"]==first["kb_id"]
        assert deleted["bound_agents"]==[]
        assert db.query(KBSpace).count()==1


def test_gpsr_listing_message_does_not_describe_the_listing_as_b2b_rfq():
    _,findings=inspect("market.eu.gpsr","Draft product listing",
                      channel="amazon_listing",locale="es_ES")
    assert len(findings)==1
    assert "若此Listing面向欧盟消费者远程销售" in findings[0][2]
    assert "B2B RFQ" not in findings[0][2]
    assert findings[0][-1]=="needs_confirmation"


@pytest.mark.parametrize("locale",["es_ES","en_CA","en_GB"])
def test_non_us_listing_does_not_apply_us_platform_baseline(locale):
    from core.foreign_trade.review import _evaluate, _bundle
    draft={"title":"!"*90,"item_highlights":"","body":"Draft product information.",
           "bullets":[],"language":"en","locale":locale}
    rules=[r for r in _bundle()["rules"] if r["status"]=="active" and "amazon_listing" in r["channels"]]
    result=_evaluate(draft,"amazon_listing",{},rules)
    platform={c["rule_id"]:c for c in result["checks"] if c["rule_id"].startswith("amazon.")}
    assert platform["amazon.scope_confirmation"]["status"]=="needs_confirmation"
    assert all(c["status"]=="not_applicable" for rid,c in platform.items()
               if rid!="amazon.scope_confirmation")
    notes=[a for a in result["text_annotations"] if a["rule_id"]=="amazon.scope_confirmation"]
    assert len(notes)==1 and "当前站点不在本项目自动平台规则范围内" in notes[0]["message"]


def test_seed_projects_bound_roles_even_when_database_binding_already_exists(database,monkeypatch):
    from core.capabilities.agents.edition import UserAgentService
    sessions,_=database
    calls=[]
    monkeypatch.setattr(UserAgentService,"_project_to_store",lambda self,role:calls.append((role.agent_id,list(role.kb_ids),role.system_prompt)))
    with sessions() as db:
        first=seed_compliance_knowledge(db,"alice")
        second=seed_compliance_knowledge(db,"alice")
        assert first==second
        assert calls==[("a",["previous",first["kb_id"]],"preserve prompt")]*2
        assert db.get(UserAgent,"custom").kb_ids==[]

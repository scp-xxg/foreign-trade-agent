"""Chat-side bilingual draft revisions preserve identity and enforce the write boundary."""
from copy import deepcopy
import pytest

from core.db.models import ForeignTradeInquiry
from core.db.models.foreign_trade_lexicon import ForeignTradeLexicon
from core.db.models.foreign_trade_review import ForeignTradeKnowledgeRule, ForeignTradeReview
from core.foreign_trade.lexicon import activate
from core.foreign_trade.review import ReviewService
from test_trade_plugin_tools import ctx, new_inquiry, read
from test_trade_plugin_end_to_end import dispatched


def review_values(row, previous=None):
    return {"source_type":"inquiry","source_id":row["id"],"source_revision":row["revision"],
        "channel":"alibaba_rfq","previous_review_id":previous,
        "draft":{"title":"DEMO RFQ","body":row["drafts"]["en"],"language":"en","locale":"en_GB","bullets":[]}}


@pytest.mark.asyncio
async def test_saved_revision_keeps_quote_scans_and_changes_review_source(ctx):
    tools,sessions,_=ctx
    with sessions() as db:
        for model in (ForeignTradeLexicon,ForeignTradeKnowledgeRule,ForeignTradeReview):
            model.__table__.create(db.get_bind())
        activate(db,"alice",{"version":"test","source_name":"Synthetic fixture","source_sha256":"a"*64,
            "rules":[{"rule_id":"test.claim","pattern":"CE certified","level":"L4","reason":"Check evidence",
                      "suggestion":"Confirm source","source_section":"test","source_line":1}]})
    row=await new_inquiry(tools)
    quote=read(await tools["trade_calculate_quote"](row["id"],row["revision"]))
    row=read(await tools["trade_inquiry"]("draft",inquiry_id=row["id"],revision=quote["revision"]))["data"]
    old=deepcopy(row)
    with sessions() as db:
        first=ReviewService(db).create("alice",review_values(row))
    texts={"zh":"演示报价：500件，USD 2400.00，不含运费税费。认证待核实。",
           "en":"DEMO DESK-001 500 units standard packaging. Total USD 2400.00. Freight and taxes excluded. CE certified is unconfirmed."}
    result=read(await tools["trade_inquiry"]("update_drafts",inquiry_id=row["id"],revision=row["revision"],data=texts))
    assert result["ok"]
    row=result["data"]
    assert row["revision"]==old["revision"]+1
    assert row["quote"]==old["quote"] and row["quote_revision"]==old["quote_revision"]
    assert all(row["drafts"][key]==value for key,value in texts.items())
    assert row["drafts"]["not_sent"] and not row["drafts"]["stale"]
    assert row["drafts"]["sensitive_terms"]["status"]=="checked"
    assert row["drafts"]["sensitive_terms"]["match_count"]==1
    with sessions() as db:
        second=ReviewService(db).create("alice",review_values(row,first["review_id"]))
        assert second["comparison"]["source_changed"]
        assert second["draft"]["body"]==texts["en"]
        assert db.query(ForeignTradeInquiry).one().payload["drafts"]["zh"]==texts["zh"]
    stale=read(await tools["trade_inquiry"]("update_drafts",inquiry_id=row["id"],revision=old["revision"],data=texts))
    assert stale["status"]==409
    with sessions() as db:
        stored=db.query(ForeignTradeInquiry).one()
        assert stored.revision==row["revision"]
        stored.owner_user_id="bob";db.commit()
    foreign=read(await tools["trade_inquiry"]("update_drafts",inquiry_id=row["id"],revision=row["revision"],data=texts))
    assert foreign["status"]==404
    with sessions() as db:
        assert db.query(ForeignTradeInquiry).one().revision==row["revision"]


@pytest.mark.asyncio
@pytest.mark.parametrize("data",[
    {"en":"English only"}, {"zh":"只有中文"}, {"zh":" ","en":"text"}, {"zh":"中文","en":""},
    {"zh":True,"en":"text"}, {"zh":"中文","en":123}, {"zh":"中文","en":None},
    {"zh":"中文","en":"x"*30001}, {"zh":"中文","en":"text","not_sent":False},
])
async def test_invalid_or_partial_revisions_do_not_write(ctx,data):
    tools,sessions,_=ctx
    row=await new_inquiry(tools)
    result=read(await tools["trade_inquiry"]("update_drafts",inquiry_id=row["id"],revision=row["revision"],data=data))
    assert result["status"]==422
    with sessions() as db:
        saved=db.query(ForeignTradeInquiry).one()
        assert saved.revision==row["revision"] and saved.payload["drafts"] is None


@pytest.mark.asyncio
async def test_new_action_is_exposed_and_dispatched_by_real_tool_schema(dispatched):
    call,_,_,_=dispatched
    created=await call("trade_save_inquiry",title="Draft editing dispatch",company_name="Demo buyer",sku="DESK-001",
                       quantity=500,custom_packaging=False,destination_country="Spain")
    row=created["data"]
    result=await call("trade_inquiry",action="update_drafts",inquiry_id=row["id"],revision=row["revision"],
                      data={"zh":"演示需求已收到，价格待核实。","en":"DEMO inquiry received; pricing pending confirmation."})
    assert result["ok"] and result["data"]["workflow_status"]["drafts_present"]
    assert result["data"]["quote"] is None

@pytest.mark.asyncio
async def test_update_drafts_requires_the_same_authorized_skill_read(ctx):
    from test_trade_plugin_tools import Collector
    from core.llm.tools import foreign_trade_tool
    from core.llm.foreign_trade_plugin import TradeSkillRequired
    tools,sessions,_=ctx
    row=await new_inquiry(tools)
    checked=[]
    def unread(name):
        checked.append(name)
        raise TradeSkillRequired("Load the current buyer skill",skill_name=name)
    collector=Collector()
    foreign_trade_tool.register_foreign_trade_tools(collector,user_id="alice",chat_id="alice-chat",install_id="trade@alice",require_skill=unread)
    result=read(await collector.tools["trade_inquiry"]("update_drafts",inquiry_id=row["id"],revision=row["revision"],
        data={"zh":"演示稿","en":"Demo draft"}))
    assert result["status"]==409 and result["errors"][0]["code"]=="skill_not_loaded"
    assert checked==["buyer-inquiry-followup"]
    with sessions() as db:
        saved=db.query(ForeignTradeInquiry).one()
        assert saved.revision==row["revision"] and saved.payload["drafts"] is None
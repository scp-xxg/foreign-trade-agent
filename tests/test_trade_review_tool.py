"""Real review-service adapter checks with isolated DB and captured actor identity."""
from copy import deepcopy
import json
import pytest
from core.db.models.foreign_trade_review import ForeignTradeReview
from core.llm.tools.foreign_trade_review_tool import register_review_tools
from core.llm.foreign_trade_plugin import TradeSkillRequired
from test_foreign_trade_collaboration import env
from test_foreign_trade_review import review_env, inquiry, rfq_values


class Collector(list):
    def __init__(self):
        super().__init__()
        self.tools = {}
    def append(self, tool):
        super().append(tool)
        self.tools[tool.name] = tool._func


def unpack(response):
    item = response.content[0]
    return json.loads(item["text"] if isinstance(item, dict) else item.text)


@pytest.fixture
def adapter(review_env, monkeypatch):
    import core.db.engine
    import core.llm.foreign_trade_plugin as plugin
    sessions, _ = review_env
    monkeypatch.setattr(core.db.engine, "SessionLocal", sessions)
    checks = []
    monkeypatch.setattr(plugin, "assert_trade_plugin_available", lambda user, install: checks.append((user, install)))
    loaded = set()
    def require_skill(name):
        if name not in loaded:
            raise TradeSkillRequired("Load the actual review skill first")
    collector = Collector()
    assert register_review_tools(collector, user_id="alice", chat_id="acceptance", install_id="trade@alice", require_skill=require_skill) == ["trade_review"]
    with sessions() as db:
        source = inquiry(db)
    return collector.tools["trade_review"], sessions, source, loaded, checks


@pytest.mark.asyncio
async def test_native_knowledge_review_two_rounds_are_real_and_owned(adapter):
    tool, sessions, source, loaded, checks = adapter
    knowledge = unpack(await tool("knowledge", data={"channel": "alibaba_rfq"}))
    assert knowledge["ok"] and knowledge["data"]["knowledge_version"]
    values = rfq_values(source)
    values["draft"]["body"] = "DEMO DESK-001 1000 units. Total USD 6000.00. Free shipping and taxes included."
    blocked = unpack(await tool("review", data=values))
    assert blocked["status"] == 409 and blocked["errors"][0]["code"] == "skill_not_loaded"
    with sessions() as db:
        assert db.query(ForeignTradeReview).count() == 0
    loaded.add("localization-review")
    first = unpack(await tool("review", data=values))
    assert first["ok"] and first["data"]["risk_labels"] and first["data"]["text_annotations"]
    second = unpack(await tool("review", data=rfq_values(source, previous_review_id=first["data"]["review_id"])))
    assert second["ok"] and second["data"]["summary"]["issue_count"] == 0
    assert second["data"]["summary"]["needs_confirmation_count"] > 0
    assert second["data"]["comparison"]["resolved_rule_ids"]
    fetched = unpack(await tool("get", review_id=second["data"]["review_id"]))
    assert fetched["ok"] and fetched["data"]["not_sent"] and fetched["data"]["not_published"]
    for receipt in (first, second, fetched):
        assert receipt['presentation']['card'] == 'trade_review'
        assert receipt['presentation']['download_formats'] == ['md', 'json']
        assert '审核卡下载按钮' in receipt['presentation']['instruction']
        assert '不要用文件工具重建报告' in receipt['presentation']['instruction']
        assert 'presentation' not in receipt['data']
    assert 'presentation' not in knowledge
    with sessions() as db:
        rows = db.query(ForeignTradeReview).all()
        assert len(rows) == 2 and {row.owner_user_id for row in rows} == {"alice"}
        assert all('presentation' not in row.payload for row in rows)
    assert checks and set(checks) == {("alice", "trade@alice")}


@pytest.mark.asyncio
async def test_native_review_rejects_actor_injection_and_stale_source(adapter):
    tool, sessions, source, loaded, _ = adapter
    loaded.add("localization-review")
    forged = rfq_values(source, user_id="bob")
    assert unpack(await tool("review", data=forged))["status"] == 422
    stale = rfq_values(source)
    stale["source_revision"] += 1
    assert unpack(await tool("review", data=stale))["status"] == 409
    assert unpack(await tool("knowledge", data={"user_id": "bob"}))["status"] == 422
    assert unpack(await tool("knowledge", data={"limit": True}))["status"] == 422
    with sessions() as db:
        assert db.query(ForeignTradeReview).count() == 0


@pytest.mark.asyncio
async def test_native_review_get_respects_ownership_and_plugin_revocation(adapter, monkeypatch):
    tool, sessions, source, loaded, _ = adapter
    loaded.add("localization-review")
    saved = unpack(await tool("review", data=rfq_values(source)))["data"]
    other = Collector()
    register_review_tools(other, user_id="bob", chat_id="other", install_id="trade@bob")
    rejected = unpack(await other.tools["trade_review"]("get", review_id=saved["review_id"]))
    assert rejected["status"] == 404
    import core.llm.foreign_trade_plugin as plugin
    def revoked(*args):
        raise PermissionError("revoked")
    monkeypatch.setattr(plugin, "assert_trade_plugin_available", revoked)
    assert unpack(await tool("get", review_id=saved["review_id"]))["status"] == 403


def test_no_review_tool_without_captured_actor():
    collector = Collector()
    assert register_review_tools(collector, user_id="", chat_id=None, install_id="trade@none") == []
    assert not collector


@pytest.mark.asyncio
async def test_knowledge_invalid_category_has_safe_field_path_and_public_options(adapter):
    from core.db.models.foreign_trade_review import ForeignTradeKnowledgeRule
    tool, sessions, _, _, _ = adapter
    for invalid in ('', 'non_media', 'synthetic-private-value'):
        result = unpack(await tool('knowledge', data={'channel': 'amazon_listing', 'category': invalid}))
        assert not result['ok'] and result['status'] == 422
        assert result['errors'][0]['field'] == 'data.category'
        assert result['errors'][0]['allowed_values'] == ['platform_rules', 'quotation_terms']
        assert 'data.category' in result['errors'][0]['message']
        if invalid:
            assert invalid not in json.dumps(result)
    # Extra-forbidden locations can themselves contain sensitive user input;
    # only known schema names may be echoed as a field path.
    result = unpack(await tool('knowledge', data={'synthetic-private-key': 'synthetic-private-value'}))
    assert result['status'] == 422 and result['errors'][0]['field'] == 'data.<unsupported_field>'
    assert 'synthetic-private' not in json.dumps(result)
    with sessions() as db:
        assert db.query(ForeignTradeKnowledgeRule).count() == 0
        assert db.query(ForeignTradeReview).count() == 0


@pytest.mark.asyncio
async def test_knowledge_zero_matches_warns_to_clear_query_without_broadening_results(adapter):
    tool, _, _, _, _ = adapter
    result = unpack(await tool('knowledge', data={'channel': 'amazon_listing', 'query': 'unmatched synthetic query 746b'}))
    assert result['ok'] and result['data']['rules'] == [] and result['data']['total_matches'] == 0
    assert any('清空 query' in warning and 'channel' in warning and '未自动放宽' in warning for warning in result['warnings'])
    retried = unpack(await tool('knowledge', data={'channel': 'amazon_listing'}))
    assert retried['ok'] and retried['data']['rules'] and retried['data']['total_matches'] > 0
    assert retried['warnings'] == []

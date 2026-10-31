"""Real local plugin imports retain their native trade tools after key deduplication."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from core.capabilities.plugins.runtime.models import DeferredPlugin, ProgressiveResolution
from core.harness.registry import device_catalog
from core.llm import foreign_trade_plugin as trade
from core.llm.factory.tools.definitions import ToolAssembly
from core.llm.tools.ontology_toolkit import OntologyFilteredToolkit
from core.llm.tools.plugin_activation import register_load_plugin
from features.desktop.capabilities import registry
from features.desktop.local.plugins import service as plugins

USER = "local-u1"
SKILLS = ["buyer-inquiry-followup", "product-content", "cross-role-collaboration", "inquiry-quote", "localization-review"]
NAMES = set(trade.TRADE_TOOL_NAMES)


def _import(tmp_path, *, name="foreign-trade-demo"):
    root = tmp_path / name
    for skill in SKILLS:
        directory = root / "skills" / skill
        directory.mkdir(parents=True)
        (directory / "SKILL.md").write_text(
            f"---\nname: {skill}\ndescription: Offline trade test\n---\nRead all instructions before use."
        )
    (root / "plugin.json").write_text(json.dumps({"name": name, "version": "0.4.0"}))
    return plugins.install(USER, str(root))


def _target(installed, *, slug=None):
    return DeferredPlugin(
        installed["install_id"], slug or installed["slug"], "Trade", "Offline test",
        skill_ids=installed["components"]["skills"],
    )


def _decoded(response):
    return json.loads("".join(block.text for block in response.content))


@pytest.mark.asyncio
async def test_real_import_registers_all_tools_initial_dynamic_and_followup(client, tmp_path):
    installed = _import(tmp_path)
    assert installed["slug"].startswith("foreign-trade-demo-")
    assert installed["slug"] != "foreign-trade-demo"
    assert installed["install_id"] == "plugin:local:" + installed["slug"]
    trade.assert_trade_plugin_available(USER, installed["install_id"])

    target = _target(installed)
    resolution = ProgressiveResolution(directory=[target], deferred=[target])
    hidden = ToolAssembly()
    assert trade.register_initial_trade_tools(
        hidden, user_id=USER, chat_id="offline-chat", progressive=resolution
    ) == []

    tools, collector = OntologyFilteredToolkit(tools=[]), ToolAssembly()
    runtime = {
        "toolkit": tools, "user_id": USER, "chat_id": "offline-chat", "persist": False,
        "trade_tools_allowed": True, "permission_context": SimpleNamespace(allow_rules={}),
        "loader": None, "loaded_skill_ids": set(),
    }
    register_load_plugin(collector, {target.slug: target}, runtime)
    load = next(tool for tool in collector if tool.name == "load_plugin")
    await load._func(plugin=target.slug)
    assert {tool.name for tool in tools.tool_groups[0].tools} == NAMES
    assert NAMES <= set(runtime["permission_context"].allow_rules)
    await load._func(plugin=target.slug)
    assert len(tools.tool_groups[0].tools) == len(NAMES)

    resolution.deferred = []
    restored = ToolAssembly()
    assert set(trade.register_initial_trade_tools(
        restored, user_id=USER, chat_id="offline-chat", progressive=resolution
    )) == NAMES

    eager = ToolAssembly()
    assert set(trade.register_initial_trade_tools(
        eager, user_id=USER, chat_id="offline-chat",
        enabled_skill_ids=installed["components"]["skills"],
    )) == NAMES


@pytest.mark.asyncio
async def test_real_import_keeps_full_read_gate_and_revocation(client, tmp_path, monkeypatch, index_db):
    from core.llm.tools import foreign_trade_tool
    installed = _import(tmp_path)
    target = _target(installed)
    loaded = set()
    collector = ToolAssembly()
    trade.register_trade_plugin_target(
        collector, target, user_id=USER, chat_id="offline-chat", loaded_skill_ids=loaded
    )
    inquiry = next(tool for tool in collector if tool.name == "trade_inquiry")
    calls = []
    monkeypatch.setattr(foreign_trade_tool, "SessionLocal", index_db)
    monkeypatch.setattr(foreign_trade_tool.InquiryService, "list", lambda self, user, limit: calls.append(user) or [])
    assert set(target.skill_ids) <= trade._enabled_skill_ids(USER)
    before_read = _decoded(await inquiry._func(action="list"))
    assert before_read["ok"] is False
    assert "view_text_file" in json.dumps(before_read)
    assert not calls

    sid = next(sid for sid in target.skill_ids if "buyer-inquiry-followup" in sid)
    loaded.add(sid)
    after_read = _decoded(await inquiry._func(action="list"))
    assert after_read["ok"] is True
    assert calls == [USER]

    foreign = ToolAssembly()
    assert trade.register_trade_plugin_target(
        foreign, target, user_id="another-user", chat_id="offline-chat", loaded_skill_ids=loaded
    ) == []
    with pytest.raises(PermissionError):
        trade.assert_trade_plugin_available("another-user", installed["install_id"])

    registry.set_enabled("skill:local:" + sid, False)
    disabled_skill = _decoded(await inquiry._func(action="list"))
    assert disabled_skill["ok"] is False
    assert disabled_skill["errors"][0]["code"] in {"plugin_unavailable", "skill_not_loaded"}
    assert sid not in trade._enabled_skill_ids(USER)
    assert "skill:local:" + sid not in trade._enabled_skill_ids(USER)
    assert calls == [USER]
    registry.set_enabled("skill:local:" + sid, True)

    registry.set_enabled(installed["install_id"], False)
    revoked = _decoded(await inquiry._func(action="list"))
    assert revoked["ok"] is False
    assert calls == [USER]


@pytest.mark.parametrize("name", ["foreign-trade-demo-evil", "foreign-trade-demo-copy"])
def test_similarly_named_import_cannot_impersonate_original_package(client, tmp_path, name):
    installed = _import(tmp_path, name=name)
    # Even a caller-provided canonical display slug cannot override the
    # actual package identity behind the authenticated installation id.
    collector = ToolAssembly()
    assert trade.register_trade_plugin_target(
        collector, _target(installed, slug="foreign-trade-demo"),
        user_id=USER, chat_id="offline-chat",
    ) == []
    assert not collector
    with pytest.raises(PermissionError):
        trade.assert_trade_plugin_available(USER, installed["install_id"])


def test_import_identity_must_resolve_the_same_installation_and_revision(client, tmp_path, monkeypatch):
    installed = _import(tmp_path)
    original = device_catalog.resolve_plugin

    def stale(slug, user_id, *, install_id=None):
        package = original(slug, user_id, install_id=install_id)
        return SimpleNamespace(
            install_id=package.install_id, slug=package.slug,
            revision="stale-revision", package=package.package,
        )

    monkeypatch.setattr(device_catalog, "resolve_plugin", stale)
    with pytest.raises(PermissionError):
        trade.assert_trade_plugin_available(USER, installed["install_id"])


@pytest.mark.asyncio
async def test_real_import_two_turn_sticky_rebuild_uses_fresh_full_read_gate(client, tmp_path, index_db, monkeypatch):
    from agentscope.message import ToolCallBlock
    from agentscope.state import AgentState
    from agentscope.tool._response import ToolResponse
    from core.db.models import ChatSession
    from core.capabilities.plugins.runtime.activation_history import record_plugin_activation
    from core.capabilities.plugins.runtime.sticky_selection import resolve_sticky_plugin_capabilities
    from core.llm.strict_trade_function import StrictTradeToolkit
    from core.llm.tools.skill_tool import register_sandboxed_view_text_file
    from core.llm.tools import foreign_trade_tool
    from features.desktop import plugin_resolution
    from features.desktop.capabilities import runtime as capability_runtime
    from core.harness import log_writer

    monkeypatch.setattr(foreign_trade_tool, "SessionLocal", index_db)
    monkeypatch.setattr(log_writer, "schedule_skill_call_write", lambda value: None)
    installed = _import(tmp_path)
    chat_id = "two-turn-imported-trade"
    with index_db() as db:
        db.add(ChatSession(chat_id=chat_id, user_id=USER, title="Offline two-turn"))
        db.commit()

    async def call(toolkit, name, **kwargs):
        block = ToolCallBlock(id="offline-" + name, name=name, input=json.dumps(kwargs))
        results = [chunk async for chunk in toolkit.call_tool(block, AgentState())]
        assert isinstance(results[-1], ToolResponse)
        return results[-1]

    first_skills = installed["components"]["skills"]
    record = None
    for number in (1, 2):
        if number == 1:
            selected = first_skills
            plugin_ids = [installed["install_id"]]
            invoked = first_skills
        else:
            # The second user turn contains no plugin_id or explicit skill_ids.
            sticky = resolve_sticky_plugin_capabilities(user_id=USER, chat_id=chat_id)
            assert sticky.install_ids == [installed["install_id"]]
            assert set(sticky.skill_ids) == set(first_skills)
            selected, plugin_ids, invoked = sticky.skill_ids, sticky.install_ids, []
        resolution = plugin_resolution.resolve_desktop_progressive_plugins(
            user_id=USER, enabled_skill_ids=selected, enabled_mcp_ids=[],
            activated_ids=plugin_ids, invoked_skill_ids=invoked,
        )
        assert len(resolution.directory) == 1
        assert set(resolution.directory[0].skill_ids) == set(first_skills)
        assert not resolution.deferred
        prepared = capability_runtime.prepare(
            f"offline-trade-round-{number}", USER, skill_ids=selected, plugin_ids=plugin_ids,
        )
        try:
            loader = prepared.skill_loader()
            loaded = set()
            collector = ToolAssembly()
            assert set(trade.register_initial_trade_tools(
                collector, user_id=USER, chat_id=chat_id, progressive=resolution,
                loaded_skill_ids=loaded,
            )) == NAMES
            directories = [loader.get_skill_dir(name) for name in selected]
            register_sandboxed_view_text_file(
                collector, directories, loader, fully_loaded_skill_ids=loaded, user_id=USER,
            )
            toolkit = StrictTradeToolkit(tools=collector)
            if number == 1:
                operation = {
                    "action": "create", "data": {
                        "title": "Two-turn inquiry", "buyer": {"company_name": "Offline buyer"},
                        "raw_inquiry": "DESK-001 1000 units custom packaging to Spain",
                        "items": [{"sku": "DESK-001", "quantity": 1000, "custom_packaging": True}],
                        "destination_country": "Spain",
                    },
                }
            else:
                operation = {
                    "action": "update", "inquiry_id": record["id"], "revision": record["revision"],
                    "data": {"items": [{"sku": "DESK-001", "quantity": 500, "custom_packaging": False}]},
                }
            denied = _decoded(await call(toolkit, "trade_inquiry", **operation))
            assert not denied["ok"] and denied["errors"][0]["code"] == "skill_not_loaded"
            with index_db() as db:
                persisted = foreign_trade_tool.InquiryService(db).list(USER, 10)
                if number == 1:
                    assert persisted == []
                else:
                    current = foreign_trade_tool.InquiryService(db).get(USER, record["id"])
                    assert current["revision"] == record["revision"]
                    assert current["items"][0]["quantity"] == 1000
            sid = next(name for name in selected if "buyer-inquiry-followup" in name)
            read = await call(toolkit, "view_text_file", file_path=str(loader.get_skill_dir(sid)) + "/SKILL.md", ranges=[])
            assert str(read.state) == "success"
            assert sid in loaded
            from core.chat.tool_payloads import _build_skill_load_payload
            display = _build_skill_load_payload(sid)
            assert display["skill_id"] == sid and display["detail"]
            result = _decoded(await call(toolkit, "trade_inquiry", **operation))
            assert result["ok"] is True
            previous = record
            record = result["data"]
            with index_db() as db:
                current = foreign_trade_tool.InquiryService(db).get(USER, record["id"])
                assert current["revision"] == record["revision"]
            if number == 1:
                assert record["items"][0]["quantity"] == 1000
                record_plugin_activation(chat_id, [installed["install_id"]], user_id=USER)
            else:
                assert record["revision"] == previous["revision"] + 1
                assert current["items"][0]["quantity"] == 500
                assert current["items"][0]["custom_packaging"] is False
        finally:
            prepared.release()

    other = resolve_sticky_plugin_capabilities(user_id="another-user", chat_id=chat_id)
    assert not other.install_ids and not other.skill_ids
    registry.set_enabled(installed["install_id"], False)
    revoked = resolve_sticky_plugin_capabilities(user_id=USER, chat_id=chat_id)
    assert not revoked.install_ids and not revoked.skill_ids


def test_team_installer_updates_the_migrated_device_package_and_installed_api(client, tmp_path, index_db):
    from core.capabilities.plugins import management
    from features.desktop.local.plugins.legacy_migration import migrate
    from features.desktop.capabilities import store
    from foreign_trade.install import install_device_plugin
    from api.routes.v1.plugins import router

    def package(path, version, names):
        for name in names:
            child = path / "skills" / name
            child.mkdir(parents=True)
            (child / "SKILL.md").write_text(
                f"---\nname: {name}\ndescription: Installer regression\n---\nFull instructions."
            )
        (path / "plugin.json").write_text(json.dumps({"name": "foreign-trade-demo", "version": version}))
        return path

    previous = package(tmp_path / "old-package", "0.3.0", SKILLS[:-1])
    current = package(tmp_path / "new-package", "0.4.0", SKILLS)
    with index_db() as db:
        management.import_plugin(db, previous, owner_user_id=USER, secrets={}, created_by="offline-test")
    assert migrate() == 1
    existing = next(row for row in registry.list_installations(kind="plugin", profile_id="local")
                    if row.payload.get("owner_user_id") == USER)
    old_revision = existing.resolved_revision
    old_package_path = store.get("plugin", "local", existing.key, old_revision).path
    result = install_device_plugin(USER, current)
    assert result["install_id"] == existing.install_id
    assert result["version"] == "0.4.0"
    assert result["action"] == "updated"
    assert result["revision"] != old_revision
    assert old_package_path.is_dir()
    assert len(result["components"]["skills"]) == len(SKILLS)
    assert any("localization-review" in name for name in result["components"]["skills"])

    client.app.include_router(router)
    response = client.get("/v1/plugins/installed")
    assert response.status_code == 200
    rows = [row for row in response.json()["data"]["items"] if row["install_id"] == existing.install_id]
    assert len(rows) == 1 and rows[0]["version"] == "0.4.0"
    assert rows[0]["enabled"] and rows[0]["callable"]
    assert len(rows[0]["skills"]) == len(SKILLS)

    unchanged = install_device_plugin(USER, current)
    assert unchanged["revision"] == result["revision"]
    assert unchanged["action"] == "unchanged"
    registry.set_enabled(existing.install_id, False)
    disabled = install_device_plugin(USER, current)
    assert disabled["enabled"] is False

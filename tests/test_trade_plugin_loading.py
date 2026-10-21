"""Plugin activation, permission boundaries and cross-turn native tool restoration."""
from types import SimpleNamespace

import pytest
from core.llm import foreign_trade_plugin as bridge
from core.llm import plugin_loader
from core.llm.tool_collector import ToolCollector
from core.ontology.toolkit import OntologyFilteredToolkit

NAMES = set(bridge.TRADE_TOOL_NAMES)


@pytest.fixture
def installed(monkeypatch):
    from core.capabilities import registry, skills, paths
    row = SimpleNamespace(install_id="plugin:local:foreign-trade-demo", kind="plugin", key="foreign-trade-demo",
        profile_id="local", ready=True, enabled=True, version="0.2.0", payload={"owner_user_id": "alice"})
    monkeypatch.setattr(paths, "capabilities_enabled", lambda: True)
    monkeypatch.setattr(registry, "get", lambda ident: row if ident == row.install_id else None)
    monkeypatch.setattr(registry, "list_installations", lambda **kw: [row])
    monkeypatch.setattr(registry, "components_of", lambda ident: {"skill:local:trade-content": True})
    monkeypatch.setattr(skills, "account_authorized_for", lambda user: False)
    return row


def target():
    return plugin_loader.DeferredPlugin("plugin:local:foreign-trade-demo", "foreign-trade-demo", "Trade", "Trade workflows")


@pytest.mark.parametrize("change", [
    {"ready": False}, {"enabled": False}, {"version": "0.1.0"},
    {"payload": {"owner_user_id": "bob"}}, {"profile_id": "another-account"},
    {"kind": "skill"}, {"key": "other-plugin"},
])
def test_foreign_or_revoked_install_never_grants_write_tools(installed, change):
    for key, value in change.items():
        setattr(installed, key, value)
    with pytest.raises(PermissionError):
        bridge.assert_trade_plugin_available("alice", installed.install_id)
    collector = ToolCollector()
    assert bridge.register_trade_plugin_target(collector, target(), user_id="alice", chat_id="chat") == []
    assert collector.function_tools == []


def test_authenticated_actor_and_exact_installation_required(installed):
    bridge.assert_trade_plugin_available("alice", installed.install_id)
    for user, ident in [("bob", installed.install_id), ("", installed.install_id), ("alice", "foreign-trade-demo")]:
        with pytest.raises(PermissionError):
            bridge.assert_trade_plugin_available(user, ident)


def test_personal_plugin_switch_revokes_projected_install(installed, monkeypatch):
    installed.payload["db_install_id"] = "foreign-trade-demo@alice"
    monkeypatch.setattr(bridge, "_legacy_available", lambda user, ident: False)
    with pytest.raises(PermissionError):
        bridge.assert_trade_plugin_available("alice", installed.install_id)
    monkeypatch.setattr(bridge, "_legacy_available", lambda user, ident: user == "alice" and ident == "foreign-trade-demo@alice")
    bridge.assert_trade_plugin_available("alice", installed.install_id)


def test_business_skill_gate_uses_the_current_run_read_state(installed, monkeypatch):
    from core.llm.tools import foreign_trade_tool
    captured = []
    monkeypatch.setattr(foreign_trade_tool, "register_foreign_trade_tools",
                        lambda collector, **kwargs: captured.append(kwargs["require_skill"]) or list(NAMES))
    plugin = target()
    sid = "foreign-trade-demo-buyer-inquiry-followup-abcdef"
    monkeypatch.setattr(bridge, "_enabled_skill_ids", lambda user: {sid})
    plugin.skill_ids = [sid]
    loaded = set()
    bridge.register_trade_plugin_target(ToolCollector(), plugin, user_id="alice", chat_id="chat", loaded_skill_ids=loaded)
    with pytest.raises(bridge.TradeSkillRequired, match="view_text_file"):
        captured[0]("buyer-inquiry-followup")
    loaded.add(sid)
    captured[0]("buyer-inquiry-followup")
    monkeypatch.setattr(bridge, "_enabled_skill_ids", lambda user: set())
    with pytest.raises(bridge.TradeSkillRequired, match="已关闭"):
        captured[0]("buyer-inquiry-followup")
    with pytest.raises(bridge.TradeSkillRequired, match="未启用"):
        captured[0]("product-content")


def test_deferred_tools_hidden_then_restored_on_followup(installed):
    plugin = target()
    resolution = plugin_loader.ProgressiveResolution(directory=[plugin], deferred=[plugin])
    collector = ToolCollector()
    assert bridge.register_initial_trade_tools(collector, user_id="alice", chat_id="chat", progressive=resolution) == []
    assert collector.function_tools == []
    resolution.deferred = []
    names = bridge.register_initial_trade_tools(collector, user_id="alice", chat_id="chat", progressive=resolution)
    assert set(names) == NAMES
    assert {tool.name for tool in collector.function_tools} == NAMES
    # Each later turn builds a fresh set of closures bound to its current user.
    other = ToolCollector()
    assert bridge.register_initial_trade_tools(other, user_id="bob", chat_id="chat", progressive=resolution) == []


def test_eager_mode_needs_selected_plugin_component(installed):
    empty, selected = ToolCollector(), ToolCollector()
    assert bridge.register_initial_trade_tools(empty, user_id="alice", chat_id="chat", enabled_skill_ids=["unrelated"]) == []
    assert set(bridge.register_initial_trade_tools(selected, user_id="alice", chat_id="chat", enabled_skill_ids=["trade-content"])) == NAMES


async def test_real_toolkit_activation_updates_surface_and_deduplicates(installed):
    collector, toolkit = ToolCollector(), OntologyFilteredToolkit(tools=[], mcps=[])
    before = await toolkit.freeze_execution_surface()
    runtime = {"toolkit": toolkit, "user_id": "alice", "chat_id": "chat", "persist": False,
               "permission_context": SimpleNamespace(allow_rules={}), "loader": None}
    plugin_loader.register_load_plugin(collector, {"foreign-trade-demo": target()}, runtime)
    response = await collector.get_tool("load_plugin")._func(plugin="foreign-trade-demo")
    text = "".join(b.get("text", "") if isinstance(b, dict) else b.text for b in response.content)
    assert "trade_product_content" in text
    after = await toolkit.freeze_execution_surface()
    assert after.generation > before.generation
    schemas = await toolkit.get_tool_schemas()
    assert NAMES <= {row["function"]["name"] for row in schemas}
    for row in schemas:
        if row["function"]["name"] in NAMES:
            assert not {"user_id", "chat_id", "install_id"} & set(row["function"]["parameters"]["properties"])
    assert NAMES <= set(runtime["permission_context"].allow_rules)
    await collector.get_tool("load_plugin")._func(plugin="foreign-trade-demo")
    assert len(toolkit.tool_groups[0].tools) == len(NAMES)


async def test_staged_native_tools_not_committed_after_failed_checkpoint(monkeypatch):
    from core.capabilities import runtime as capability_runtime
    async_calls = []
    def invalid(prepared):
        async_calls.append(prepared)
        raise PermissionError("revoked during activation")
    monkeypatch.setattr(capability_runtime, "validate", invalid)
    group = SimpleNamespace(tools=[], mcps=[], skills_or_loaders=[])
    with pytest.raises(PermissionError):
        async with plugin_loader._activation_stage(group, {}, object()) as stage:
            stage.group.tools.append(SimpleNamespace(name="native"))
            await stage.checkpoint()
    assert group.tools == [] and async_calls


async def test_read_only_run_never_activates_business_tools(installed):
    collector, toolkit = ToolCollector(), OntologyFilteredToolkit(tools=[], mcps=[])
    runtime = {"toolkit": toolkit, "user_id": "alice", "chat_id": "chat", "persist": False,
               "trade_tools_allowed": False, "permission_context": SimpleNamespace(allow_rules={}), "loader": None}
    plugin_loader.register_load_plugin(collector, {"foreign-trade-demo": target()}, runtime)
    await collector.get_tool("load_plugin")._func(plugin="foreign-trade-demo")
    assert not NAMES.intersection(tool.name for tool in toolkit.tool_groups[0].tools)

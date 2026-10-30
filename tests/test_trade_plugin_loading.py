"""Plugin activation, permission boundaries and cross-turn native tool restoration."""
from types import SimpleNamespace

import pytest
from core.llm import foreign_trade_plugin as bridge
from core.capabilities.plugins.runtime import models as plugin_models
from core.llm.tools import plugin_activation as plugin_loader
from core.llm.factory.tools.definitions import ToolAssembly as ToolCollector
from core.llm.tools.ontology_toolkit import OntologyFilteredToolkit

NAMES = set(bridge.TRADE_TOOL_NAMES)


@pytest.fixture
def installed(monkeypatch):
    from core.harness.registry import device_catalog, execution_account
    row = SimpleNamespace(
        install_id="plugin:local:foreign-trade-demo", kind="plugin", key="foreign-trade-demo",
        profile_id="local", ready=True, enabled=True, version="0.2.0",
        payload={"owner_user_id": "alice", "components": {"skills": ["skill:local:trade-content"]}},
    )
    monkeypatch.setattr(device_catalog, "installations", lambda *a, **kw: [row])
    monkeypatch.setattr(device_catalog, "plugin_entries", lambda *a: [])
    monkeypatch.setattr(device_catalog, "active", lambda: False)
    monkeypatch.setattr(execution_account, "account_authorized_for", lambda user: False)
    monkeypatch.setattr(bridge, "_legacy_available", lambda *a: False)
    from core.capabilities.plugins import management
    from core.db import engine as dbe
    class Session:
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(dbe, "SessionLocal", Session)
    monkeypatch.setattr(management, "list_installed", lambda *a, **kw: [])
    return row


def target():
    return plugin_models.DeferredPlugin("plugin:local:foreign-trade-demo", "foreign-trade-demo", "Trade", "Trade workflows")


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
    assert collector == []


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
    resolution = plugin_models.ProgressiveResolution(directory=[plugin], deferred=[plugin])
    collector = ToolCollector()
    assert bridge.register_initial_trade_tools(collector, user_id="alice", chat_id="chat", progressive=resolution) == []
    assert collector == []
    resolution.deferred = []
    names = bridge.register_initial_trade_tools(collector, user_id="alice", chat_id="chat", progressive=resolution)
    assert set(names) == NAMES
    assert {tool.name for tool in collector} == NAMES
    # Each later turn builds a fresh set of closures bound to its current user.
    other = ToolCollector()
    assert bridge.register_initial_trade_tools(other, user_id="bob", chat_id="chat", progressive=resolution) == []


def test_eager_mode_needs_selected_plugin_component(installed):
    empty, selected = ToolCollector(), ToolCollector()
    assert bridge.register_initial_trade_tools(empty, user_id="alice", chat_id="chat", enabled_skill_ids=["unrelated"]) == []
    assert set(bridge.register_initial_trade_tools(selected, user_id="alice", chat_id="chat", enabled_skill_ids=["trade-content"])) == NAMES


async def test_real_toolkit_activation_updates_surface_and_deduplicates(installed):
    collector, toolkit = ToolCollector(), OntologyFilteredToolkit(tools=[])
    before = await toolkit.freeze_execution_surface()
    runtime = {"toolkit": toolkit, "user_id": "alice", "chat_id": "chat", "persist": False, "trade_tools_allowed": True,
               "permission_context": SimpleNamespace(allow_rules={}), "loader": None}
    plugin_loader.register_load_plugin(collector, {"foreign-trade-demo": target()}, runtime)
    response = await next(tool for tool in collector if tool.name == "load_plugin")._func(plugin="foreign-trade-demo")
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
    await next(tool for tool in collector if tool.name == "load_plugin")._func(plugin="foreign-trade-demo")
    assert len(toolkit.tool_groups[0].tools) == len(NAMES)


async def test_staged_native_tools_not_committed_after_failed_checkpoint(monkeypatch):
    from core.harness.registry import capability_runtime
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
    collector, toolkit = ToolCollector(), OntologyFilteredToolkit(tools=[])
    runtime = {"toolkit": toolkit, "user_id": "alice", "chat_id": "chat", "persist": False, "trade_tools_allowed": False, "permission_context": SimpleNamespace(allow_rules={}), "loader": None}
    plugin_loader.register_load_plugin(collector, {"foreign-trade-demo": target()}, runtime)
    await next(tool for tool in collector if tool.name == "load_plugin")._func(plugin="foreign-trade-demo")
    assert not NAMES.intersection(tool.name for tool in toolkit.tool_groups[0].tools)


def test_full_read_instruction_uses_actual_local_revision_path(installed, monkeypatch, tmp_path):
    from core.llm.tools import foreign_trade_tool
    from core.capabilities.skills import loader_factory, config
    captured = []
    monkeypatch.setattr(foreign_trade_tool, "register_foreign_trade_tools",
        lambda collector, **kwargs: captured.append(kwargs["require_skill"]) or list(NAMES))
    plugin = target()
    sid = "buyer-inquiry-followup-current"
    plugin.skill_ids = [sid]
    directory = tmp_path / "skills" / "local" / sid / "abcdef123456"
    monkeypatch.setattr(bridge, "_enabled_skill_ids", lambda user: {sid})
    monkeypatch.setattr(loader_factory, "get_skill_loader",
        lambda: SimpleNamespace(get_skill_dir=lambda name: str(directory) if name == sid else None))
    monkeypatch.setattr(config, "model_facing_skill_dir", lambda name, path: str(path))
    bridge.register_trade_plugin_target(ToolCollector(), plugin, user_id="alice", chat_id="chat", loaded_skill_ids=set())
    with pytest.raises(bridge.TradeSkillRequired) as error:
        captured[0]("buyer-inquiry-followup")
    assert str(directory / "SKILL.md") in str(error.value)
    assert "/workspace/skills/" not in str(error.value)

    monkeypatch.setattr(loader_factory, "get_skill_loader",
        lambda: SimpleNamespace(get_skill_dir=lambda name: None))
    with pytest.raises(bridge.TradeSkillRequired) as error:
        captured[0]("buyer-inquiry-followup")
    assert "load_plugin" in str(error.value) and "view_text_file" in str(error.value)
    assert "buyer-inquiry-followup" in str(error.value)
    assert sid in str(error.value)
    assert "product-content" not in str(error.value)
    assert "localization-review" not in str(error.value)
    assert "/workspace/skills/" not in str(error.value)


def test_product_full_read_fallback_names_its_own_component_not_review(installed, monkeypatch):
    from core.llm.tools import foreign_trade_tool
    from core.capabilities.skills import loader_factory
    captured = []
    monkeypatch.setattr(foreign_trade_tool, "register_foreign_trade_tools",
        lambda collector, **kwargs: captured.append(kwargs["require_skill"]) or list(NAMES))
    plugin = target()
    product_id, review_id = "product-content-d9cdd9", "localization-review-d9cdd9"
    plugin.skill_ids = [review_id, product_id]
    monkeypatch.setattr(bridge, "_enabled_skill_ids", lambda user: {product_id, review_id})
    monkeypatch.setattr(loader_factory, "get_skill_loader",
        lambda: SimpleNamespace(get_skill_dir=lambda name: None))
    bridge.register_trade_plugin_target(
        ToolCollector(), plugin, user_id="alice", chat_id="chat", loaded_skill_ids={review_id}
    )
    with pytest.raises(bridge.TradeSkillRequired) as error:
        captured[0]("product-content")
    message = str(error.value)
    assert "业务技能 product-content" in message
    assert product_id in message
    assert review_id not in message and "localization-review" not in message
    assert "load_plugin" in message and "view_text_file" in message

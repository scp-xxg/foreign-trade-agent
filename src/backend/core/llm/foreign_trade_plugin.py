"""Bind this fork's trade tools to an authorized, activated plugin installation.

The loopback catalog MCP remains read-only. User-owned business operations run
inside the authenticated agent process, never under an identity supplied by a model.
"""
from __future__ import annotations

TRADE_PLUGIN = "foreign-trade-demo"
TRADE_TOOL_NAMES = frozenset({"trade_inquiry", "trade_calculate_quote", "trade_product_content",
                              "trade_save_inquiry", "trade_import_product", "trade_confirm_product_facts"})


class TradeSkillRequired(ValueError):
    """Recoverable tool response: load the authorized skill before business writes."""


def _upgraded(version: str) -> bool:
    try:
        parts = str(version).split(".")
        return (int(parts[0]), int(parts[1])) >= (0, 2)
    except (ValueError, IndexError):
        return False


def _trade_selector(value: str) -> bool:
    return value == TRADE_PLUGIN or value.endswith(":" + TRADE_PLUGIN)


def _legacy_available(user_id: str, install_id: str) -> bool:
    from core.db.engine import SessionLocal
    from core.services.plugin_service import list_installed
    with SessionLocal() as db:
        matches = [row for row in list_installed(db, user_id, include_global=True)
                   if row["install_id"] == install_id and row["slug"] == TRADE_PLUGIN]
    return bool(matches and matches[0].get("enabled") and matches[0].get("callable")
                and _upgraded(matches[0].get("version", "")))


def _enabled_skill_ids(user_id: str) -> set[str]:
    from core.db.engine import SessionLocal
    from core.config.catalog_resolver import resolve_all_runtime_enabled
    with SessionLocal() as db:
        selected, _, _ = resolve_all_runtime_enabled(db, user_id)
    return set(selected or ())


def assert_trade_plugin_available(user_id: str, install_id: str) -> None:
    """Recheck plugin ownership, current enablement and compatible version per call."""
    if not user_id or not install_id:
        raise PermissionError("外贸插件缺少当前用户的有效安装，请重新加载插件。")
    from core.capabilities.paths import capabilities_enabled, LOCAL_PROFILE, BUILTIN_PROFILE
    if capabilities_enabled():
        from core.capabilities import registry, skills
        row = registry.get(install_id)
        allowed_profiles = {LOCAL_PROFILE, BUILTIN_PROFILE}
        if skills.account_authorized_for(user_id):
            profile = skills.current_account_profile()
            if profile:
                allowed_profiles.add(profile)
        if (row is None or row.kind != "plugin" or row.key != TRADE_PLUGIN or
            row.profile_id not in allowed_profiles or not row.ready or not row.enabled or
            row.payload.get("owner_user_id") not in (None, "", user_id) or not _upgraded(row.version)):
            raise PermissionError("当前账号的外贸插件未安装、已停用或需要升级至 0.2.0。")
        # The web plugin switch is a per-user component override. A projected
        # local installation may remain globally enabled after that switch is off.
        source_install = row.payload.get("db_install_id")
        if source_install and not _legacy_available(user_id, str(source_install)):
            raise PermissionError("当前用户已关闭外贸插件，请重新启用后再使用。")
    else:
        if not _legacy_available(user_id, install_id):
            raise PermissionError("当前账号的外贸插件未安装、已停用或需要升级至 0.2.0。")


def register_trade_plugin_target(collector, target, *, user_id: str, chat_id: str | None,
                                loaded_skill_ids: set[str] | None = None) -> list[str]:
    """Only the resolved trade installation can contribute these native tools."""
    if not _trade_selector(str(target.slug)):
        return []
    try:
        assert_trade_plugin_available(user_id, target.install_id)
    except PermissionError:
        # Version 0.1 still provides its original read-only catalog MCP. Do not
        # break old quote-only installs or grant them the new business tools.
        return []
    import re
    visible_skills = tuple(getattr(target, "skill_ids", ()) or ())
    def require_skill(name: str):
        matches = [sid for sid in visible_skills
                   if re.search(r"(^|[:_-])" + re.escape(name) + r"($|[:_-])", sid)]
        if not matches:
            raise TradeSkillRequired("该业务所需技能未启用，请启用外贸插件中的 " + name + " 技能后重试；本次未执行。")
        if not set(matches).intersection(_enabled_skill_ids(user_id)):
            raise TradeSkillRequired("当前用户已关闭 " + name + " 技能，请重新启用后再执行；本次未执行。")
        if loaded_skill_ids is None or not set(matches).intersection(loaded_skill_ids):
            path = "/workspace/skills/" + matches[0] + "/SKILL.md"
            raise TradeSkillRequired("必须先用 view_text_file(file_path=\"" + path + "\") 读取当前技能，再重试业务操作；本次未执行。")
    from core.llm.tools.foreign_trade_tool import register_foreign_trade_tools
    return register_foreign_trade_tools(collector, user_id=user_id, chat_id=chat_id,
                                       install_id=target.install_id, require_skill=require_skill)


def register_initial_trade_tools(collector, *, user_id: str, chat_id: str | None,
                                 progressive=None, enabled_skill_ids=(), loaded_skill_ids=None) -> list[str]:
    """Restore already-activated tools each turn; leave deferred plugins unloaded."""
    if not user_id:
        return []
    if progressive is not None:
        deferred = {p.install_id for p in progressive.deferred}
        targets = [p for p in progressive.directory if p.install_id not in deferred]
    else:
        # Eager mode still requires this run to select an actual plugin skill.
        from types import SimpleNamespace
        from core.capabilities.paths import capabilities_enabled
        selected = set(enabled_skill_ids or ())
        targets = []
        if capabilities_enabled():
            from core.capabilities import registry
            for row in registry.list_installations(kind="plugin"):
                if row.key != TRADE_PLUGIN:
                    continue
                components = registry.components_of(row.install_id)
                skills = {key for key in components if key.startswith("skill:")}
                aliases = skills | {key.split(":", 2)[-1] for key in skills}
                if aliases & selected:
                    targets.append(SimpleNamespace(slug=row.key, install_id=row.install_id,
                                                   skill_ids=sorted(aliases & selected)))
        elif selected:
            from core.db.engine import SessionLocal
            from core.services.plugin_service import list_installed
            with SessionLocal() as db:
                targets = [SimpleNamespace(slug=row["slug"], install_id=row["install_id"],
                                           skill_ids=sorted(set(row.get("skills", [])) & selected))
                           for row in list_installed(db, user_id, include_global=True)
                           if row["slug"] == TRADE_PLUGIN and set(row.get("skills", [])) & selected]
    names = []
    for target in targets:
        try:
            names.extend(register_trade_plugin_target(collector, target, user_id=user_id, chat_id=chat_id,
                                                     loaded_skill_ids=loaded_skill_ids))
        except PermissionError:
            # An old/disabled installation must not gain write tools during assembly.
            continue
    return list(dict.fromkeys(names))

"""Bind this fork's trade tools to an authorized, activated plugin installation.

The loopback catalog MCP remains read-only. User-owned business operations run
inside the authenticated agent process, never under an identity supplied by a model.
"""
from __future__ import annotations

TRADE_PLUGIN = "foreign-trade-demo"
from core.foreign_trade.tool_names import TRADE_TOOL_NAMES


def trade_tools_allowed(request) -> bool:
    """Business writes require a selected plugin in a writable standard run."""
    return bool(
        request.current_user_id and not request.profile
        and not (request.read_only or request.plan_mode or request.disable_tools or request.turbo_mode)
    )


class TradeSkillRequired(ValueError):
    """Recoverable tool response: load the authorized skill before business writes."""


def _upgraded(version: str) -> bool:
    try:
        parts = str(version).split(".")
        return (int(parts[0]), int(parts[1])) >= (0, 2)
    except (ValueError, IndexError):
        return False


def _device_trade_identity(row, user_id: str, entry: dict | None) -> bool:
    """Resolve imported names through the exact authorized package, never a prefix."""
    if row.key == TRADE_PLUGIN:
        return True
    # Local import keys include the owner's dedup suffix. The callable catalog
    # entry validates the retained package before its original manifest is read.
    if entry is None or not (entry.get("enabled") and entry.get("callable")):
        return False
    from core.harness.registry import device_catalog
    from core.capabilities.plugins.packaging.importer import detect_manifest
    from fastapi import HTTPException
    import json

    try:
        package = device_catalog.resolve_plugin(row.key, user_id, install_id=row.install_id)
        if (
            package is None or package.install_id != row.install_id
            or package.slug != row.key
            or not row.resolved_revision or package.revision != row.resolved_revision
        ):
            return False
        _, manifest_path = detect_manifest(package.package)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return (
            manifest.get("name") == TRADE_PLUGIN
            and str(manifest.get("version") or "") == str(row.version)
        )
    except (OSError, ValueError, TypeError, HTTPException):
        return False


def _legacy_available(user_id: str, install_id: str) -> bool:
    from core.db.engine import SessionLocal
    from core.capabilities.plugins.management import list_installed
    with SessionLocal() as db:
        rows = list_installed(db, user_id, include_global=True)
    if install_id.startswith("plugin:"):
        from types import SimpleNamespace
        from core.capabilities.plugins.runtime.sticky_selection import _local_sticky_selection

        visible = [SimpleNamespace(
            install_id=row["install_id"], slug=row["slug"],
            owner_user_id=None if row.get("is_global") else user_id,
            source=row.get("source"),
        ) for row in rows]
        ids = {row.install_id for row in
               _local_sticky_selection([install_id], visible, user_id=user_id)}
    else:
        ids = {install_id}
    matches = [row for row in rows if row["install_id"] in ids and row["slug"] == TRADE_PLUGIN]
    return bool(len(matches) == 1 and matches[0].get("enabled") and matches[0].get("callable")
                and _upgraded(matches[0].get("version", "")))


def _enabled_skill_ids(user_id: str) -> set[str]:
    from core.db.engine import SessionLocal
    from core.capabilities.catalog.resolver import resolve_all_runtime_enabled
    with SessionLocal() as db:
        selected, _, _ = resolve_all_runtime_enabled(db, user_id)
    enabled = set(selected or ())
    # Local imports now live in the device registry rather than AdminSkill.
    # Recheck the authoritative installation on each call, including revocation;
    # neither a known suffix nor a previously loaded skill grants current access.
    from core.harness.registry import device_catalog, execution_account
    from core.capabilities.identity_rules import LOCAL_PROFILE, BUILTIN_PROFILE
    allowed_profiles = {LOCAL_PROFILE, BUILTIN_PROFILE}
    if execution_account.account_authorized_for(user_id):
        profile = execution_account.current_account_profile()
        if profile:
            allowed_profiles.add(profile)
    for row in device_catalog.installations("skill", user_id=user_id):
        if (
            row.kind != "skill" or row.profile_id not in allowed_profiles
            or row.payload.get("owner_user_id") not in (None, "", user_id)
        ):
            continue
        identities = {str(row.key), str(row.install_id)}
        if row.ready and row.enabled and (row.payload.get("user_enabled") or {}).get(user_id, True):
            enabled.update(identities)
        else:
            # A stale catalog cache must not revive a disabled device skill.
            enabled.difference_update(identities)
    return enabled


def assert_trade_plugin_available(user_id: str, install_id: str) -> None:
    """Recheck the exact installation and authenticated actor on every call."""
    if not user_id or not install_id:
        raise PermissionError("外贸插件缺少当前用户的有效安装，请重新加载插件。")
    from core.harness.registry import device_catalog, execution_account
    from core.capabilities.identity_rules import LOCAL_PROFILE, BUILTIN_PROFILE

    rows = device_catalog.installations("plugin", user_id=user_id)
    row = next((item for item in rows if item.install_id == install_id), None)
    if row is not None:
        allowed_profiles = {LOCAL_PROFILE, BUILTIN_PROFILE}
        if execution_account.account_authorized_for(user_id):
            profile = execution_account.current_account_profile()
            if profile:
                allowed_profiles.add(profile)
        if (row.kind != "plugin" or
            row.profile_id not in allowed_profiles or not row.ready or not row.enabled or
            row.payload.get("owner_user_id") not in (None, "", user_id) or not _upgraded(row.version)):
            raise PermissionError("当前账号的外贸插件未安装、已停用或需要升级至 0.2.0。")
        entries = device_catalog.plugin_entries(user_id)
        entry = next((item for item in entries if item.get("install_id") in {
            install_id, row.payload.get("cloud_install_id"),
        }), None)
        if entry is not None and not (entry.get("enabled") and entry.get("callable")):
            raise PermissionError("当前用户已关闭外贸插件或其组件尚未就绪。")
        if not _device_trade_identity(row, user_id, entry):
            raise PermissionError("该安装不是受支持的外贸插件。")
        source_install = row.payload.get("db_install_id")
        if source_install and not device_catalog.active() and not _legacy_available(user_id, str(source_install)):
            raise PermissionError("当前用户已关闭外贸插件，请重新启用后再使用。")
        return
    # Only local/builtin identities may resolve to local database installations.
    # Unknown cloud/account-scoped ids must never retarget an identically named plugin.
    if install_id.startswith("plugin:"):
        parts = install_id.split(":", 2)
        if len(parts) != 3 or parts[1] not in (LOCAL_PROFILE, BUILTIN_PROFILE):
            raise PermissionError("当前账号没有该外贸插件的有效安装。")
    if not _legacy_available(user_id, install_id):
        raise PermissionError("当前账号的外贸插件未安装、已停用或需要升级至 0.2.0。")


def register_trade_plugin_target(collector, target, *, user_id: str, chat_id: str | None,
                                loaded_skill_ids: set[str] | None = None) -> list[str]:
    """Only the resolved trade installation can contribute these native tools."""
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
            from core.capabilities.skills.loader_factory import get_skill_loader
            from core.capabilities.skills.config import model_facing_skill_dir
            import json
            try:
                directory = get_skill_loader().get_skill_dir(matches[0])
                path = model_facing_skill_dir(matches[0], directory) + "/SKILL.md" if directory else None
            except Exception:
                path = None
            required = "业务技能 " + name + "（当前技能 ID：" + matches[0] + "）"
            if path:
                hint = "用 view_text_file(file_path=" + json.dumps(path, ensure_ascii=False) + ") 完整读取" + required
            else:
                hint = (
                    "为" + required + "取得当前 SKILL.md 路径（可调用 load_plugin 加载插件 "
                    + str(target.slug) + "），再用 view_text_file 完整读取该指定技能"
                )
            raise TradeSkillRequired("必须先" + hint + "，不能以读取其他技能代替；再重试业务操作，本次未执行。")
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
        from core.harness.registry import device_catalog
        from core.db.engine import SessionLocal
        from core.capabilities.plugins.management import list_installed

        selected = set(enabled_skill_ids or ())
        targets = []
        if selected:
            for row in device_catalog.installations("plugin", user_id=user_id):
                # Exact package identity is checked by register_trade_plugin_target;
                # imported keys must not be rejected merely for their owner suffix.
                components = row.payload.get("components") or {}
                skills = set(components.get("skills") or ())
                aliases = skills | {
                    "skill:" + row.profile_id + ":" + key for key in skills
                    if not key.startswith("skill:")
                } | {key.split(":", 2)[-1] for key in skills}
                if aliases & selected:
                    targets.append(SimpleNamespace(
                        slug=row.key, install_id=row.install_id,
                        skill_ids=sorted(aliases & selected),
                    ))
            with SessionLocal() as db:
                local = list_installed(db, user_id, include_global=True)
            projected_ids = {target.install_id for target in targets}
            for row in local:
                if (row["slug"] == TRADE_PLUGIN and row["install_id"] not in projected_ids
                        and set(row.get("skills", [])) & selected):
                    targets.append(SimpleNamespace(
                        slug=row["slug"], install_id=row["install_id"],
                        skill_ids=sorted(set(row.get("skills", [])) & selected),
                    ))
    names = []
    for target in targets:
        try:
            names.extend(register_trade_plugin_target(collector, target, user_id=user_id, chat_id=chat_id,
                                                     loaded_skill_ids=loaded_skill_ids))
        except PermissionError:
            # An old/disabled installation must not gain write tools during assembly.
            continue
    return list(dict.fromkeys(names))

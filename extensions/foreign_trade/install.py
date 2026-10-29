"""Install this demo for an existing local account using HugAgentOS's own service."""
from __future__ import annotations

import argparse
import json
import hashlib
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent


def apply_homepage_copy(db):
    """Apply only the public fork's trade home copy; retain navigation and auth."""
    from copy import deepcopy
    from datetime import datetime, timezone
    from sqlalchemy.orm.attributes import flag_modified
    from core.files.content.content_blocks_constants import DEFAULT_PAGE_CONFIG
    from core.db.models import ContentBlock

    page = db.query(ContentBlock).filter(ContentBlock.id == "page_config").one_or_none()
    if page is None:
        raise RuntimeError("Existing page_config was not found; initialize the application first.")
    payload = deepcopy(page.payload or {})
    branding = payload.setdefault("branding", {})
    for key in ("product_subtitle", "hero_title", "hero_subtitle", "disclaimer"):
        branding[key] = DEFAULT_PAGE_CONFIG["branding"][key]
    homepage = payload.setdefault("homepage", {})
    homepage["show_suggestions"] = True
    homepage["suggested_questions"] = deepcopy(DEFAULT_PAGE_CONFIG["homepage"]["suggested_questions"])
    texts = payload.setdefault("texts", {})
    for key in ("input_placeholder", "input_placeholder_agent", "recommend_banner_text"):
        texts[key] = DEFAULT_PAGE_CONFIG["texts"][key]
    page.payload = payload
    page.updated_at = datetime.now(timezone.utc)
    page.updated_by = "foreign-trade-home-copy"
    flag_modified(page, "payload")
    db.commit()


def apply_assistant_prompt(db):
    """Activate a trade variant of the current prompt, retaining the prior version."""
    from core.llm import prompt_versions as prompts

    active = prompts.get_active_version("system", db=db)
    if active is None:
        raise RuntimeError("Active system prompt was not found; initialize the application first.")
    from copy import deepcopy
    from uuid import uuid4
    parts = deepcopy(active["parts"])
    directory = HERE.parents[1] / "src/backend/prompts/prompt_text/default/system"
    for name in ("00_role", "10_constraints", "20_tools"):
        matches = [part for part in parts if part["part_id"] == "system/" + name]
        if len(matches) != 1:
            raise RuntimeError("Expected exactly one system prompt part: " + name)
        matches[0]["content"] = (directory / (name + ".system.md")).read_text(encoding="utf-8")
    # A content-addressed version preserves every prior prompt, including an
    # operator's edits to a previously installed trade variant.
    digest = hashlib.sha256(json.dumps(parts, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]
    version_id = "foreign-trade-demo-v3-" + digest
    if active.get("id", "").startswith("foreign-trade-demo-v3-") and active["parts"] == parts:
        return active["id"]
    existing = prompts.get_version("system", version_id, db=db)
    if existing and existing.get("parts") != parts:
        # A human can edit a content-addressed version later. Never overwrite it
        # merely because its original identifier matches today's shipped text.
        version_id += "-" + uuid4().hex[:8]
    elif existing:
        prompts.activate_version("system", version_id, db=db)
        return version_id
    prompts.upsert_version(
        "system", version_id, name="外贸助手 · 询盘、商品资料与岗位协同",
        description="公开项目外贸演示；保留其他系统片段，仅更新身份、业务事实约束与插件加载步骤。",
        parts=parts, db=db, updated_by="foreign-trade-home-copy",
    )
    prompts.activate_version("system", version_id, db=db)
    return version_id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-home", required=True, type=Path, help="Existing public application's data directory")
    parser.add_argument("--username", required=True, help="Existing local account; no account or permission changes")
    parser.add_argument("--legacy-chat-completions", action="store_true", help="Identify this existing unversioned database as a known old Chat Completions installation")
    parser.add_argument("--repair-legacy-filenames", action="store_true", help="Preserve duplicate file metadata using upstream unique names and a recovery journal")
    parser.add_argument("--expected-filename-repairs", type=int, help="Refuse repair when the reviewed count differs")
    parser.add_argument("--apply-homepage-copy", action="store_true", help="Replace home copy and suggestions with public foreign-trade defaults")
    parser.add_argument("--apply-assistant-prompt", action="store_true", help="Activate the trade assistant prompt, retaining the previous version")
    args = parser.parse_args()
    home = args.app_home.expanduser().resolve()
    if not (home / "data.db").is_file():
        raise SystemExit("Existing local application's data.db was not found; nothing installed.")
    from foreign_trade.upgrade import prepare_database
    from foreign_trade.team import runtime_env
    upgrade_report = prepare_database(home, legacy_chat_completions=args.legacy_chat_completions, repair_legacy_filenames=args.repair_legacy_filenames, expected_filename_repairs=args.expected_filename_repairs)
    os.environ.update(runtime_env(home))

    from cli import apply_local_env
    apply_local_env(3001)
    from core.db.engine import SessionLocal
    from core.db.models import UserShadow, ContentBlock
    from sqlalchemy.orm.attributes import flag_modified
    from copy import deepcopy
    from datetime import datetime
    from core.capabilities.plugins import management as plugin_service
    from features import register_package_sources, register_resource_owners
    register_package_sources()
    register_resource_owners()

    with SessionLocal() as db:
        account = db.query(UserShadow.user_id).filter(UserShadow.username == args.username).one_or_none()
        if account is None:
            raise SystemExit("Existing account was not found; no account was created.")
        user_id = account[0]
        result = plugin_service.import_plugin(
            db, HERE / "plugin", owner_user_id=user_id, secrets={}, created_by="foreign-trade-local-setup",
        )
        meta = plugin_service.set_installed_plugin_meta(
            db, result["install_id"], owner_user_id=user_id,
            display_name="外贸业务助手（演示）", category="办公效率",
        )
        # CE hides plugin-contributed shortcut cards. Use its existing homepage
        # suggestions instead. Replacing the full scene copy is an explicit opt-in.
        page = db.query(ContentBlock).filter(ContentBlock.id == "page_config").one_or_none()
        from core.files.content.content_blocks_constants import DEFAULT_PAGE_CONFIG
        homepage_entries = DEFAULT_PAGE_CONFIG["homepage"]["suggested_questions"]
        if args.apply_homepage_copy:
            apply_homepage_copy(db)
        elif page is not None:
            payload = deepcopy(page.payload or {})
            homepage = dict(payload.get("homepage") or {})
            questions = list(homepage.get("suggested_questions") or [])
            homepage["suggested_questions"] = questions + [entry for entry in homepage_entries if entry not in questions]
            payload["homepage"] = homepage
            page.payload = payload
            page.updated_at = datetime.utcnow()
            page.updated_by = "foreign-trade-local-setup"
            flag_modified(page, "payload")
            db.commit()
        if args.apply_assistant_prompt:
            apply_assistant_prompt(db)
        report = result["import_report"]
        print(json.dumps({
            "ok": True, "action": result["action"], "name": meta["name"], "schema_upgrade": upgrade_report,
            "installed_components": [{"type": x["type"], "name": x["name"]} for x in report["imported"]],
            "adapted": report["adapted"], "dropped": report["dropped"],
            "account_permissions_changed": False,
            "homepage_copy_applied": args.apply_homepage_copy,
            "assistant_prompt_applied": args.apply_assistant_prompt,
            "next_step": "After a source upgrade, restart this public backend, refresh the page and start a new chat. For a package-content-only update, toggle the trade plugin off and on to refresh the running cache.",
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

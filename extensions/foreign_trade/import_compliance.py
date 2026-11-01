"""Seed curated public compliance cases into one account's real, searchable KB.

No model, embeddings, web request, credentials or private merchant data is needed.
Wiki pages are explicitly authored case summaries, not claimed to be AI-generated.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path


def _id(prefix, *values):
    return prefix + hashlib.sha256("|".join(values).encode()).hexdigest()[:32]


def seed_compliance_knowledge(db, user_id, *, bind_roles=True):
    from core.db.models import UserShadow, UserAgent
    from core.foreign_trade.market_compliance import bundle, render_case
    from core.foreign_trade.review import KnowledgeService
    from core.files.storage import get_storage
    from features.knowledge.models import KBSpace, KBDocument, KBChunk, KBWikiPage
    from features.knowledge.wiki.store import upsert_page
    from prompts.kb_lite_section import invalidate_kb_lite_cache

    uid = str(user_id or "")
    if not uid or not db.query(UserShadow).filter_by(user_id=uid).first():
        raise ValueError("An existing account is required")
    data = bundle()
    version = data["knowledge_version"]
    kb_id = _id("kb_", uid, "sailagent-market-compliance", version)
    space = db.query(KBSpace).filter_by(kb_id=kb_id).first()
    if space is not None and space.user_id != uid:
        raise ValueError("Knowledge space belongs to another account")
    if space is not None and space.deleted_at is not None:
        return {"ok":True, "kb_id":kb_id, "version":version, "documents":[],
                "document_count":0, "page_count":0, "bound_agents":[],
                "mode":"curated_offline", "skipped_space":kb_id,
                "notice":"知识库已由用户删除，本次保留删除状态，不重新创建。"}
    if space is None:
        space = KBSpace(kb_id=kb_id, user_id=uid, name="多国合规案例 · " + version,
            description="美国、欧盟/西班牙、英国、加拿大的官方来源摘要与模拟审稿案例；可追溯原文、无模型依赖。",
            visibility="private", chunk_method="recursive",
            extra_data={"seed_bundle":"sailagent-market-compliance", "seed_version":version,
                        "index_modes":["wiki"], "curated_without_model":True})
        db.add(space)
        db.flush()
    storage = get_storage()
    documents, slugs, skipped_documents, skipped_pages = [], [], [], []
    for rule in data["rules"]:
        text = render_case(rule)
        raw = text.encode("utf-8")
        checksum = hashlib.sha256(raw).hexdigest()
        document_id = _id("doc_", uid, version, rule["rule_id"])
        chunk_id = _id("chunk_", document_id, checksum)
        document = db.query(KBDocument).filter_by(document_id=document_id).first()
        if document is not None and document.kb_id == kb_id and document.deleted_at is not None:
            skipped_documents.append(document_id)
            continue
        if document is not None and (document.kb_id != kb_id or document.checksum != checksum):
            raise ValueError("Curated document has changed; preserve it and publish a new bundle version")
        if document is None:
            storage_key = f"knowledge/{uid}/{kb_id}/{document_id}.md"
            storage.upload_bytes(raw, storage_key)
            document = KBDocument(document_id=document_id, kb_id=kb_id, title=rule["title"],
                filename=rule["rule_id"] + ".md", size_bytes=len(raw), mime_type="text/markdown",
                storage_key=storage_key, checksum=checksum, indexing_status="processing",
                extra_data={"seed_bundle":"sailagent-market-compliance", "source_url":rule["source_url"],
                            "verified_at":rule["verified_at"], "curated_without_model":True})
            db.add(document)
            db.flush()
        stored = storage.download_bytes(document.storage_key)
        if hashlib.sha256(stored).hexdigest() != checksum:
            raise ValueError("Stored case source no longer matches its rule bundle")
        chunk = db.query(KBChunk).filter_by(chunk_id=chunk_id).first()
        if chunk is None:
            db.add(KBChunk(chunk_id=chunk_id, kb_id=kb_id, document_id=document_id,
                chunk_index=0, content=text, char_start=0, char_end=len(text),
                tags=[rule["market"], rule["rule_id"], "合规案例"], questions=rule["unknowns"]))
        elif chunk.content != text:
            raise ValueError("Source chunk changed; publish a new version instead of replacing it")
        document.indexing_status = "completed"
        slug = "concept/" + rule["rule_id"].replace(".", "-")
        page = db.query(KBWikiPage).filter_by(kb_id=kb_id, slug=slug).first()
        if page is not None and page.deleted_at is not None:
            skipped_pages.append(slug)
        elif page is None:
            page = upsert_page(db, kb_id, slug=slug, title=rule["title"], page_type="concept",
                content=text, summary=rule["summary"], aliases=[rule["market"], rule["rule_id"]],
                source_refs=[document_id], chunk_refs=[chunk_id], out_links=["index"],
                category_path=[rule["market"]], edit_source="manual", editor_id=uid)
            page.page_metadata = {"curated_without_model":True, "seed_version":version}
        # Existing Wiki text may have been edited by a person. Never replace it.
        documents.append({"document_id":document_id, "rule_id":rule["rule_id"], "checksum":checksum, "slug":slug})
        if page.deleted_at is None:
            slugs.append(slug)
    index = db.query(KBWikiPage).filter_by(kb_id=kb_id, slug="index").first()
    if index is not None and index.deleted_at is not None:
        skipped_pages.append("index")
    elif index is None:
        by_slug = {"concept/" + r["rule_id"].replace(".", "-"):r for r in data["rules"]}
        index = upsert_page(db, kb_id, slug="index", title="多国合规案例索引", page_type="index",
            content="# 多国合规案例\n\n" + data["scope_note"] + "\n\n" +
                "\n".join(f"- [[{slug}|{by_slug[slug]['title']}]]" for slug in slugs),
            summary="四个市场、八个案例；项目整理的官方资料摘要，原文和规则均有版本。",
            source_refs=[d["document_id"] for d in documents],
            chunk_refs=[_id("chunk_", d["document_id"], d["checksum"]) for d in documents],
            out_links=slugs, category_path=[], edit_source="manual", editor_id=uid)
        index.page_metadata = {"curated_without_model":True, "seed_version":version}
    active_docs = db.query(KBDocument).filter_by(kb_id=kb_id).filter(KBDocument.deleted_at.is_(None)).all()
    space.document_count = len(active_docs)
    space.total_size_bytes = sum(doc.size_bytes for doc in active_docs)
    bound = []
    if bind_roles:
        # Use the installer marker, so renamed core roles work and same-name custom roles are untouched.
        keys = {"sales", "procurement", "operations"}
        for role in db.query(UserAgent).filter_by(user_id=uid, owner_type="user").all():
            if (role.extra_config or {}).get("sailagent_core_role") not in keys:
                continue
            if kb_id not in (role.kb_ids or []):
                role.kb_ids = [*(role.kb_ids or []), kb_id]
            bound.append(role.agent_id)
    KnowledgeService(db)._seed()
    db.commit()
    # Keep the desktop capability projection aligned with its authoritative DB row.
    # Repeat even when kb_ids did not change: this repairs a prior partial seed.
    from core.capabilities.agents.edition import UserAgentService
    agent_service = UserAgentService(db)
    for agent_id in bound:
        agent_service._project_to_store(db.get(UserAgent, agent_id))
    invalidate_kb_lite_cache()
    return {"ok":True, "kb_id":kb_id, "version":version, "documents":documents,
            "document_count":len(documents),
            "page_count":db.query(KBWikiPage).filter_by(kb_id=kb_id).filter(KBWikiPage.deleted_at.is_(None)).count(),
            "bound_agents":bound, "skipped_documents":skipped_documents, "skipped_pages":skipped_pages,
            "mode":"curated_offline", "source_sha256":hashlib.sha256(
                json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--app-home", type=Path, required=True)
    p.add_argument("--username", required=True)
    args = p.parse_args()
    home = args.app_home.expanduser().resolve()
    if not (home / "data.db").is_file():
        p.error("Existing app-home and account required")
    from foreign_trade.team import runtime_env
    os.environ.update(runtime_env(home, 3002))
    from features import register_package_sources, register_resource_owners, register_run_capabilities, register_product_tools
    register_package_sources()
    register_resource_owners()
    register_run_capabilities()
    register_product_tools()
    from core.db.engine import SessionLocal
    from core.db.models import UserShadow
    with SessionLocal() as db:
        user = db.query(UserShadow).filter_by(username=args.username).one_or_none()
        if user is None:
            p.error("Existing account not found")
        print(json.dumps(seed_compliance_knowledge(db, user.user_id), ensure_ascii=False))


if __name__ == "__main__":
    main()

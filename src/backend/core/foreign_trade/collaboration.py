"""Owner-scoped role tasks with source freshness and explicit human acceptance.

This coordinates the current user's records. It does not grant team access,
contact assignees, publish products, or send customer messages.
"""
from copy import deepcopy
import hashlib
import html
import json
from uuid import uuid4

from core.db.models.foreign_trade_collaboration import ForeignTradeCollaboration
from core.files.storage import get_storage
from core.foreign_trade.content import ContentPackError, ContentPackService
from core.foreign_trade.inquiry import InquiryError, InquiryService, now_iso


class CollaborationError(Exception):
    def __init__(self, status: int, message: str):
        self.status, self.message = status, message
        super().__init__(message)


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


TASKS = (
    ("sales_requirements", "确认需求和买家资料", "sales", [], ["inquiry"],
     ["保留询盘原文和明确需求", "区分公开买家事实、未知项和模拟交易"]),
    ("procurement_quote", "核对供货条件和模拟报价", "procurement", ["sales_requirements"], ["inquiry", "quote"],
     ["核对当前报价金额、币种和费用范围", "保留运费、供应商和目标市场待确认项"]),
    ("design_assets", "准备产品图片素材", "design", ["sales_requirements"], ["content_pack"],
     ["核对图片来源、署名及实际生成素材", "模拟示意图不得称为实物照片"]),
    ("operations_content", "审阅商品文案与 FAQ", "operations", ["design_assets"], ["content_pack"],
     ["核对当前已确认事实、英文文案和 FAQ", "未提供商务条件不得写成承诺"]),
    ("compliance_review", "审核来源和对外表述", "compliance", ["procurement_quote", "operations_content"],
     ["inquiry", "quote", "content_pack"], ["核对证据、图片许可与模拟标记", "审核完成不代表认证或法规结论通过"]),
    ("sales_handoff", "汇总内部交接草稿", "sales", ["compliance_review"], ["inquiry", "quote", "content_pack"],
     ["核对所有岗位有效验收记录", "列明未确认项与风险，明确未发送和未发布"]),
)
ROLES = {row[2] for row in TASKS}
STATUSES = {"todo", "in_progress", "in_review", "done", "cancelled"}


def _tasks(assignees):
    pending = {
        "sales_requirements": ["实际来信身份、采购意愿和合作关系未核实"],
        "procurement_quote": ["实际供货、库存、运费、运输时效和税费仍待确认"],
        "design_assets": ["模拟几何示意图不构成真实产品外观或结构证据"],
        "operations_content": ["实际售价、库存、保修和销售授权仍待确认"],
        "compliance_review": ["目标市场法规、认证及销售资格尚无最终结论"],
        "sales_handoff": ["本单仅供内部交接，不代表客户已收到或商品已发布"],
    }
    return [{"id": ident, "title": title, "role": role,
             "assignee_label": assignees.get(role, ""), "status": "todo",
             "depends_on": list(deps), "source_keys": list(sources),
             "acceptance_criteria": list(criteria), "result_note": "",
             "unresolved_items": pending[ident], "risks": ["模拟交易与真实公开信息须分别标注"], "review": None}
            for ident, title, role, deps, sources, criteria in TASKS]


def _validate_graph(tasks):
    by_id = {task["id"]: task for task in tasks}
    if len(by_id) != len(tasks):
        raise CollaborationError(422, "任务编号重复")
    visiting, visited = set(), set()
    def walk(key):
        if key in visiting:
            raise CollaborationError(422, "任务依赖不能成环或依赖自身")
        if key in visited:
            return
        visiting.add(key)
        deps = by_id[key]["depends_on"]
        if len(set(deps)) != len(deps) or any(dep not in by_id for dep in deps):
            raise CollaborationError(422, "依赖任务不存在或重复")
        for dep in deps:
            walk(dep)
        visiting.remove(key)
        visited.add(key)
    for key in by_id:
        walk(key)


class CollaborationService:
    def __init__(self, db):
        self.db = db

    def _row(self, user_id, identifier):
        row = self.db.query(ForeignTradeCollaboration).filter_by(
            owner_user_id=str(user_id), collaboration_id=identifier).populate_existing().first()
        if row is None:
            raise CollaborationError(404, "协同单不存在或无权访问")
        return row

    def _raw(self, user_id, identifier):
        row = self._row(user_id, identifier)
        return {**deepcopy(row.payload), "collaboration_id": identifier, "revision": row.revision,
                "created_at": row.created_at, "updated_at": row.updated_at}

    def _load(self, user_id, identifier, revision):
        result = self._raw(user_id, identifier)
        if type(revision) is not int or result["revision"] != revision:
            raise CollaborationError(409, "协同单已更新，请读取最新修订后重试")
        return result

    def _sources(self, user_id, inquiry_id, pack_id, relationship):
        try:
            self.db.expire_all()
            inquiry = InquiryService(self.db).get(user_id, inquiry_id)
            pack = ContentPackService(self.db).get(user_id, pack_id) if pack_id else None
        except (InquiryError, ContentPackError):
            raise CollaborationError(404, "引用资料不存在或无权访问") from None
        business = {key: inquiry.get(key) for key in ("buyer", "raw_inquiry", "items", "destination_country",
            "requested_lead_days", "buyer_card", "is_demo_inquiry")}
        refs = [{"key": "inquiry", "kind": "inquiry", "id": inquiry_id,
                 "revision": inquiry["revision"], "fingerprint": fingerprint(business), "relationship": "transaction"},
                {"key": "quote", "kind": "quote", "id": (inquiry.get("quote") or {}).get("data", {}).get("quote_id", ""),
                 "revision": inquiry.get("quote_revision") or inquiry["revision"],
                 "fingerprint": fingerprint(inquiry.get("quote")), "relationship": "transaction"}]
        if pack:
            refs.append({"key": "content_pack", "kind": "content_pack", "id": pack_id,
                "revision": pack["revision"], "relationship": relationship,
                "fingerprint": fingerprint({key: pack.get(key) for key in ("product_name", "brand", "model",
                    "source_url", "facts", "image_credit", "documents", "outputs", "catalog_binding")})})
        return refs, inquiry, pack

    @staticmethod
    def _binding_valid(inquiry, pack):
        binding = (pack or {}).get("catalog_binding") or {}
        items = inquiry.get("items", [])
        return bool(pack and binding.get("is_simulated") is True and len(items) == 1
                    and items[0]["sku"] == binding.get("sku") == pack.get("model")
                    and binding.get("product_name") == pack.get("product_name")
                    and all(fact in binding.get("allowed_facts", []) for fact in pack.get("facts", [])))

    def _evaluate(self, record, refs, inquiry, pack):
        result = deepcopy(record)
        result["content_preparation"].update(facts_confirmed=bool((pack or {}).get("facts")),
                                             generated=bool((pack or {}).get("outputs")))
        if (pack or {}).get("outputs"):
            result["content_preparation"]["note"] = "当前资料包已生成；岗位验收仍以人工审核记录为准"
        elif (pack or {}).get("facts"):
            result["content_preparation"]["note"] = "当前产品事实已保存，尚需生成本版本资料包"
        current = {ref["key"]: ref for ref in refs}
        stale_keys = {ref["key"] for ref in record["source_refs"]
                      if ref["key"] not in current or ref["fingerprint"] != current[ref["key"]]["fingerprint"]}
        result["source_refs"] = [{**ref, "stale": ref["key"] in stale_keys} for ref in record["source_refs"]]
        by_id = {task["id"]: task for task in result["tasks"]}
        evaluated = set()
        def evaluate(task):
            if task["id"] in evaluated:
                return
            for dep in task["depends_on"]:
                evaluate(by_id[dep])
            task["stale"] = bool(stale_keys.intersection(task["source_keys"])) or any(by_id[d]["stale"] for d in task["depends_on"])
            blockers = []
            if task["stale"]:
                blockers.append("依据已变更，请刷新来源并重新审核")
            for dep in task["depends_on"]:
                if by_id[dep]["status"] != "done" or by_id[dep]["blocked"]:
                    blockers.append("前置任务尚未有效完成：" + by_id[dep]["title"])
            if task["id"] == "sales_requirements":
                if not inquiry.get("raw_inquiry", "").strip() or not inquiry.get("items") or not inquiry.get("destination_country"):
                    blockers.append("询盘原文、产品条件或目的国尚未完整")
                if not inquiry.get("buyer_card"):
                    blockers.append("尚未核验买家公开资料；核验失败时需保留未知状态")
            if "quote" in task["source_keys"] and not (inquiry.get("quote") or {}).get("ok"):
                blockers.append("尚无当前有效模拟报价")
            if "content_pack" in task["source_keys"]:
                if not pack:
                    blockers.append("尚未关联产品资料包")
                elif record["content_relationship"] == "transaction" and not self._binding_valid(inquiry, pack):
                    blockers.append("资料包与询盘模拟产品不一致，不能作为本交易规格或报价依据")
                elif not pack.get("outputs"):
                    blockers.append("产品事实尚未确认或当前资料包尚未生成")
            if task["id"] == "design_assets" and pack and pack.get("outputs"):
                if not any(doc["kind"] == "image" for doc in pack.get("documents", [])) or not pack.get("image_credit"):
                    blockers.append("缺少图片或图片来源说明")
                if not any(a.get("kind") in {"square", "landscape", "spec"} for a in pack["outputs"].get("assets", [])):
                    blockers.append("当前版本没有实际生成的图片素材")
            if task["id"] == "operations_content" and pack and pack.get("outputs"):
                output = pack["outputs"]
                if not output.get("listing") or not output.get("faq"):
                    blockers.append("当前版本缺少商品文案或 FAQ")
                if output.get("method") == "template" and any(any(ord(c) > 127 for c in f["value"]) for f in pack.get("facts", [])):
                    blockers.append("基础模板未完成英文翻译，需核对后重新生成")
            task["blockers"] = list(dict.fromkeys(blockers))
            task["blocked"] = bool(blockers)
            evaluated.add(task["id"])
        for task in result["tasks"]:
            evaluate(task)
        result["workflow_status"] = {"total_tasks": len(result["tasks"]),
            "done_tasks": sum(t["status"] == "done" and not t["blocked"] for t in result["tasks"]),
            "blocked_tasks": sum(t["blocked"] for t in result["tasks"]),
            "stale_tasks": sum(t["stale"] for t in result["tasks"]),
            "ready_for_handoff": all(t["status"] == "done" and not t["blocked"] for t in result["tasks"])}
        return result

    def get(self, user_id, identifier):
        record = self._raw(user_id, identifier)
        return self._evaluate(record, *self._sources(user_id, record["inquiry_id"], record["content_pack_id"], record["content_relationship"]))

    def list(self, user_id, limit=100):
        rows = self.db.query(ForeignTradeCollaboration).filter_by(owner_user_id=str(user_id)).order_by(
            ForeignTradeCollaboration.updated_at.desc(), ForeignTradeCollaboration.collaboration_id).limit(limit).all()
        return [self.get(user_id, row.collaboration_id) for row in rows]

    def create(self, user_id, values):
        user_id = str(user_id)
        pack_id = values.get("content_pack_id", "")
        relationship = values.get("content_relationship", "independent_reference")
        refs, inquiry, pack = self._sources(user_id, values["inquiry_id"], pack_id, relationship)
        keys, prepared = [], False
        try:
            if not pack_id and values.get("prepare_catalog_content", True):
                from core.foreign_trade.catalog_content import create_catalog_content
                try:
                    pack_id, keys = create_catalog_content(self.db, user_id, inquiry)
                except ValueError as exc:
                    raise CollaborationError(422, str(exc)) from None
                relationship, prepared = "transaction", True
                refs, inquiry, pack = self._sources(user_id, values["inquiry_id"], pack_id, relationship)
            if relationship == "transaction" and pack and not self._binding_valid(inquiry, pack):
                raise CollaborationError(422, "交易资料必须来自同一模拟 SKU 的目录绑定；外部产品只能作为独立参考")
            timestamp, identifier = now_iso(), "collab_" + uuid4().hex
            record = {"document_type": "foreign_trade_collaboration", "document_version": 1,
                "title": values.get("title") or "跨岗位协同单", "scope": "current_user_role_coordination",
                "is_demo_transaction": True, "source_note": inquiry["source_note"] + " 本单仅为当前账号下的岗位协同记录，未向负责人发送通知。",
                "inquiry_id": values["inquiry_id"], "content_pack_id": pack_id,
                "content_relationship": relationship, "source_refs": refs,
                "content_preparation": {"created": prepared, "pack_id": pack_id,
                    "facts_confirmed": False if prepared else bool((pack or {}).get("facts")),
                    "generated": False if prepared else bool((pack or {}).get("outputs")),
                    "note": "仅导入模拟目录候选事实和几何示意图；请人工确认后生成" if prepared else "使用已有资料或等待补充"},
                "tasks": _tasks(values.get("assignees", {})),
                "external_actions": {"messages_sent": False, "published": False},
                "history": [{"event": "created", "at": timestamp, "revision": 1, "actor_user_id": user_id}]}
            if relationship == "independent_reference" and pack:
                record["source_note"] += " 产品资料为独立参考，不构成本询盘产品规格或报价依据。"
            self.db.add(ForeignTradeCollaboration(collaboration_id=identifier, owner_user_id=user_id,
                revision=1, payload=record, created_at=timestamp, updated_at=timestamp))
            self.db.commit()
            return self.get(user_id, identifier)
        except Exception:
            self.db.rollback()
            for key in keys:
                try:
                    get_storage().delete(key)
                except Exception:
                    pass
            raise

    def _save(self, user_id, identifier, revision, record, event, task_id=None):
        timestamp = now_iso()
        record = deepcopy(record)
        record["history"].append({"event": event, "at": timestamp, "revision": revision + 1,
                                  "actor_user_id": str(user_id), **({"task_id": task_id} if task_id else {})})
        for key in ("collaboration_id", "revision", "created_at", "updated_at", "workflow_status"):
            record.pop(key, None)
        for task in record["tasks"]:
            for key in ("stale", "blocked", "blockers"):
                task.pop(key, None)
        for ref in record["source_refs"]:
            ref.pop("stale", None)
        count = self.db.query(ForeignTradeCollaboration).filter_by(owner_user_id=str(user_id),
            collaboration_id=identifier, revision=revision).update({"revision": revision + 1,
            "payload": record, "updated_at": timestamp}, synchronize_session=False)
        if count != 1:
            self.db.rollback()
            raise CollaborationError(409, "协同单已更新，请读取最新修订后重试")
        self.db.commit()
        self.db.expire_all()
        return self.get(user_id, identifier)

    @staticmethod
    def _invalidate(record, changed_ids):
        affected = set(changed_ids)
        while True:
            expanded = affected | {t["id"] for t in record["tasks"] if affected.intersection(t["depends_on"])}
            if expanded == affected:
                break
            affected = expanded
        for task in record["tasks"]:
            if task["id"] in affected:
                if task["review"]:
                    record["history"].append({"event": "acceptance_superseded", "at": now_iso(),
                        "revision": record["revision"] + 1, "actor_user_id": task["review"]["actor_user_id"],
                        "task_id": task["id"], "previous_review": deepcopy(task["review"])})
                task["review"] = None
                if task["status"] == "done":
                    task["status"] = "in_review"

    def update_task(self, user_id, identifier, revision, task_id, values):
        record = self._load(user_id, identifier, revision)
        task = next((t for t in record["tasks"] if t["id"] == task_id), None)
        if task is None:
            raise CollaborationError(404, "任务不存在")
        allowed = {"assignee_label", "status", "result_note", "unresolved_items", "risks", "depends_on"}
        if set(values) - allowed or values.get("status") == "done":
            raise CollaborationError(422, "完成任务必须明确人工审核，不能直接设置 done")
        if "status" in values and values["status"] not in STATUSES:
            raise CollaborationError(422, "任务状态无效")
        mandatory = set(next(row[3] for row in TASKS if row[0] == task_id))
        if "depends_on" in values and not mandatory.issubset(values["depends_on"]):
            raise CollaborationError(422, "不能移除模板必需的前置任务")
        if any(task.get(k) != v for k, v in values.items()):
            self._invalidate(record, {task_id})
        task.update(deepcopy(values))
        _validate_graph(record["tasks"])
        return self._save(user_id, identifier, revision, record, "task_updated", task_id)

    def refresh_sources(self, user_id, identifier, revision):
        record = self._load(user_id, identifier, revision)
        refs, inquiry, pack = self._sources(user_id, record["inquiry_id"], record["content_pack_id"], record["content_relationship"])
        current = self._evaluate(record, refs, inquiry, pack)
        self._invalidate(record, {t["id"] for t in current["tasks"] if t["stale"]})
        record["source_refs"] = refs
        return self._save(user_id, identifier, revision, record, "sources_refreshed")

    def link_content(self, user_id, identifier, revision, pack_id, relationship):
        record = self._load(user_id, identifier, revision)
        refs, inquiry, pack = self._sources(user_id, record["inquiry_id"], pack_id, relationship)
        if relationship == "transaction" and not self._binding_valid(inquiry, pack):
            raise CollaborationError(422, "交易资料必须来自同一模拟 SKU；外部产品只能作为独立参考")
        current = self._evaluate(record, refs, inquiry, pack)
        self._invalidate(record, {t["id"] for t in current["tasks"] if t["stale"] or "content_pack" in t["source_keys"]})
        record.update(content_pack_id=pack_id, content_relationship=relationship, source_refs=refs)
        record["content_preparation"].update(created=False, pack_id=pack_id, note="已关联现有资料包，受影响任务须重新审核")
        record["source_note"] = inquiry["source_note"] + " 本单仅为当前账号下的岗位协同记录，未向负责人发送通知。"
        if relationship == "independent_reference":
            record["source_note"] += " 产品资料为独立参考，不构成本询盘产品规格或报价依据。"
        return self._save(user_id, identifier, revision, record, "content_linked")

    def review(self, user_id, identifier, revision, task_id, confirmed, review_note):
        record = self._load(user_id, identifier, revision)
        if confirmed is not True or not isinstance(review_note, str) or not review_note.strip():
            raise CollaborationError(422, "请人工核对验收条件后明确确认，并记录审核依据")
        sources = self._sources(user_id, record["inquiry_id"], record["content_pack_id"], record["content_relationship"])
        current = self._evaluate(record, *sources)
        task = next((t for t in current["tasks"] if t["id"] == task_id), None)
        if task is None:
            raise CollaborationError(404, "任务不存在")
        if task["blocked"]:
            raise CollaborationError(409, "；".join(task["blockers"]))
        if task["status"] != "in_review" or not task["result_note"].strip() or not task["assignee_label"].strip():
            raise CollaborationError(422, "请先填写负责人和结果依据，将任务提交为待审核")
        if "content_pack" in task["source_keys"] and sources[2]:
            self._verify_files(user_id, sources[2])
        target = next(t for t in record["tasks"] if t["id"] == task_id)
        target.update(status="done", review={"actor_user_id": str(user_id), "at": now_iso(), "note": review_note.strip()})
        return self._save(user_id, identifier, revision, record, "task_reviewed", task_id)

    def _verify_files(self, user_id, pack):
        try:
            for document in pack.get("documents", []):
                ContentPackService(self.db).read_file(user_id, pack["pack_id"], document["file_id"])
        except ContentPackError:
            raise CollaborationError(409, "产品原文件已变化或不可访问，请重新导入资料并审核") from None

    def handoff(self, user_id, identifier, revision, kind):
        # Keep the exact revision the caller requested throughout rendering. A
        # second get here could replace an accepted snapshot with a newer review.
        snapshot = self._load(user_id, identifier, revision)
        sources = self._sources(user_id, snapshot["inquiry_id"], snapshot["content_pack_id"], snapshot["content_relationship"])
        record = self._evaluate(snapshot, *sources)
        if not record["workflow_status"]["ready_for_handoff"]:
            raise CollaborationError(409, "所有任务须按当前依据完成人工验收后才能导出交接稿")
        if sources[2]:
            self._verify_files(user_id, sources[2])
        def checked_result(payload, mime, filename):
            # Source/file checks and rendering can take time. Recheck both the
            # caller's version and its acceptance immediately before returning,
            # but never export data from this newer read.
            current = self.get(user_id, identifier)
            if current["revision"] != revision:
                raise CollaborationError(409, "协同单已更新，请读取最新修订后重新下载")
            if not current["workflow_status"]["ready_for_handoff"]:
                raise CollaborationError(409, "交接依据已变化，请按当前版本重新审核后下载")
            return payload, mime, filename
        if kind == "json":
            return checked_result(json.dumps(record, ensure_ascii=False, indent=2).encode(), "application/json", identifier + ".json")
        if kind != "md":
            raise CollaborationError(422, "仅支持 md 或 json 交接稿")
        # Treat notes as text even when the downloaded Markdown is rendered elsewhere.
        def quoted(text):
            value = html.escape(str(text).replace("\n", " ").replace("\r", " "), quote=True)
            for char in ("\\", "`", "*", "_", "[", "]", "(", ")", "#", "!"):
                value = value.replace(char, "\\" + char)
            return value
        lines = ["# 内部跨岗位交接草稿", "", quoted(record["title"]), "", record["source_note"],
                 "", "未发送外部消息；未发布商品。岗位姓名仅为当前账号的责任记录。", "", "## 版本依据"]
        for ref in record["source_refs"]:
            lines.append(f"- {ref['kind']} {ref['id']} / revision {ref['revision']} / {ref['relationship']} / SHA256 {ref['fingerprint']}")
        for task in record["tasks"]:
            lines.extend(["", "## " + task["title"], "", "负责人：" + quoted(task["assignee_label"]),
                          "结果：" + quoted(task["result_note"]), "审核：" + quoted(task["review"]["note"]),
                          "未确认项：" + quoted("；".join(task["unresolved_items"]) or "未记录，仍须按来源范围使用"),
                          "风险：" + quoted("；".join(task["risks"]) or "未记录新增风险，不代表交易或合规保证")])
        return checked_result(("\n".join(lines) + "\n").encode(), "text/markdown; charset=utf-8", identifier + ".md")

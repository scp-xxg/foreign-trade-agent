"""Native, run-bound foreign-trade tools; identity is never a model argument.

Only the agent factory/plugin activation may register these closures after plugin
visibility/activation checks. Business records and uploaded artifacts retain
service-level ownership checks and optimistic revisions on every call.
"""

import asyncio
from copy import deepcopy
from importlib.resources import files
import json
from typing import Literal

from agentscope.message import TextBlock
from agentscope.tool._response import ToolChunk as ToolResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, ValidationError

from core.db.engine import SessionLocal
from core.db.models import Artifact, ChatMessage, ChatSession
from core.foreign_trade.inquiry import InquiryError, InquiryService
from core.foreign_trade.content import ContentPackError, ContentPackService, MAX_UPLOAD, demo_file
from core.files.storage import get_storage
from api.routes.v1.foreign_trade import (
    CreateInquiry, UpdateInquiry, RevisionRequest, CreateFollowup, UpdateFollowup,
)
from api.routes.v1.foreign_trade_content import CreatePack, UpdatePack, GeneratePack


class EmptyData(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ListData(EmptyData):
    limit: StrictInt = Field(default=20, ge=1, le=50)


class GenerateData(EmptyData):
    generation_mode: Literal["ai", "template"] = "ai"


class FollowupData(UpdateFollowup):
    task_id: str = Field(min_length=1, max_length=64)


def _response(payload: dict) -> ToolResponse:
    return ToolResponse(content=[TextBlock(type="text", text=json.dumps(payload, ensure_ascii=False))])


def _success(data, **extra):
    return {"ok": True, "data": data, "errors": [], "warnings": [], **extra}


def _failure(exc: Exception) -> dict:
    from core.llm import foreign_trade_plugin
    skill_error = getattr(foreign_trade_plugin, "TradeSkillRequired", None)
    if skill_error is not None and isinstance(exc, skill_error):
        return {"ok": False, "status": 409, "errors": [{"code": "skill_not_loaded", "message": str(exc)}], "warnings": []}
    if isinstance(exc, PermissionError):
        return {"ok": False, "status": 403, "errors": [{"code": "plugin_unavailable", "message": "外贸插件已停用、卸载或无权使用，请刷新插件状态。"}], "warnings": []}
    if isinstance(exc, (InquiryError, ContentPackError)):
        problems = [{"code": "business_error", "message": str(exc)}]
        details = getattr(exc, "details", None)
        if isinstance(details, dict) and isinstance(details.get("errors"), list):
            problems.extend({"code": item.get("code", "validation"), "message": item.get("message", "条件无效")}
                            for item in details["errors"][:10] if isinstance(item, dict))
        return {"ok": False, "status": exc.status, "errors": problems, "warnings": []}
    if isinstance(exc, ValidationError):
        # Never echo ValidationError.input, raw request values or provider exceptions.
        fields = [".".join(str(part) for part in error["loc"]) for error in exc.errors()]
        return {"ok": False, "status": 422, "errors": [{"code": "invalid_input", "message": "参数无效，请核对字段：" + ", ".join(fields)}], "warnings": []}
    return {"ok": False, "status": 500, "errors": [{"code": "internal_error", "message": "本次操作未完成，请刷新业务记录后重试。"}], "warnings": []}


def _assert_available(user_id: str, install_id: str):
    from core.llm.foreign_trade_plugin import assert_trade_plugin_available
    assert_trade_plugin_available(user_id, install_id)


def _data(data):
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise InquiryError(422, "data 必须为对象")
    return data


def _revision(revision):
    return RevisionRequest.model_validate({"revision": revision}).revision


def _with_revision(data, revision):
    data = _data(data)
    if "revision" in data:
        raise InquiryError(422, "revision 请只在工具顶层提供")
    return {**data, "revision": revision}


def _workflow_status(record: dict):
    return {"buyer_verification": (record.get("buyer_card") or {}).get("status", "not_checked"),
            "quote_present": bool(record.get("quote") and record["quote"].get("ok")),
            "drafts_present": bool(record.get("drafts") and not record["drafts"].get("stale")),
            "drafts_stale": bool(record.get("drafts") and record["drafts"].get("stale")),
            "pending_followups": sum(task["status"] == "pending" for task in record.get("followups", []))}


def _inquiry_view(record: dict):
    result = deepcopy(record)
    result["raw_inquiry"] = result.get("raw_inquiry", "")[:12000]
    result["raw_inquiry_truncated"] = len(record.get("raw_inquiry", "")) > 12000
    result["history"] = [{key: value for key, value in event.items() if key != "quote"}
                         for event in result.get("history", [])[-12:]]
    result["auxiliary_view"] = "询盘工作台"
    result["workflow_status"] = _workflow_status(record)
    return result


def _pack_view(record: dict):
    result = deepcopy(record)
    result["raw_text"] = result.get("raw_text", "")[:6000]
    result["raw_text_truncated"] = len(record.get("raw_text", "")) > 6000
    result["documents"] = [{key: value for key, value in doc.items() if key not in {"text", "sha256"}}
                           for doc in result.get("documents", [])]
    result["suggested_facts"] = result.get("suggested_facts", [])[:20]
    result["suggested_facts_total"] = len(record.get("suggested_facts", []))
    result["suggested_facts_truncated"] = len(record.get("suggested_facts", [])) > 20
    result["auxiliary_view"] = "商品资料工作台"
    if record.get("outputs"):
        output = record["outputs"]
        return {
            "document_type": "foreign_trade_content_pack", "document_version": 1,
            "pack_id": record["pack_id"], "revision": record["revision"], "title": record["title"],
            "product_name": record["product_name"], "generated_at": output["generated_at"],
            "not_published": True, "assets": deepcopy(output.get("assets", [])),
            "listing": deepcopy(output.get("listing", {})), "faq": deepcopy(output.get("faq", [])),
            "method": output.get("method", "template"), "generation_mode": output.get("generation_mode", "ai"),
            "warnings": deepcopy(output.get("warnings", [])),
            "facts": deepcopy(record["facts"]), "image_credit": record["image_credit"],
            "source_url": record["source_url"], "auxiliary_view": result["auxiliary_view"],
        }
    return result


def _attached_file_bytes(db, *, user_id: str, chat_id: str | None, file_id: str):
    if not chat_id:
        raise ContentPackError(422, "导入附件需要当前聊天，请先在聊天中上传或引用文件")
    chat = db.query(ChatSession.chat_id).filter_by(chat_id=chat_id, user_id=user_id).first()
    if chat is None:
        raise ContentPackError(404, "当前聊天不存在或无权访问")
    artifact = db.query(Artifact).filter_by(artifact_id=file_id, user_id=user_id).first()
    if artifact is None or artifact.deleted_at is not None:
        raise ContentPackError(404, "附件不存在或无权访问")
    attached = artifact.chat_id == chat_id
    if not attached:
        # MySpace imports keep their original chat_id; allow explicit references
        # in this authenticated conversation, never all of the user's files.
        messages = db.query(ChatMessage.extra_data).filter_by(chat_id=chat_id).order_by(
            ChatMessage.chat_seq.desc(),
        ).limit(500).all()
        for (extra,) in messages:
            for key in ("attachments", "artifacts"):
                refs = (extra or {}).get(key) or []
                if isinstance(refs, list) and any(isinstance(ref, dict) and ref.get("file_id") == file_id for ref in refs):
                    attached = True
                    break
            if attached:
                break
    if not attached:
        raise ContentPackError(404, "该文件未在当前聊天中上传或引用，请先添加附件")
    if not 0 < artifact.size_bytes <= MAX_UPLOAD:
        raise ContentPackError(413, "附件为空或超过单文件 8 MiB 限制")
    content = get_storage().download_bytes(artifact.storage_key)
    if not content or len(content) > MAX_UPLOAD:
        raise ContentPackError(413, "附件为空或超过单文件 8 MiB 限制")
    return artifact.filename, content


def register_foreign_trade_tools(toolkit, *, user_id: str, chat_id: str | None, install_id: str, require_skill=None) -> list[str]:
    """Capture authenticated identity; no HTTP identity header or model-owned ID."""
    if not user_id or not install_id:
        return []
    actor, conversation, installation = str(user_id), str(chat_id) if chat_id else None, str(install_id)

    async def trade_inquiry(
        action: Literal["list", "get", "create", "update", "verify_buyer", "interpret", "draft", "add_followup", "update_followup", "mark_replied", "resume_followups"],
        inquiry_id: str = "", revision: int | None = None, data: dict | None = None,
    ) -> ToolResponse:
        """处理当前用户的买家背调、询盘、回复草稿和跟进待办；不发送外部消息。

        create 的 data 为 title/buyer/raw_inquiry/items/destination_country/requested_lead_days/is_demo_inquiry。
        buyer 必须是对象 {company_name,website,email,country}，不能写成字符串或混入title；未知值留空，不代表已核验。
        完整示例 data={"title":"办公用品询盘","buyer":{"company_name":"Buyer Ltd","website":"","email":"","country":""},"raw_inquiry":"DESK-001 500 units standard packaging to Spain","items":[{"sku":"DESK-001","quantity":500,"custom_packaging":false}],"destination_country":"Spain"}。
        items 每项必须显式有 sku、quantity、custom_packaging。先 interpret 提取建议、用户确认后 update。
        所有现有记录的写操作必须携带最近回执的 inquiry_id 和 revision。
        add_followup data={title,due_at(带时区ISO),timezone}；update_followup data={task_id,status:completed|cancelled}。
        verify_buyer/get/draft/interpret/mark_replied/resume_followups 无额外 data。
        list data 可含 limit。价格计算使用独立 trade_calculate_quote；普通查询可用现有产品查询工具。
        """
        try:
            _assert_available(actor, installation)
            if require_skill is not None:
                require_skill("buyer-inquiry-followup")
            payload = _data(data)
            with SessionLocal() as db:
                service = InquiryService(db)
                if action == "list":
                    request = ListData.model_validate(payload)
                    result = []
                    for row in service.list(actor, request.limit):
                        summary = {k: row[k] for k in ("id", "revision", "title", "buyer", "updated_at", "replied_at")}
                        pending = [task for task in row.get("followups", []) if task["status"] == "pending"]
                        summary["pending_followups"] = [{key: task[key] for key in ("id", "title", "due_at", "timezone", "is_due")} for task in pending[:20]]
                        summary["pending_followups_total"] = len(pending)
                        summary["pending_followups_truncated"] = len(pending) > 20
                        result.append(summary)
                    return _response(_success(result))
                if action == "create":
                    request = CreateInquiry.model_validate(payload)
                    result = service.create(actor, request.model_dump())
                elif action == "get":
                    EmptyData.model_validate(payload)
                    result = service.get(actor, inquiry_id)
                elif action == "update":
                    request = UpdateInquiry.model_validate(_with_revision(payload, revision))
                    result = service.update(actor, inquiry_id, request.revision,
                                            request.model_dump(exclude_unset=True, exclude={"revision"}))
                elif action == "add_followup":
                    request = CreateFollowup.model_validate(_with_revision(payload, revision))
                    result = service.create_followup(actor, inquiry_id, request.revision, request.title, request.due_at, request.timezone)
                elif action == "update_followup":
                    request = FollowupData.model_validate(_with_revision(payload, revision))
                    result = service.update_followup(actor, inquiry_id, request.revision, request.task_id, request.status)
                elif action in {"verify_buyer", "interpret", "draft", "mark_replied", "resume_followups"}:
                    EmptyData.model_validate(payload)
                    rev = _revision(revision)
                    if action == "verify_buyer":
                        result = await service.verify(actor, inquiry_id, rev)
                    elif action == "interpret":
                        from core.foreign_trade.ai import interpret_inquiry
                        from foreign_trade.engine import search_products
                        record = service._load(actor, inquiry_id, rev)
                        proposal = await interpret_inquiry(record["raw_inquiry"], search_products(limit=50)["data"]["products"])
                        db.expire_all()
                        service._load(actor, inquiry_id, rev)
                        return _response(_success({"inquiry_id": inquiry_id, "revision": rev, **proposal}))
                    else:
                        result = getattr(service, action)(actor, inquiry_id, rev)
                else:
                    raise InquiryError(422, "不支持的询盘操作")
                return _response(_success(_inquiry_view(result)))
        except Exception as exc:
            return _response(_failure(exc))

    async def trade_calculate_quote(inquiry_id: str, revision: int) -> ToolResponse:
        """为当前用户已确认的询盘重新计算报价；返回可下载PDF/Excel的真实报价工具快照。

        必须传最近回执的 inquiry_id 与 revision；MOQ、数量、包装与目的国由报价引擎校验。
        所有目录与价格均为演示数据。改单后必须重算；不得手工拼接金额或下载链接。
        """
        try:
            _assert_available(actor, installation)
            if require_skill is not None:
                require_skill("buyer-inquiry-followup")
            def calculate():
                with SessionLocal() as db:
                    result = InquiryService(db).quote(actor, inquiry_id, _revision(revision))
                    return {**result["quote"], "inquiry_id": result["id"], "revision": result["revision"],
                            "auxiliary_view": "询盘工作台", "workflow_status": _workflow_status(result)}
            return _response(await asyncio.to_thread(calculate))
        except Exception as exc:
            return _response(_failure(exc))

    async def trade_product_content(
        action: Literal["list", "get", "create", "update", "import_files", "load_demo", "generate"],
        pack_id: str = "", revision: int | None = None, data: dict | None = None,
        file_ids: list[str] | None = None, confirmed: bool = False,
    ) -> ToolResponse:
        """从聊天附件制作有来源的商品资料包；仅生成草稿，不发布商品。

        create data={title}；update data可含product_name/brand/model/source_url/raw_text/facts/image_credit/title。
        facts 每项为label/value/source_url，最多20条；必须由用户核对。import_files只接当前聊天附件file_ids，
        不接本地路径、远程URL或身份。load_demo载入固定公开Pi5产品CSV和授权照片，仅形成suggested_facts，
        不自动确认；可省pack_id创建新资料包，已有pack须为空。generate在事实确认后传confirmed=true。
        generate的data仅可含generation_mode:"ai"|"template"，默认ai；用户明确选择本地原文模板才传template，完全不调用模型。
        所有现有资料包写操作需最新revision。get/generate成功回执可显示资料包下载卡。
        """
        try:
            _assert_available(actor, installation)
            if require_skill is not None:
                require_skill("product-content")
            payload = _data(data)
            if action != "import_files" and file_ids:
                raise ContentPackError(422, "file_ids 仅供 import_files 使用")
            if action == "generate":
                mode = GenerateData.model_validate(payload)
                request = GeneratePack.model_validate({"revision": revision, "confirmed": confirmed,
                                                       "generation_mode": mode.generation_mode})
                with SessionLocal() as db:
                    result = await ContentPackService(db).generate(actor, pack_id, request.revision,
                                                                  request.confirmed, request.generation_mode)
                receipt = _pack_view(result)
                return _response(_success(receipt, warnings=receipt.get("warnings", [])))

            def operate():
                with SessionLocal() as db:
                    service = ContentPackService(db)
                    if action == "list":
                        request = ListData.model_validate(payload)
                        return _success([{k: row[k] for k in ("pack_id", "revision", "title", "product_name", "updated_at")}
                                         for row in service.list(actor, request.limit)])
                    if action == "create":
                        request = CreatePack.model_validate(payload)
                        result = service.create(actor, request.title)
                    elif action == "get":
                        EmptyData.model_validate(payload)
                        result = service.get(actor, pack_id)
                    elif action == "update":
                        request = UpdatePack.model_validate(_with_revision(payload, revision))
                        result = service.update(actor, pack_id, request.revision,
                                                request.model_dump(exclude_unset=True, exclude={"revision"}))
                    elif action == "import_files":
                        EmptyData.model_validate(payload)
                        rev = _revision(revision)
                        service._load(actor, pack_id, rev)
                        if not isinstance(file_ids, list) or not 1 <= len(file_ids) <= 10 or not all(isinstance(fid, str) and 0 < len(fid) <= 64 for fid in file_ids) or len(set(file_ids)) != len(file_ids):
                            raise ContentPackError(422, "请提供 1–10 个不重复的当前聊天附件 ID")
                        uploads = [_attached_file_bytes(db, user_id=actor, chat_id=conversation, file_id=fid) for fid in file_ids]
                        # Validate every file before persisting the first one.
                        from core.foreign_trade.content import parse_upload, MAX_FILES, MAX_TOTAL
                        parsed = [parse_upload(name, content) for name, content in uploads]
                        import hashlib
                        current = service.get(actor, pack_id)
                        # Idempotence uses normalized bytes already hashed by the service.
                        # It also covers a retry after the first files committed before a CAS loss.
                        seen = {doc.get("sha256") for doc in current["documents"]}
                        pending, skipped = [], []
                        for source_id, upload, normalized in zip(file_ids, uploads, parsed):
                            digest = hashlib.sha256(normalized["content"]).hexdigest()
                            if digest in seen:
                                skipped.append(source_id)
                            else:
                                pending.append((source_id, upload, normalized))
                                seen.add(digest)
                        if len(current["documents"]) + len(pending) > MAX_FILES or sum(doc["size"] for doc in current["documents"]) + sum(len(item[2]["content"]) for item in pending) > MAX_TOTAL:
                            raise ContentPackError(413, "导入将超过资料包文件数量或总大小限制")
                        result, imported, target_ids = current, [], []
                        for source_id, (name, content_bytes), normalized in pending:
                            try:
                                result = service.upload(actor, pack_id, result["revision"], name, content_bytes)
                                imported.append(source_id)
                                target_ids.append(result["documents"][-1]["file_id"])
                            except Exception as exc:
                                failed = _failure(exc)
                                db.rollback()
                                db.expire_all()
                                try:
                                    latest_revision = service.get(actor, pack_id)["revision"]
                                except Exception:
                                    latest_revision = None
                                failed["data"] = {"pack_id": pack_id, "revision": latest_revision,
                                                  "imported_source_file_ids": imported, "imported_file_ids": target_ids,
                                                  "skipped_source_file_ids": skipped}
                                failed["errors"].append({"code": "check_partial_import", "message": "部分附件可能已导入。请先 get 最新资料包，再继续导入；相同规范化内容会自动跳过。"})
                                return failed
                        receipt = _pack_view(result)
                        receipt["import_summary"] = {"imported_source_file_ids": imported, "imported_file_ids": target_ids,
                                                     "skipped_source_file_ids": skipped}
                        return _success(receipt, warnings=receipt.get("warnings", []))
                    elif action == "load_demo":
                        request = CreatePack.model_validate(payload)
                        metadata = json.loads(files("foreign_trade").joinpath("demo_product", "sources.json").read_text(encoding="utf-8"))
                        demo_csv, _, csv_name = demo_file("csv")
                        demo_image, _, image_name = demo_file("photo")
                        if pack_id:
                            result = service._load(actor, pack_id, _revision(revision))
                            if result["documents"] or result["facts"] or result["product_name"]:
                                raise ContentPackError(409, "示例仅能载入空资料包，请新建资料包以保留已有内容")
                        else:
                            result = service.create(actor, request.title if "title" in payload else "Raspberry Pi 5 公开产品示例")
                        result = service.update(actor, result["pack_id"], result["revision"], {
                            "product_name": metadata["product_name"], "brand": "Raspberry Pi", "model": "Raspberry Pi 5",
                            "source_url": metadata["facts_source"]["url"],
                            "image_credit": metadata.get("derivative_image_credit") or metadata["image_credit"],
                        })
                        result = service.upload(actor, result["pack_id"], result["revision"], csv_name, demo_csv)
                        result = service.upload(actor, result["pack_id"], result["revision"], image_name, demo_image)
                    else:
                        raise ContentPackError(422, "不支持的资料包操作")
                    receipt = _pack_view(result)
                    return _success(receipt, warnings=receipt.get("warnings", []))
            return _response(await asyncio.to_thread(operate))
        except Exception as exc:
            return _response(_failure(exc))

    async def trade_save_inquiry(
        inquiry_id: str = "", revision: int | None = None, title: str | None = None,
        company_name: str | None = None, website: str | None = None,
        email: str | None = None, country: str | None = None, raw_inquiry: str | None = None,
        sku: str | None = None, quantity: StrictInt | None = None,
        custom_packaging: StrictBool | None = None, destination_country: str | None = None,
        requested_lead_days: StrictInt | None = None,
    ) -> ToolResponse:
        """用明确字段新建或修改单SKU询盘，优先用于聊天中的普通保存需求。

        示例：title="办公用品询盘",company_name="LYRECO",website="https://www.lyreco.com/group/",
        raw_inquiry="DESK-001 500件标准包装发西班牙",sku="DESK-001",quantity=500,
        custom_packaging=false,destination_country="Spain"。不需要构造嵌套data或buyer JSON。
        新建不传inquiry_id；修改传最近回执的inquiry_id/revision，仅改本次明确提供的字段。
        未知字段省略，绝不默认数量或包装；原有多SKU询盘修改产品行必须用trade_inquiry update。
        本工具只保存，不自动核验买家、计算报价、生成回复或安排跟进。
        """
        try:
            _assert_available(actor, installation)
            if require_skill is not None:
                require_skill("buyer-inquiry-followup")
            existing = None
            if inquiry_id:
                with SessionLocal() as db:
                    existing = InquiryService(db)._load(actor, inquiry_id, _revision(revision))
            values = {key: value for key, value in {
                "title": title, "raw_inquiry": raw_inquiry, "destination_country": destination_country,
                "requested_lead_days": requested_lead_days,
            }.items() if value is not None}
            buyer_changes = {key: value for key, value in {"company_name": company_name, "website": website,
                             "email": email, "country": country}.items() if value is not None}
            if buyer_changes:
                values["buyer"] = {**((existing or {}).get("buyer") or {}), **buyer_changes}
            item_changes = {key: value for key, value in {"sku": sku, "quantity": quantity,
                            "custom_packaging": custom_packaging}.items() if value is not None}
            if item_changes:
                previous = (existing or {}).get("items") or []
                if len(previous) > 1:
                    raise InquiryError(422, "原询盘包含多个SKU，不能用单SKU工具覆盖产品行；请用 trade_inquiry(action=update) 提供完整items。")
                item = {**(previous[0] if previous else {}), **item_changes}
                missing = [key for key in ("sku", "quantity", "custom_packaging") if key not in item]
                if missing:
                    raise InquiryError(422, "产品行缺少明确条件：" + ", ".join(missing) + "。请先澄清；也可暂不传产品行字段，仅保存询盘原文。")
                values["items"] = [item]
            if existing:
                return await trade_inquiry("update", inquiry_id=inquiry_id, revision=revision, data=values)
            return await trade_inquiry("create", data=values)
        except Exception as exc:
            return _response(_failure(exc))

    def unpack_response(response):
        block = response.content[0]
        return json.loads(block["text"] if isinstance(block, dict) else block.text)

    async def trade_import_product(
        file_ids: list[str], title: str = "", product_name: str = "", brand: str = "", model: str = "",
        source_url: str = "", image_credit: str = "", pack_id: str = "", revision: int | None = None,
    ) -> ToolResponse:
        """把当前聊天附件导入商品资料包，使用平铺字段，无需手写嵌套JSON。

        file_ids为当前聊天已上传或引用的文件ID；不接受路径/URL。可同时填写产品名、品牌、型号、
        来源链接及图片署名；已有资料包传pack_id和最新revision，空字符串表示不修改已有信息。
        返回suggested_facts候选事实，尚未人工确认，也不会生成素材。随后先展示事实摘要，
        用户确认后用trade_confirm_product_facts，再用trade_product_content generate。
        """
        prepared = None
        try:
            _assert_available(actor, installation)
            if require_skill is not None:
                require_skill("product-content")
            metadata = {key: value for key, value in {"title": title, "product_name": product_name,
                        "brand": brand, "model": model, "source_url": source_url, "image_credit": image_credit}.items()
                        if value != ""}
            # Validate all flat inputs before creating a record.
            UpdatePack.model_validate({"revision": 1, **metadata})
            if not isinstance(file_ids, list) or not 1 <= len(file_ids) <= 10 or not all(isinstance(fid, str) and 0 < len(fid) <= 64 for fid in file_ids) or len(set(file_ids)) != len(file_ids):
                raise ContentPackError(422, "请提供 1–10 个不重复的当前聊天附件ID")
            def preflight():
                from core.foreign_trade.content import parse_upload
                with SessionLocal() as db:
                    if pack_id:
                        ContentPackService(db)._load(actor, pack_id, _revision(revision))
                    for fid in file_ids:
                        name, payload = _attached_file_bytes(db, user_id=actor, chat_id=conversation, file_id=fid)
                        parse_upload(name, payload)
            await asyncio.to_thread(preflight)
            if pack_id:
                prepared = {"pack_id": pack_id, "revision": _revision(revision)}
            else:
                created = unpack_response(await trade_product_content("create", data={"title": title or "新品资料包"}))
                if not created.get("ok"):
                    return _response(created)
                prepared = created["data"]
            if metadata:
                updated = unpack_response(await trade_product_content("update", pack_id=prepared["pack_id"],
                                          revision=prepared["revision"], data=metadata))
                if not updated.get("ok"):
                    updated.setdefault("data", {"pack_id": prepared["pack_id"], "revision": prepared["revision"]})
                    updated["errors"].append({"code": "get_latest_pack", "message": "请先 get 最新资料包再重试；已创建的资料包保留。"})
                    return _response(updated)
                prepared = updated["data"]
            imported = unpack_response(await trade_product_content("import_files", pack_id=prepared["pack_id"],
                                       revision=prepared["revision"], file_ids=file_ids))
            if not imported.get("ok"):
                imported.setdefault("data", {"pack_id": prepared["pack_id"], "revision": prepared["revision"]})
                imported["errors"].append({"code": "get_latest_pack", "message": "资料包已准备，附件可能尚未全部导入；请先 get 最新记录，重试会跳过相同文件内容。"})
            return _response(imported)
        except Exception as exc:
            failed = _failure(exc)
            if prepared:
                failed["data"] = {"pack_id": prepared["pack_id"], "revision": prepared["revision"]}
                failed["errors"].append({"code": "get_latest_pack", "message": "部分准备步骤可能已成功，请先 get 最新资料包后重试。"})
            return _response(failed)

    async def trade_confirm_product_facts(
        pack_id: str, revision: int, confirmed: StrictBool, fact_indices: list[int] | None = None,
        product_name: str | None = None, brand: str | None = None, model: str | None = None,
        source_url: str | None = None, image_credit: str | None = None,
    ) -> ToolResponse:
        """用户明确确认后，原样采用资料包候选事实，避免重写整份事实JSON。

        先展示suggested_facts和图片来源，用户确认后传confirmed=true。fact_indices为1-based序号，
        如[1,2,4]；省略表示采用全部候选，最多20条且不能重复。可同时补产品名/品牌/型号/来源/图片署名。
        本工具精确复制原候选事实；事实或元数据变更时旧输出失效，不会自动生成，下一步调用trade_product_content generate。
        """
        try:
            _assert_available(actor, installation)
            if require_skill is not None:
                require_skill("product-content")
            request = GeneratePack.model_validate({"revision": revision, "confirmed": confirmed})
            if request.confirmed is not True:
                raise ContentPackError(422, "必须先向用户展示候选事实并获得明确确认，尚未保存事实")
            with SessionLocal() as db:
                record = ContentPackService(db)._load(actor, pack_id, request.revision)
            candidates = record.get("suggested_facts") or []
            selected = list(range(1, len(candidates) + 1)) if fact_indices is None else fact_indices
            if (not isinstance(selected, list) or not 1 <= len(selected) <= 20 or
                not all(type(index) is int and 1 <= index <= len(candidates) for index in selected) or
                len(set(selected)) != len(selected)):
                raise ContentPackError(422, "请选择1–20个不重复的有效候选事实序号（从1开始）；候选超过20条时请明确选择")
            values = {key: value for key, value in {"product_name": product_name, "brand": brand,
                      "model": model, "source_url": source_url, "image_credit": image_credit}.items()
                      if value is not None}
            values["facts"] = [deepcopy(candidates[index - 1]) for index in selected]
            updated = unpack_response(await trade_product_content("update", pack_id=pack_id,
                                      revision=request.revision, data=values))
            if updated.get("ok"):
                updated["data"]["facts_confirmation"] = {"confirmed": True, "selected_indices": selected,
                                                          "generated": False}
            return _response(updated)
        except Exception as exc:
            return _response(_failure(exc))

    tools = [trade_inquiry, trade_calculate_quote, trade_product_content,
             trade_save_inquiry, trade_import_product, trade_confirm_product_facts]
    from core.llm.factory.tools.definitions import function_tool
    from core.sandbox.permissions.tool_specs import allow_tool

    existing = {tool.name for tool in toolkit}
    if existing.intersection(tool.__name__ for tool in tools):
        raise ValueError("Duplicate foreign-trade tool registration")
    for tool in tools:
        # Identity, revision, skill read and explicit business confirmations are
        # enforced inside these closures; they expose no arbitrary host paths.
        toolkit.append(function_tool(tool, dispatch_spec=allow_tool()))
    from core.llm.tools.foreign_trade_collaboration_tool import register_collaboration_tools

    collaboration = register_collaboration_tools(
        toolkit, user_id=actor, chat_id=chat_id, install_id=installation,
        require_skill=require_skill,
    )
    return [tool.__name__ for tool in tools] + collaboration

"""Authenticated trade-rule review adapter; never publishes or sends content."""
from __future__ import annotations

import asyncio
import json
from typing import Literal
from agentscope.message import TextBlock
from agentscope.tool._response import ToolChunk as ToolResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError


class KnowledgeQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(default="", max_length=300, description="可省略；建议先仅按 channel 获取规则，再使用关键词过滤")
    channel: Literal["alibaba_rfq", "amazon_listing"] | None = Field(default=None, description="可省略，或 alibaba_rfq / amazon_listing")
    category: Literal["platform_rules", "quotation_terms"] | None = Field(default=None, description="可省略，或 platform_rules / quotation_terms；不能使用空字符串或商品类目")
    language: Literal["en", "es"] = "en"
    limit: StrictInt = Field(default=30, ge=1, le=50)
    include_superseded: bool = False


class ReviewListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_type: Literal["inquiry", "content_pack"] | None = None
    source_id: str | None = Field(default=None, max_length=100)
    limit: StrictInt = Field(default=20, ge=1, le=50)


def _validation_feedback(exc: ValidationError) -> list[dict]:
    """Expose declared field paths and public enums, never submitted values."""
    declared = set(KnowledgeQuery.model_fields) | set(ReviewListQuery.model_fields)
    enums = {"channel": ["alibaba_rfq", "amazon_listing"],
             "category": ["platform_rules", "quotation_terms"],
             "language": ["en", "es"], "source_type": ["inquiry", "content_pack"]}
    result = []
    for error in exc.errors(include_input=False, include_context=False, include_url=False):
        location = error.get("loc", ())
        field = location[0] if len(location) == 1 and location[0] in declared else None
        path = "data." + field if field else "data.<unsupported_field>"
        options = enums.get(field, [])
        message = "参数字段 " + path + " 无效"
        if options:
            message += "；可省略，或使用允许值：" + ", ".join(options)
        result.append({"code": "invalid_input", "field": path, "message": message,
                       **({"allowed_values": options} if options else {})})
    return result


def register_review_tools(toolkit, *, user_id: str, chat_id: str | None,
                          install_id: str, require_skill=None) -> list[str]:
    if not user_id or not install_id:
        return []
    actor, installation = str(user_id), str(install_id)

    async def trade_review(action: Literal["knowledge", "review", "get", "list"],
                           review_id: str = "", data: dict | None = None) -> ToolResponse:
        """检索有版本与公开来源的规则，并对本账号真实来源生成本地化草稿校验记录。

        knowledge 的 data 字段均可省略：channel=alibaba_rfq|amazon_listing，
        category 省略或仅用 platform_rules|quotation_terms；不要传空字符串、non_media 或商品类目。
        query 是可省略的关键词过滤，默认空字符串；建议先只传 channel 取当前全部适用规则，
        例如 data={"channel":"amazon_listing"}。零匹配时清空 query 再重试，不自动放宽筛选。
        language=en|es 默认en，limit=1..50 默认30，include_superseded 默认false。
        读取当前规则，不凭模型记忆引用政策；商品类目/站点适用范围见返回规则的 scope_note。
        review data={source_type:inquiry|content_pack,source_id,source_revision,channel:alibaba_rfq|amazon_listing,
        draft:{title,body,bullets:[],item_highlights?,language:en|es,locale},previous_review_id?}。
        先读取来源、按销售RFQ或运营Listing语境生成草稿，再送校验；source_revision必须是真实当前版本。
        每次review新建不可变记录；第二轮带previous_review_id对比风险变化。get/list只读取本人记录。
        响应包含文字批注、风险标记、规则来源和下载身份；未发现问题不等于平台批准或法律认证。
        review/get返回foreign_trade_review时前端自动显示“平台文案审核反馈”卡及认证MD/JSON下载按钮；
        使用真实回执的审核卡下载，不要调用Bash/Write等文件工具重建独立报告或拼接下载地址。
        不发送邮件，不发布商品，不替用户确认未知交易条件。
        """
        from core.db.engine import SessionLocal
        from core.foreign_trade.review import KnowledgeService, ReviewService, ReviewError
        from core.llm.foreign_trade_plugin import assert_trade_plugin_available, TradeSkillRequired

        def response(value):
            return ToolResponse(content=[TextBlock(type="text", text=json.dumps(value, ensure_ascii=False))])
        try:
            assert_trade_plugin_available(actor, installation)
            if action == "review" and require_skill is not None:
                require_skill("localization-review")
            if data is not None and not isinstance(data, dict):
                raise ReviewError(422, "data 必须为对象")
            values = data or {}
            if action != "get" and review_id:
                raise ReviewError(422, "仅 get 使用顶层 review_id；新审阅的 previous_review_id 放在 data 中")
            def operate():
                with SessionLocal() as db:
                    if action == "knowledge":
                        req = KnowledgeQuery.model_validate(values)
                        return KnowledgeService(db).search(actor, **req.model_dump())
                    service = ReviewService(db)
                    if action == "review":
                        return service.create(actor, values)
                    if action == "get":
                        if values or not review_id:
                            raise ReviewError(422, "get 需要 review_id 且不接受 data")
                        return service.get(actor, review_id)
                    if action == "list":
                        req = ReviewListQuery.model_validate(values)
                        return service.list(actor, **req.model_dump())
                    raise ReviewError(422, "不支持的审阅操作")
            result = await asyncio.to_thread(operate)
            warnings = []
            if action == "knowledge" and result["total_matches"] == 0:
                warnings.append("当前筛选没有匹配规则；未自动放宽筛选。请清空 query，并先仅保留 channel 重试（category 可省略，或仅用 platform_rules / quotation_terms）。")
            receipt = {"ok": True, "data": result, "errors": [], "warnings": warnings}
            if action in {"review", "get"} and isinstance(result, dict) and result.get("document_type") == "foreign_trade_review":
                receipt["presentation"] = {"card": "trade_review", "download_formats": ["md", "json"],
                    "instruction": "前端自动显示平台文案审核反馈卡及认证下载按钮。请使用该真实回执渲染的审核卡下载按钮；不要用文件工具重建报告或拼接下载地址。"}
            return response(receipt)
        except TradeSkillRequired as exc:
            return response({"ok": False, "status": 409, "errors": [{"code": "skill_not_loaded", "message": str(exc)}], "warnings": []})
        except PermissionError:
            return response({"ok": False, "status": 403, "errors": [{"code": "plugin_unavailable", "message": "当前外贸插件不可用"}], "warnings": []})
        except ReviewError as exc:
            return response({"ok": False, "status": exc.status, "errors": [{"code": "business_error", "message": exc.message}], "warnings": []})
        except ValidationError as exc:
            return response({"ok": False, "status": 422, "errors": _validation_feedback(exc), "warnings": []})
        except Exception:
            return response({"ok": False, "status": 500, "errors": [{"code": "internal_error", "message": "本次审阅未完成，请读取当前来源后重试"}], "warnings": []})

    from core.llm.factory.tools.definitions import function_tool
    from core.sandbox.permissions.tool_specs import allow_tool
    if any(tool.name == "trade_review" for tool in toolkit):
        raise ValueError("Duplicate trade review tool registration")
    toolkit.append(function_tool(trade_review, dispatch_spec=allow_tool()))
    return ["trade_review"]

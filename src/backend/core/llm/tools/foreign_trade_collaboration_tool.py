"""Plugin-gated current-user collaboration adapter; no outward communication."""
import asyncio
import json
from typing import Literal
from agentscope.message import TextBlock
from agentscope.tool._response import ToolChunk as ToolResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError

from core.db.engine import SessionLocal
from core.foreign_trade.collaboration import CollaborationError, CollaborationService
from api.routes.v1.foreign_trade_collaboration import CreateCollaboration, RevisionRequest, UpdateTask, ReviewTask, LinkContent


class ListData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: StrictInt = Field(default=20, ge=1, le=50)


def register_collaboration_tools(toolkit, *, user_id: str, chat_id: str | None,
                                 install_id: str, require_skill=None) -> list[str]:
    if not user_id or not install_id:
        return []
    actor, installation = str(user_id), str(install_id)

    async def trade_collaboration(action: Literal["list", "get", "create", "update_task", "review", "refresh_sources", "link_content"],
                                  collaboration_id: str = "", revision: int | None = None,
                                  task_id: str = "", data: dict | None = None) -> ToolResponse:
        """当前账号下的业务/采购/美工/运营/合规岗位协同，不发送通知、不共享账号权限。

        create data={title,inquiry_id,content_pack_id?,content_relationship?,prepare_catalog_content?,assignees?}。
        未指定资料包时默认导入同一DESK-001模拟目录候选事实和几何示意图，仍需用户确认后通过商品工具生成。
        外部真实产品资料只能作为independent_reference，不得套用DESK报价。
        link_content data={content_pack_id,content_relationship}关联现有资料包并使相关旧验收失效。
        update_task data={assignee_label,status:todo|in_progress|in_review|cancelled,result_note,unresolved_items:[],risks:[],depends_on:[]}。
        review data={confirmed:true,review_note}：仅在用户看到验收依据并明确确认后调用，不能把任务创建视为完成。
        现有记录写入必须使用最新revision；来源过期先refresh_sources，再重新审阅受影响任务。
        """
        from core.llm.foreign_trade_plugin import assert_trade_plugin_available, TradeSkillRequired
        def response(value):
            return ToolResponse(content=[TextBlock(type="text", text=json.dumps(value, ensure_ascii=False))])
        try:
            assert_trade_plugin_available(actor, installation)
            if action not in {"list", "get"} and require_skill is not None:
                require_skill("cross-role-collaboration")
            if data is not None and not isinstance(data, dict):
                raise CollaborationError(422, "data 必须为对象")
            values = data or {}
            def operate():
                with SessionLocal() as db:
                    svc = CollaborationService(db)
                    if action == "list":
                        return svc.list(actor, ListData.model_validate(values).limit)
                    if action == "create":
                        return svc.create(actor, CreateCollaboration.model_validate(values).model_dump())
                    if action == "get":
                        if values:
                            raise CollaborationError(422, "get 不接受 data 字段")
                        return svc.get(actor, collaboration_id)
                    if "revision" in values or "task_id" in values:
                        raise CollaborationError(422, "revision 和 task_id 只在工具顶层提供")
                    if action == "update_task":
                        req = UpdateTask.model_validate({**values, "revision": revision})
                        return svc.update_task(actor, collaboration_id, req.revision, task_id,
                                               req.model_dump(exclude_unset=True, exclude={"revision"}))
                    if action == "review":
                        req = ReviewTask.model_validate({**values, "revision": revision, "task_id": task_id})
                        return svc.review(actor, collaboration_id, req.revision, req.task_id, req.confirmed, req.review_note)
                    if action == "link_content":
                        req = LinkContent.model_validate({**values, "revision": revision})
                        return svc.link_content(actor, collaboration_id, req.revision, req.content_pack_id, req.content_relationship)
                    if action == "refresh_sources":
                        req = RevisionRequest.model_validate({**values, "revision": revision})
                        return svc.refresh_sources(actor, collaboration_id, req.revision)
                    raise CollaborationError(422, "不支持的协同操作")
            result = await asyncio.to_thread(operate)
            return response({"ok": True, "data": result, "errors": [], "warnings": []})
        except TradeSkillRequired as exc:
            return response({"ok": False, "status": 409, "errors": [{"code": "skill_not_loaded", "message": str(exc)}], "warnings": []})
        except PermissionError:
            return response({"ok": False, "status": 403, "errors": [{"code": "plugin_unavailable", "message": "当前外贸插件不可用"}], "warnings": []})
        except CollaborationError as exc:
            return response({"ok": False, "status": exc.status, "errors": [{"code": "business_error", "message": exc.message}], "warnings": []})
        except ValidationError:
            return response({"ok": False, "status": 422, "errors": [{"code": "invalid_input", "message": "参数无效，请核对字段与当前修订号"}], "warnings": []})
        except Exception:
            return response({"ok": False, "status": 500, "errors": [{"code": "internal_error", "message": "本次操作未完成，请刷新协同记录后重试"}], "warnings": []})

    from core.llm.factory.tools.definitions import function_tool
    from core.sandbox.permissions.tool_specs import allow_tool
    if any(tool.name == "trade_collaboration" for tool in toolkit):
        raise ValueError("Duplicate collaboration tool registration")
    toolkit.append(function_tool(trade_collaboration, dispatch_spec=allow_tool()))
    return ["trade_collaboration"]

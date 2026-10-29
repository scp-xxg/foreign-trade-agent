"""Authenticated current-user role coordination and internal handoff exports."""
from typing import Annotated, Literal
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator
from sqlalchemy.orm import Session

from core.auth.backend import UserContext, get_current_user
from core.db.engine import get_db
from core.infra.responses import created_response, success_response
from core.foreign_trade.collaboration import CollaborationError, CollaborationService, ROLES

router = APIRouter(prefix="/v1/foreign-trade/collaborations", tags=["Foreign trade role coordination"])
ShortText = Annotated[str, Field(max_length=1000)]


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateCollaboration(StrictRequest):
    title: str = Field(default="跨岗位协同单", min_length=1, max_length=200)
    inquiry_id: str = Field(pattern=r"^inq_[a-f0-9]{32}$")
    content_pack_id: str = Field(default="", max_length=64)
    content_relationship: Literal["transaction", "independent_reference"] = "independent_reference"
    prepare_catalog_content: StrictBool = True
    assignees: dict[str, str] = Field(default_factory=dict, max_length=5)

    @field_validator("assignees")
    @classmethod
    def valid_assignees(cls, value):
        if set(value) - ROLES or any(not isinstance(v, str) or len(v) > 200 for v in value.values()):
            raise ValueError("负责人必须为受支持岗位的姓名标签")
        return value

    @field_validator("content_pack_id")
    @classmethod
    def valid_pack_id(cls, value):
        import re
        if value and not re.fullmatch(r"pack_[a-f0-9]{32}", value):
            raise ValueError("资料包编号无效")
        return value


class RevisionRequest(StrictRequest):
    revision: StrictInt = Field(gt=0)


class LinkContent(RevisionRequest):
    content_pack_id: str = Field(pattern=r"^pack_[a-f0-9]{32}$")
    content_relationship: Literal["transaction", "independent_reference"] = "independent_reference"


class UpdateTask(RevisionRequest):
    assignee_label: str | None = Field(default=None, max_length=200)
    status: Literal["todo", "in_progress", "in_review", "cancelled"] | None = None
    result_note: str | None = Field(default=None, max_length=5000)
    unresolved_items: list[ShortText] | None = Field(default=None, max_length=30)
    risks: list[ShortText] | None = Field(default=None, max_length=30)
    depends_on: list[Annotated[str, Field(max_length=64)]] | None = Field(default=None, max_length=6)

    @field_validator("assignee_label", "status", "result_note", "unresolved_items", "risks", "depends_on")
    @classmethod
    def no_explicit_null(cls, value):
        if value is None:
            raise ValueError("字段不能为 null")
        return value


class ReviewTask(RevisionRequest):
    task_id: str = Field(min_length=1, max_length=64)
    confirmed: StrictBool
    review_note: str = Field(min_length=1, max_length=3000)


def _call(fn, *args):
    try:
        return fn(*args)
    except CollaborationError as exc:
        raise HTTPException(exc.status, detail={"message": exc.message}) from None


@router.get("")
def list_collaborations(limit: int = Query(default=100, ge=1, le=200),
                        user: UserContext = Depends(get_current_user), db: Session = Depends(get_db)):
    return success_response(data=_call(CollaborationService(db).list, user.user_id, limit))


@router.post("")
def create_collaboration(req: CreateCollaboration, user: UserContext = Depends(get_current_user), db: Session = Depends(get_db)):
    return created_response(data=_call(CollaborationService(db).create, user.user_id, req.model_dump()))


@router.get("/{collaboration_id}")
def get_collaboration(collaboration_id: str, user: UserContext = Depends(get_current_user), db: Session = Depends(get_db)):
    return success_response(data=_call(CollaborationService(db).get, user.user_id, collaboration_id))


@router.patch("/{collaboration_id}")
def link_content(collaboration_id: str, req: LinkContent,
                 user: UserContext = Depends(get_current_user), db: Session = Depends(get_db)):
    return success_response(data=_call(CollaborationService(db).link_content, user.user_id, collaboration_id,
        req.revision, req.content_pack_id, req.content_relationship))


@router.patch("/{collaboration_id}/tasks/{task_id}")
def update_task(collaboration_id: str, task_id: str, req: UpdateTask,
                user: UserContext = Depends(get_current_user), db: Session = Depends(get_db)):
    return success_response(data=_call(CollaborationService(db).update_task, user.user_id, collaboration_id,
        req.revision, task_id, req.model_dump(exclude_unset=True, exclude={"revision"})))


@router.post("/{collaboration_id}/refresh-sources")
def refresh_sources(collaboration_id: str, req: RevisionRequest,
                    user: UserContext = Depends(get_current_user), db: Session = Depends(get_db)):
    return success_response(data=_call(CollaborationService(db).refresh_sources, user.user_id, collaboration_id, req.revision))


@router.post("/{collaboration_id}/review")
def review_task(collaboration_id: str, req: ReviewTask,
                user: UserContext = Depends(get_current_user), db: Session = Depends(get_db)):
    return success_response(data=_call(CollaborationService(db).review, user.user_id, collaboration_id,
        req.revision, req.task_id, req.confirmed, req.review_note))


@router.get("/{collaboration_id}/handoff")
def download_handoff(collaboration_id: str, revision: int = Query(..., ge=1), kind: Literal["md", "json"] = "md",
                     user: UserContext = Depends(get_current_user), db: Session = Depends(get_db)):
    content, mime, name = _call(CollaborationService(db).handoff, user.user_id, collaboration_id, revision, kind)
    return Response(content, media_type=mime, headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(name),
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

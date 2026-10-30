"""Authenticated rule retrieval and immutable draft-review reports."""
from typing import Annotated, Literal
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator
from sqlalchemy.orm import Session

from core.auth.backend import UserContext, get_current_user
from core.db.engine import get_db
from core.infra.responses import created_response, success_response
from core.foreign_trade.review import KnowledgeService, ReviewError, ReviewService

router = APIRouter(prefix="/v1/foreign-trade", tags=["Foreign trade knowledge and draft review"])
Channel = Literal["alibaba_rfq", "amazon_listing"]
SourceType = Literal["inquiry", "content_pack"]
Category = Literal["platform_rules", "quotation_terms"]


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReviewDraft(StrictRequest):
    title: str = Field(default="", max_length=1000)
    item_highlights: str = Field(default="", max_length=2000)
    body: str = Field(default="", max_length=20000)
    bullets: list[Annotated[str, Field(max_length=2000)]] = Field(default_factory=list, max_length=20)
    language: Literal["en", "es"]
    locale: str = Field(default="en_US", pattern=r"^[A-Za-z0-9_.-]{2,40}$")

    @model_validator(mode="after")
    def nonempty_draft(self):
        if not any(value.strip() for value in [self.title, self.item_highlights, self.body, *self.bullets]):
            raise ValueError("审核草稿不能为空")
        return self


class CreateReview(StrictRequest):
    source_type: SourceType
    source_id: str = Field(pattern=r"^(?:inq|pack)_[a-f0-9]{32}$")
    source_revision: StrictInt = Field(gt=0)
    channel: Channel
    draft: ReviewDraft
    previous_review_id: str | None = Field(default=None, pattern=r"^review_[a-f0-9]{32}$")

    @model_validator(mode="after")
    def source_prefix(self):
        if not self.source_id.startswith("inq_" if self.source_type == "inquiry" else "pack_"):
            raise ValueError("来源类型与编号不一致")
        return self


def _call(fn, *args):
    try:
        return fn(*args)
    except ReviewError as exc:
        raise HTTPException(exc.status, detail={"message": exc.message}) from None


@router.get("/knowledge")
def search_knowledge(query: str = Query(default="", max_length=300), channel: Channel | None = None,
                     category: Category | None = None, language: Literal["en", "es"] = "en",
                     limit: int = Query(default=50, ge=1, le=100), include_superseded: bool = False,
                     user: UserContext = Depends(get_current_user), db: Session = Depends(get_db)):
    return success_response(data=_call(KnowledgeService(db).search, user.user_id, query, channel, category,
                                      language, limit, include_superseded))


@router.post("/reviews")
def create_review(req: CreateReview, user: UserContext = Depends(get_current_user), db: Session = Depends(get_db)):
    return created_response(data=_call(ReviewService(db).create, user.user_id, req.model_dump()))


@router.get("/reviews")
def list_reviews(source_type: SourceType | None = None, source_id: str | None = Query(default=None, max_length=64),
                 limit: int = Query(default=50, ge=1, le=100), user: UserContext = Depends(get_current_user), db: Session = Depends(get_db)):
    return success_response(data=_call(ReviewService(db).list, user.user_id, source_type, source_id, limit))


@router.get("/reviews/{review_id}")
def get_review(review_id: str, user: UserContext = Depends(get_current_user), db: Session = Depends(get_db)):
    return success_response(data=_call(ReviewService(db).get, user.user_id, review_id))


@router.get("/reviews/{review_id}/download")
def download_review(review_id: str, kind: Literal["md", "json"] = "md",
                    user: UserContext = Depends(get_current_user), db: Session = Depends(get_db)):
    payload, mime, filename = _call(ReviewService(db).download, user.user_id, review_id, kind)
    return Response(payload, media_type=mime, headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(filename),
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

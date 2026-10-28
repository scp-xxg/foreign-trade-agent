"""Authenticated API for scenario one: public facts, inquiries and follow-up tasks."""
from __future__ import annotations

from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator
from sqlalchemy.orm import Session

from core.auth.backend import UserContext, get_current_user
from core.db.engine import get_db
from core.infra.responses import success_response, created_response
from core.foreign_trade.inquiry import InquiryError, InquiryService, search_products

router = APIRouter(prefix="/v1/foreign-trade", tags=["Foreign trade inquiries"])


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BuyerInput(StrictRequest):
    company_name: str = Field(default="", max_length=300)
    website: str = Field(default="", max_length=2000)
    email: str = Field(default="", max_length=320)
    country: str = Field(default="", max_length=100)


class ItemInput(StrictRequest):
    sku: str = Field(min_length=1, max_length=100)
    quantity: StrictInt = Field(gt=0, le=100000000)
    custom_packaging: StrictBool


class CreateInquiry(StrictRequest):
    title: str = Field(default="新询盘", min_length=1, max_length=200)
    buyer: BuyerInput = Field(default_factory=BuyerInput)
    raw_inquiry: str = Field(default="", max_length=20000)
    items: list[ItemInput] = Field(default_factory=list, max_length=50)
    destination_country: str = Field(default="", max_length=100)
    requested_lead_days: StrictInt | None = Field(default=None, gt=0, le=3650)
    is_demo_inquiry: StrictBool = True


class RevisionRequest(StrictRequest):
    revision: StrictInt = Field(gt=0)


class UpdateInquiry(RevisionRequest):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    buyer: BuyerInput | None = None
    raw_inquiry: str | None = Field(default=None, max_length=20000)
    items: list[ItemInput] | None = Field(default=None, max_length=50)
    destination_country: str | None = Field(default=None, max_length=100)
    requested_lead_days: StrictInt | None = Field(default=None, gt=0, le=3650)

    @field_validator("title", "buyer", "raw_inquiry", "items", "destination_country")
    @classmethod
    def reject_explicit_null(cls, value):
        if value is None:
            raise ValueError("该字段不能为 null")
        return value


class CreateFollowup(RevisionRequest):
    title: str = Field(min_length=1, max_length=300)
    due_at: str = Field(min_length=10, max_length=50)
    timezone: str = Field(default="Asia/Shanghai", max_length=100)


class UpdateFollowup(RevisionRequest):
    status: Literal["completed", "cancelled"]


def _call(fn, *args):
    try:
        return fn(*args)
    except InquiryError as exc:
        raise HTTPException(status_code=exc.status, detail={
            "message": exc.message, "details": exc.details,
        }) from None


def _svc(db: Session) -> InquiryService:
    return InquiryService(db)


@router.get("/products")
def products(query: str = Query(default="", max_length=300),
             user: UserContext = Depends(get_current_user)):
    return success_response(data=search_products(query=query, limit=20))


@router.get("/inquiries")
def list_inquiries(limit: int = Query(default=100, ge=1, le=200),
                   user: UserContext = Depends(get_current_user), db: Session = Depends(get_db)):
    return success_response(data=_call(_svc(db).list, user.user_id, limit))


@router.post("/inquiries")
def create_inquiry(req: CreateInquiry, user: UserContext = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    return created_response(data=_call(_svc(db).create, user.user_id, req.model_dump()))


@router.get("/inquiries/{inquiry_id}")
def get_inquiry(inquiry_id: str, user: UserContext = Depends(get_current_user), db: Session = Depends(get_db)):
    return success_response(data=_call(_svc(db).get, user.user_id, inquiry_id))


@router.patch("/inquiries/{inquiry_id}")
def update_inquiry(inquiry_id: str, req: UpdateInquiry, user: UserContext = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    values = req.model_dump(exclude_unset=True, exclude={"revision"})
    return success_response(data=_call(_svc(db).update, user.user_id, inquiry_id, req.revision, values))


@router.post("/inquiries/{inquiry_id}/verify-buyer")
async def verify_buyer(inquiry_id: str, req: RevisionRequest, user: UserContext = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    try:
        result = await _svc(db).verify(user.user_id, inquiry_id, req.revision)
    except InquiryError as exc:
        raise HTTPException(status_code=exc.status, detail={"message": exc.message, "details": exc.details}) from None
    return success_response(data=result)


@router.post("/inquiries/{inquiry_id}/quote")
def calculate_quote(inquiry_id: str, req: RevisionRequest, user: UserContext = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    return success_response(data=_call(_svc(db).quote, user.user_id, inquiry_id, req.revision))


@router.post("/inquiries/{inquiry_id}/draft")
def generate_draft(inquiry_id: str, req: RevisionRequest, user: UserContext = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    return success_response(data=_call(_svc(db).draft, user.user_id, inquiry_id, req.revision))


@router.post("/inquiries/{inquiry_id}/followups")
def create_followup(inquiry_id: str, req: CreateFollowup, user: UserContext = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    return success_response(data=_call(_svc(db).create_followup, user.user_id, inquiry_id, req.revision,
                                      req.title, req.due_at, req.timezone))


@router.patch("/inquiries/{inquiry_id}/followups/{task_id}")
def update_followup(inquiry_id: str, task_id: str, req: UpdateFollowup,
                    user: UserContext = Depends(get_current_user), db: Session = Depends(get_db)):
    return success_response(data=_call(_svc(db).update_followup, user.user_id, inquiry_id, req.revision,
                                      task_id, req.status))


@router.post("/inquiries/{inquiry_id}/mark-replied")
def mark_replied(inquiry_id: str, req: RevisionRequest, user: UserContext = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    return success_response(data=_call(_svc(db).mark_replied, user.user_id, inquiry_id, req.revision))


@router.post("/inquiries/{inquiry_id}/resume-followups")
def resume_followups(inquiry_id: str, req: RevisionRequest, user: UserContext = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    return success_response(data=_call(_svc(db).resume_followups, user.user_id, inquiry_id, req.revision))


@router.post("/inquiries/{inquiry_id}/interpret")
async def interpret_inquiry(inquiry_id: str, req: RevisionRequest,
                            user: UserContext = Depends(get_current_user), db: Session = Depends(get_db)):
    from core.foreign_trade.ai import interpret_inquiry as interpret
    record = _call(_svc(db).get, user.user_id, inquiry_id)
    if record["revision"] != req.revision:
        raise HTTPException(409, detail={"message": "询盘已更新，请刷新后重新提取"})
    catalog = search_products(limit=50)["data"]["products"]
    result = await interpret(record["raw_inquiry"], catalog)
    db.expire_all()
    latest = _call(_svc(db).get, user.user_id, inquiry_id)
    if latest["revision"] != req.revision:
        raise HTTPException(409, detail={"message": "提取期间询盘已更新，请刷新后重新提取"})
    return success_response(data={"revision": req.revision, **result})

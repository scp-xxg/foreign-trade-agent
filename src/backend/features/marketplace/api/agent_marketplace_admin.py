"""Administrator review API for community sub-agent marketplace listings."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.deps import require_admin
from core.db.engine import get_db
from core.infra.responses import success_response
from features.marketplace import agent_submissions

router = APIRouter(
    prefix="/v1/admin/agent-marketplace",
    tags=["Admin Agent Marketplace"],
    dependencies=[Depends(require_admin)],
)


class ReviewRequest(BaseModel):
    approve: bool
    review_note: str = Field("", max_length=2000)
    category: Optional[str] = Field(None, max_length=64)


@router.get("/submissions", summary="管理员查看智能体上架申请")
def list_agent_submissions(
    status: Optional[str] = Query(None, pattern="^(pending|approved|rejected)$"),
    db: Session = Depends(get_db),
):
    return success_response(
        data={"items": agent_submissions.list_submissions(db, status=status)}
    )


@router.get("/submissions/{submission_id}", summary="管理员查看智能体上架申请详情")
def get_agent_submission(submission_id: str, db: Session = Depends(get_db)):
    return success_response(
        data=agent_submissions.get_submission(db, submission_id)
    )


@router.post("/submissions/{submission_id}/review", summary="管理员审核智能体上架申请")
def review_agent_submission(
    submission_id: str,
    body: ReviewRequest,
    db: Session = Depends(get_db),
):
    result = agent_submissions.review_submission(
        db,
        submission_id,
        approve=body.approve,
        review_note=body.review_note,
        category=body.category or "",
    )
    return success_response(data=result)

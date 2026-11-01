# Modified by foreign-trade-agent contributors, 2026-10-31.
"""Authenticated, stateless buyer discovery; results are never shared across users."""
from fastapi import APIRouter, Depends, HTTPException
from core.auth.backend import UserContext, get_current_user
from core.infra.responses import success_response
from core.foreign_trade.buyer_search import SearchInput, make_plan, run_search
router=APIRouter(prefix="/v1/foreign-trade/buyer-search",tags=["Foreign trade buyer search"])

@router.post("/plan")
def plan(req: SearchInput,user: UserContext=Depends(get_current_user)):
    try:
        return success_response(data=make_plan(req))
    except ValueError as exc:
        raise HTTPException(status_code=422,detail=str(exc)) from None

@router.post("/run")
async def run(req: SearchInput,user: UserContext=Depends(get_current_user)):
    try:
        return success_response(data=await run_search(req))
    except ValueError as exc:
        raise HTTPException(status_code=422,detail=str(exc)) from None
    except RuntimeError:
        raise HTTPException(status_code=429,detail="买家搜索繁忙，请稍后重试。") from None

# Acquisition stages share the same authenticated, request-scoped boundary.
from core.foreign_trade.acquisition import ProfileInput, ResearchInput, draft_profile, due_diligence, discover_contacts

@router.post('/profile')
def profile(req: ProfileInput, user: UserContext=Depends(get_current_user)):
    return success_response(data=draft_profile(req))

@router.post('/due-diligence')
async def dossier(req: ResearchInput, user: UserContext=Depends(get_current_user)):
    return success_response(data=await due_diligence(req))

@router.post('/contacts')
async def contacts(req: ResearchInput, user: UserContext=Depends(get_current_user)):
    return success_response(data=await discover_contacts(req))

from core.foreign_trade.lead_outreach import LeadInput, OutreachInput, prioritize, draft_outreach

@router.post('/prioritize')
def prioritize_lead(req: LeadInput, user: UserContext=Depends(get_current_user)):
    return success_response(data=prioritize(req))

@router.post('/outreach')
def outreach(req: OutreachInput, user: UserContext=Depends(get_current_user)):
    try:
        return success_response(data=draft_outreach(req))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

from core.foreign_trade.followup import CadenceInput, ReplyInput, plan_cadence, triage_reply

@router.post('/cadence')
def cadence(req: CadenceInput, user: UserContext=Depends(get_current_user)):
    return success_response(data=plan_cadence(req))

@router.post('/reply-triage')
def reply_triage(req: ReplyInput, user: UserContext=Depends(get_current_user)):
    return success_response(data=triage_reply(req))


from core.foreign_trade.diligence import DiligenceInput, run_stage
from typing import Literal

@router.post('/diligence/{stage}')
async def diligence_stage(stage: Literal['identity-check','business-fit','decision-chain','transaction-risk'],
                          req: DiligenceInput, user: UserContext=Depends(get_current_user)):
    return success_response(data=await run_stage(req, stage))

# Direct composer checks use the same authenticated route family.
from api.routes.v1.foreign_trade_material_check import router as material_check_router
router.include_router(material_check_router)

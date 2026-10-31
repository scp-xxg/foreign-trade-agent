"""Authenticated capability discovery; never exposes model URLs or credentials."""
from fastapi import APIRouter, Depends
from core.auth.backend import UserContext, get_current_user
from core.infra.responses import success_response
from features.knowledge.runtime import runtime_capabilities

router = APIRouter()

@router.get("/runtime", summary="当前私有知识库索引能力")
def get_knowledge_runtime(user: UserContext = Depends(get_current_user)):
    return success_response(data=runtime_capabilities())

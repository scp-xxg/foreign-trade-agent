"""Compose knowledge routes in the original endpoint order."""
from fastapi import APIRouter
from features.knowledge.api import kb_assets, kb_spaces, kb_documents, kb_mutations, kb_chunks, kb_runtime

router = APIRouter()
for group in (kb_runtime, kb_assets, kb_spaces, kb_documents, kb_mutations, kb_chunks):
    router.include_router(group.router, prefix="/v1/catalog/kb", tags=["Knowledge Base"])

"""Community knowledge-base request models."""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class IndexingConfig(BaseModel):
    parent_chunk_size: int = Field(1024, ge=256, le=4096)
    child_chunk_size: int = Field(128, ge=64, le=512)
    overlap_tokens: int = Field(20, ge=0, le=100)
    parent_child_indexing: bool = True
    auto_keywords_count: int = Field(0, ge=0, le=10)
    auto_questions_count: int = Field(0, ge=0, le=5)
    separators: Optional[List[str]] = None
    child_separators: Optional[List[str]] = None


class WikiConfigRequest(BaseModel):
    granularity: Literal["focused", "standard", "exhaustive"] = "standard"
    language: str = Field("中文", min_length=1, max_length=40)
    extraction_instructions: str = Field("", max_length=4000)
    content_instructions: str = Field("", max_length=4000)
    batch_size: int = Field(5, ge=1, le=50)
    map_parallel: int = Field(2, ge=1, le=16)
    reduce_parallel: int = Field(2, ge=1, le=16)
    max_llm_calls: int = Field(100, ge=1, le=4000)


class CreateKBSpaceRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    chunk_method: Optional[str] = "semantic"
    metadata: Optional[dict] = Field(default_factory=dict)
    indexing_config: Optional[IndexingConfig] = None
    visibility: Literal["private"] = "private"
    index_modes: Optional[List[Literal["rag", "wiki"]]] = Field(None, min_length=1, max_length=2)
    wiki_config: Optional[WikiConfigRequest] = None


class UpdateKBSpaceRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    index_modes: Optional[List[Literal["rag", "wiki"]]] = Field(None, min_length=1, max_length=2)
    wiki_config: Optional[WikiConfigRequest] = None


class PolishKBDescriptionRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None


class UpdateChunkRequest(BaseModel):
    content: Optional[str] = None
    tags: Optional[List[str]] = None
    questions: Optional[List[str]] = None


class ReindexRequest(BaseModel):
    indexing_config: Optional[IndexingConfig] = None
    chunk_method: Optional[str] = None


__all__ = [
    "CreateKBSpaceRequest",
    "IndexingConfig",
    "PolishKBDescriptionRequest",
    "ReindexRequest",
    "UpdateChunkRequest",
    "UpdateKBSpaceRequest",
]

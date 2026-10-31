"""Local private knowledge availability without changing deployment or ownership."""
import os
from core.config.local_mode import local_mode_enabled
from core.infra.exceptions import BadRequestError


def local_private_knowledge_enabled() -> bool:
    return local_mode_enabled() and os.getenv("LOCAL_PRIVATE_KB_ENABLED", "").lower() in {"1", "true", "yes"}


def runtime_capabilities() -> dict:
    from core.models.embedding import resolve_embed_config
    from features.knowledge.wiki.llm import wiki_model_configured
    url, model, _ = resolve_embed_config()
    embedding = bool(url and model)
    wiki = wiki_model_configured()
    return {"local_private_only": local_private_knowledge_enabled(),
            "embedding_configured": embedding, "wiki_configured": wiki,
            "default_index_modes": ["rag"] if embedding else (["wiki"] if wiki else [])}


def require_indexing_ready(modes: list[str], chunk_method: str = "structured") -> None:
    # Preserve existing deployments; this guard is opt-in with the local integration.
    if not local_private_knowledge_enabled():
        return
    caps = runtime_capabilities()
    if ("rag" in modes or chunk_method == "embedding_semantic") and not caps["embedding_configured"]:
        raise BadRequestError(message="尚未配置 embedding 向量模型；请在模型服务中配置，或选择 Wiki 索引和结构感知分块。")
    if "wiki" in modes and not caps["wiki_configured"]:
        raise BadRequestError(message="Wiki 索引需要可用的对话模型，请在模型服务中指派 kb_wiki 或 main_agent。")


def new_space_modes(requested: list[str] | None) -> list[str]:
    if requested is not None:
        return list(dict.fromkeys(requested))
    if not local_private_knowledge_enabled():
        return ["rag"]
    modes = runtime_capabilities()["default_index_modes"]
    if not modes:
        raise BadRequestError(message="请先配置对话模型（Wiki）或 embedding 模型（向量检索）。")
    return modes

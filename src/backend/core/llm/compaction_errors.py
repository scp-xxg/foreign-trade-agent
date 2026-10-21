# Modified by foreign-trade-agent contributors, 2026-10-21; see CHANGES_FOREIGN_TRADE.md.
"""Dependency-free failure contract for context compression."""

COMPACTION_FAILURE_MESSAGE = (
    "本轮未完成：对话整理失败。已保存的操作和工具结果仍保留，"
    "请查看记录后继续未完成步骤。"
)


class ContextCompactionError(RuntimeError):
    """Compression failed without replacing the current task with a summary."""

    code = "context_compaction_failed"

    def __init__(self) -> None:
        super().__init__(COMPACTION_FAILURE_MESSAGE)


def find_context_compaction_error(exc: BaseException) -> ContextCompactionError | None:
    """Find the typed failure through wrappers without reading their messages."""
    pending = [exc]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, ContextCompactionError):
            return current
        if isinstance(current, BaseExceptionGroup):
            pending.extend(current.exceptions)
        for nested in (current.__cause__, current.__context__):
            if nested is not None:
                pending.append(nested)
    return None

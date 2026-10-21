# Modified by foreign-trade-agent contributors, 2026-10-21; see CHANGES_FOREIGN_TRADE.md.
"""Compatibility mixin: structured-output failures must remain failures.

The agent owns compression recovery because it can preserve the original
context. A model adapter must never manufacture a successful summary after a
provider error, including for non-compression structured-output requests.
"""

from __future__ import annotations

from typing import Any

from agentscope.message import Msg
from agentscope.model import StructuredResponse

class StructuredFallbackMixin:
    """Retain the shared model MRO while propagating structured-output errors.

    Must be placed before the actual model class in the MRO
    (``class Foo(StructuredFallbackMixin, SomeChatModel)``), so that this class's
    ``super()`` points to the real model implementation.
    """

    async def generate_structured_output(  # type: ignore[override]
        self,
        messages: "list[Msg]",
        structured_model: Any,
        **kwargs: Any,
    ) -> StructuredResponse:
        return await super().generate_structured_output(  # type: ignore[misc]
            messages, structured_model, **kwargs
        )

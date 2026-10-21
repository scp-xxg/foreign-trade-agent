"""Reject repaired JSON only at the registered foreign-trade tool boundaries.

AgentScope parses tool_call.input with JSON repair before FunctionTool.__call__.
This toolkit retains the raw ToolCallBlock and stops malformed business writes
before delegating to the existing ontology/permission-aware dispatch chain.
"""
from __future__ import annotations

import json
import math

from agentscope.message import TextBlock, ToolResultState
from agentscope.tool._response import ToolChunk, ToolResponse
from core.ontology.toolkit import OntologyFilteredToolkit

from core.llm.foreign_trade_plugin import TRADE_TOOL_NAMES


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _finite_float(text):
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("nonfinite number")
    return value


def _reject_constant(value):
    raise ValueError("non-JSON constant")


def validate_trade_tool_json(raw):
    """Strict object JSON, recursively unique keys and finite numeric values."""
    if not isinstance(raw, str) or not raw or len(raw) > 1_048_576:
        raise ValueError("expected bounded JSON string")
    value = json.loads(raw, object_pairs_hook=_unique_object, parse_float=_finite_float,
                       parse_constant=_reject_constant)
    if not isinstance(value, dict):
        raise ValueError("expected JSON object")
    return value


class StrictTradeToolkit(OntologyFilteredToolkit):
    """Preserve all inherited filtering/ticket/surface behavior for valid input."""

    async def call_tool(self, tool_call, state):
        if getattr(tool_call, "name", None) in TRADE_TOOL_NAMES:
            try:
                validate_trade_tool_json(getattr(tool_call, "input", None))
            except (ValueError, TypeError, RecursionError):
                payload = {"ok": False, "status": 422, "errors": [{
                    "code": "invalid_tool_json",
                    "message": "工具参数必须是完整、无重复键的严格 JSON 对象，不能包含 NaN/Infinity。当前参数不完整或格式无效，未执行任何操作。请重新发送完整 JSON，不要省略闭合引号或括号。",
                }], "warnings": [], "retryable": True, "executed": False}
                chunk = ToolChunk(content=[TextBlock(type="text", text=json.dumps(payload, ensure_ascii=False))],
                                  state=ToolResultState.ERROR)
                response = ToolResponse(id=str(getattr(tool_call, "id", "") or ""))
                yield chunk
                yield response.append_chunk(chunk)
                return
        async for item in super().call_tool(tool_call, state):
            yield item

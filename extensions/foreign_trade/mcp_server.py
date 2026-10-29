"""Local demo-only MCP tools for product facts and deterministic quotations."""
from __future__ import annotations

from typing import Any
from mcp.server.mcpserver import MCPServer
from pydantic import StrictInt
from starlette.requests import Request
from starlette.responses import JSONResponse

if __package__:
    from . import engine
else:
    import engine

mcp = MCPServer(
    "foreign-trade-demo",
    instructions=(
        "All products and prices are synthetic demo data. Query product facts and "
        "call calculate_quote for every quotation or quantity change. Never invent "
        "freight, certification, stock or delivery commitments."
    ),
    log_level="WARNING",
)


@mcp.tool()
def search_products(query: str = "", category: str = "", limit: StrictInt = 5) -> dict[str, Any]:
    """查询模拟办公收纳产品。支持SKU、中文或英文关键词；空查询列出目录。
    返回匹配的产品事实、MOQ、价格阶梯、来源与演示标识。查询不是报价，金额须调用calculate_quote。
    """
    return engine.search_products(query=query, category=category, limit=limit)


@mcp.tool()
def get_product(sku: str) -> dict[str, Any]:
    """读取一个模拟SKU的完整事实、包装政策、交期和价格阶梯，并提供资料版本与记录来源。
    不存在的SKU返回结构化错误，不能自行补全产品参数或价格。
    """
    return engine.get_product(sku)


@mcp.tool()
def calculate_quote(
    items: list[dict[str, Any]],
    destination_country: str = "",
    requested_lead_days: StrictInt | None = None,
) -> dict[str, Any]:
    """计算模拟询盘报价。items每项必须有sku、quantity，custom_packaging可选且为布尔值。
    示例：[{"sku":"DESK-001","quantity":500,"custom_packaging":false}]。
    数量必须正整数，校验MOQ和定制条件；按数量阶梯定价并用Decimal计算金额。
    返回USD货值、包装费和不含运费小计。运费始终待确认，不得称到岸总价。
    requested_lead_days表示希望的生产天数，不等同到货日期；冲突会返回警告。
    用户改数量或包装时必须重新调用本工具。成功结果含稳定报价编号，网页提供中英文PDF和Excel下载按钮。
    不编造文件下载链接。所有结果仅为模拟演示，不能对外承诺。
    """
    return engine.calculate_quote(
        items=items,
        destination_country=destination_country,
        requested_lead_days=requested_lead_days,
    )


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    result = engine.search_products(limit=1)
    return JSONResponse({
        "service": "foreign-trade-demo",
        "ok": bool(result["ok"]),
        "catalog_version": result.get("catalog_version"),
        "is_simulated": True,
    })


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="127.0.0.1", port=9120,
            stateless_http=True, json_response=True)

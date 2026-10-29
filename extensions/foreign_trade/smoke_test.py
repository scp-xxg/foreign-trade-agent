"""Read-only protocol acceptance against the local simulated trade MCP."""
import asyncio
import json
import re
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

async def main():
    async with streamable_http_client("http://127.0.0.1:9120/mcp") as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            names = {tool.name for tool in (await session.list_tools()).tools}
            assert names == {"search_products", "get_product", "calculate_quote"}, names
            async def call(name, args):
                result = await session.call_tool(name, args)
                assert not result.is_error, result
                if result.structured_content is not None:
                    return result.structured_content
                return json.loads(next(b.text for b in result.content if b.type == "text"))
            search = await call("search_products", {"query": "DESK-001", "limit": 5})
            assert search["ok"] and search["data"]["products"][0]["sku"] == "DESK-001"
            product = await call("get_product", {"sku": "DESK-001"})
            assert product["ok"] and product["data"]["moq"] == 100
            results = []
            for quantity, custom, expected in [(500, False, "2400.00"), (2000, False, "8400.00"), (1000, True, "5100.00")]:
                quote = await call("calculate_quote", {
                    "items": [{"sku": "DESK-001", "quantity": quantity, "custom_packaging": custom}],
                    "destination_country": "Spain",
                })
                assert quote["ok"], quote
                assert quote["data"]["subtotal"] == expected, quote
                assert quote["data"]["document_type"] == "foreign_trade_quote", quote
                assert quote["data"]["document_version"] == 1, quote
                assert re.fullmatch(r"DEMO-[A-F0-9]{16}", quote["data"]["quote_id"]), quote
                assert quote["data"]["freight"]["amount"] is None
                assert quote["data"]["subtotal_excludes_freight"] is True
                assert quote["is_simulated"] is True and quote["source"]["record_refs"]
                results.append({"quantity": quantity, "custom_packaging": custom, "subtotal_usd": expected,
                                "quote_id": quote["data"]["quote_id"]})
            assert len({quote["quote_id"] for quote in results}) == len(results)
            for items in [
                [{"sku": "DESK-001", "quantity": 99}],
                [{"sku": "DESK-001", "quantity": True}],
                [{"sku": "UNKNOWN", "quantity": 500}],
                [{"sku": "DESK-001", "quantity": 500, "discount": 0.5}],
            ]:
                bad = await call("calculate_quote", {"items": items})
                assert bad["ok"] is False and bad["data"] is None and bad["errors"], bad
                assert "quote_id" not in bad and "document_type" not in bad, bad
            strict = await session.call_tool("calculate_quote", {
                "items": [{"sku": "DESK-001", "quantity": 500}], "requested_lead_days": True,
            })
            assert strict.is_error is True
            print(json.dumps({"ok": True, "tools": sorted(names), "verified_quotes": results,
                              "invalid_inputs_rejected": 5, "catalog_version": product["catalog_version"]},
                             ensure_ascii=False, indent=2))

if __name__ == "__main__":
    asyncio.run(main())

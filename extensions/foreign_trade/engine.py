"""Read-only, deterministic helpers for an entirely fictional trade catalog.

Money is calculated with Decimal and returned as decimal strings.  A quote is
a simulated goods-and-packaging subtotal, never a freight-inclusive offer.
Only the adjacent, public catalog file is read; no network or database is used.
"""

from __future__ import annotations

from copy import deepcopy
from decimal import Context, Decimal, ROUND_HALF_UP, localcontext
from functools import lru_cache
import hashlib
import json
from pathlib import Path
from typing import Any

_CATALOG_PATH = Path(__file__).with_name("catalog.json")
_MAX_SEARCH_RESULTS = 50
_ALLOWED_ITEM_FIELDS = frozenset({"sku", "quantity", "custom_packaging"})


@lru_cache(maxsize=1)
def _catalog() -> dict[str, Any]:
    # This private cached value is never returned to callers.
    return json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))


def _issue(code: str, message: str, **details: Any) -> dict[str, Any]:
    return {"code": code, "message": message, **details}


def _response(
    data: Any = None,
    *,
    errors: list[dict[str, Any]] | None = None,
    warnings: list[dict[str, Any]] | None = None,
    record_refs: list[str] | None = None,
) -> dict[str, Any]:
    catalog = _catalog()
    problems = errors or []
    notices = [
        _issue(
            "SIMULATED_DATA",
            "All products, specifications, prices, and production times are fictional demo data.",
        ),
        *(warnings or []),
    ]
    return {
        "ok": not problems,
        "errors": deepcopy(problems),
        "warnings": deepcopy(notices),
        "data": deepcopy(data) if not problems else None,
        "catalog_version": catalog["catalog_version"],
        "is_simulated": True,
        "source": {
            "type": "synthetic_demo_catalog",
            "catalog_record_ref": catalog["source"]["record_ref"],
            "record_refs": list(dict.fromkeys(record_refs or [])),
        },
    }


def _sku(value: Any) -> str | None:
    return value.strip().upper() if isinstance(value, str) and value.strip() else None


def _products_by_sku() -> dict[str, dict[str, Any]]:
    return {product["sku"]: product for product in _catalog()["products"]}


def search_products(
    query: str = "", category: str = "", limit: int = 5
) -> dict[str, Any]:
    """Search the local demo catalog by English/Chinese keywords and category."""
    errors = []
    if not isinstance(query, str):
        errors.append(_issue("INVALID_QUERY", "query must be a string.", field="query"))
    if not isinstance(category, str):
        errors.append(_issue("INVALID_CATEGORY", "category must be a string.", field="category"))
    if type(limit) is not int or not 1 <= limit <= _MAX_SEARCH_RESULTS:
        errors.append(
            _issue(
                "INVALID_LIMIT",
                f"limit must be an integer between 1 and {_MAX_SEARCH_RESULTS}.",
                field="limit",
            )
        )
    if errors:
        return _response(errors=errors)

    terms = query.strip().casefold().split()
    category_filter = category.strip().casefold()
    matches = []
    for product in _catalog()["products"]:
        categories = {product["category"].casefold(), product["category_zh"].casefold()}
        if category_filter and category_filter not in categories:
            continue
        searchable = " ".join(
            [
                product["sku"],
                product["name"],
                product["name_zh"],
                product["category"],
                product["category_zh"],
                product["description"],
                product["material"],
                *product["keywords"],
            ]
        ).casefold()
        if all(term in searchable for term in terms):
            matches.append(product)

    selected = matches[:limit]
    return _response(
        {
            "products": selected,
            "total_matches": len(matches),
            "returned_count": len(selected),
        },
        record_refs=[product["source"]["record_ref"] for product in selected],
    )


def get_product(sku: str) -> dict[str, Any]:
    """Return the full simulated product record, including tiers and packaging."""
    normalized = _sku(sku)
    if normalized is None:
        return _response(
            errors=[_issue("INVALID_SKU", "sku must be a nonempty string.", field="sku")]
        )
    product = _products_by_sku().get(normalized)
    if product is None:
        return _response(
            errors=[_issue("UNKNOWN_SKU", f"Unknown demo SKU: {normalized}.", field="sku")]
        )
    return _response(product, record_refs=[product["source"]["record_ref"]])


def _money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")


def calculate_quote(
    items: list[dict[str, Any]],
    destination_country: str = "",
    requested_lead_days: int | None = None,
) -> dict[str, Any]:
    """Calculate a simulated subtotal; reject invalid lines without partial totals.

    Tier pricing applies independently to each SKU. Duplicate SKUs are rejected,
    so callers must send one combined quantity per SKU before selecting a tier.
    Production lead time is the longest line's production estimate, including
    any custom-packaging time, and never includes unconfirmed shipping transit.
    """
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if not isinstance(destination_country, str):
        errors.append(
            _issue(
                "INVALID_DESTINATION",
                "destination_country must be a string.",
                field="destination_country",
            )
        )
    if requested_lead_days is not None and (
        type(requested_lead_days) is not int or requested_lead_days <= 0
    ):
        errors.append(
            _issue(
                "INVALID_REQUESTED_LEAD_DAYS",
                "requested_lead_days must be a positive integer or null.",
                field="requested_lead_days",
            )
        )
    if not isinstance(items, list) or not items:
        errors.append(
            _issue("INVALID_ITEMS", "items must be a nonempty list.", field="items")
        )
        return _response(errors=errors)

    products = _products_by_sku()
    seen: set[str] = set()
    validated: list[tuple[dict[str, Any], int, bool]] = []
    record_refs = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(
                _issue(
                    "INVALID_ITEM", "Each item must be an object.", field="items", item_index=index
                )
            )
            continue
        extra_fields = set(item) - _ALLOWED_ITEM_FIELDS
        if extra_fields:
            errors.append(
                _issue(
                    "UNSUPPORTED_ITEM_FIELDS",
                    "Only sku, quantity, and custom_packaging may be supplied.",
                    field="items",
                    item_index=index,
                )
            )

        normalized = _sku(item.get("sku"))
        product = products.get(normalized) if normalized else None
        if normalized is None:
            errors.append(
                _issue(
                    "INVALID_SKU",
                    "sku must be a nonempty string.",
                    field="sku",
                    item_index=index,
                )
            )
        else:
            if normalized in seen:
                errors.append(
                    _issue(
                        "DUPLICATE_SKU",
                        f"Combine quantities into one line for {normalized} before quoting.",
                        field="sku",
                        item_index=index,
                    )
                )
            seen.add(normalized)
            if product is None:
                errors.append(
                    _issue(
                        "UNKNOWN_SKU",
                        f"Unknown demo SKU: {normalized}.",
                        field="sku",
                        item_index=index,
                    )
                )
            else:
                record_refs.append(product["source"]["record_ref"])

        quantity = item.get("quantity")
        valid_quantity = type(quantity) is int and quantity > 0
        if not valid_quantity:
            errors.append(
                _issue(
                    "INVALID_QUANTITY",
                    "quantity must be a positive integer; booleans, floats, and strings are rejected.",
                    field="quantity",
                    item_index=index,
                )
            )
        custom_packaging = item.get("custom_packaging", False)
        valid_packaging = type(custom_packaging) is bool
        if not valid_packaging:
            errors.append(
                _issue(
                    "INVALID_CUSTOM_PACKAGING",
                    "custom_packaging must be true or false.",
                    field="custom_packaging",
                    item_index=index,
                )
            )

        if product is None or not valid_quantity or not valid_packaging:
            continue
        if quantity < product["moq"]:
            errors.append(
                _issue(
                    "BELOW_MOQ",
                    f"{normalized} requires at least {product['moq']} units.",
                    field="quantity",
                    item_index=index,
                    minimum_quantity=product["moq"],
                )
            )
        custom = product["packaging"]["custom"]
        if custom_packaging:
            if not custom["supported"]:
                errors.append(
                    _issue(
                        "CUSTOM_PACKAGING_UNSUPPORTED",
                        f"{normalized} does not support custom packaging in this demo.",
                        field="custom_packaging",
                        item_index=index,
                    )
                )
            elif quantity < custom["moq"]:
                errors.append(
                    _issue(
                        "BELOW_CUSTOM_PACKAGING_MOQ",
                        f"Custom packaging for {normalized} requires at least {custom['moq']} units.",
                        field="quantity",
                        item_index=index,
                        minimum_quantity=custom["moq"],
                    )
                )
        validated.append((product, quantity, custom_packaging))

    if errors:
        return _response(errors=errors, record_refs=record_refs)

    destination = destination_country.strip()
    if not destination:
        warnings.append(
            _issue(
                "DESTINATION_REQUIRED",
                "Destination country is missing; freight and delivery need confirmation.",
                field="destination_country",
            )
        )
    warnings.append(
        _issue(
            "FREIGHT_UNCONFIRMED",
            "No freight rate is available. The subtotal excludes freight; freight is not zero.",
        )
    )
    warnings.append(
        _issue(
            "TAXES_DUTIES_UNCONFIRMED",
            "Import taxes and duties are not calculated and are excluded from the subtotal.",
        )
    )

    lines = []
    # A fresh decimal context prevents a caller's rounding or precision settings
    # from changing a quote. Precision scales with order size before summation.
    max_quantity_digits = max(len(str(quantity)) for _, quantity, _ in validated)
    precision = max(28, max_quantity_digits + len(str(len(validated))) + 12)
    with localcontext(Context(prec=precision, rounding=ROUND_HALF_UP)):
        merchandise_total = Decimal("0.00")
        packaging_total = Decimal("0.00")
        for product, quantity, custom_packaging in validated:
            tier = next(
                tier
                for tier in reversed(product["price_tiers"])
                if quantity >= tier["min_quantity"]
            )
            unit_price = Decimal(tier["unit_price"])
            custom = product["packaging"]["custom"]
            unit_surcharge = (
                Decimal(custom["unit_surcharge"]) if custom_packaging else Decimal("0.00")
            )
            merchandise_amount = unit_price * quantity
            packaging_amount = unit_surcharge * quantity
            merchandise_total += merchandise_amount
            packaging_total += packaging_amount
            production_days = product["production_lead_days"] + (
                custom["additional_production_days"] if custom_packaging else 0
            )
            lines.append(
                {
                    "sku": product["sku"],
                    "name": product["name"],
                    "name_zh": product["name_zh"],
                    "quantity": quantity,
                    "currency": "USD",
                    "is_simulated": True,
                    "custom_packaging": custom_packaging,
                    "standard_packaging_included": True,
                    "applied_price_tier": deepcopy(tier),
                    "unit_price": _money(unit_price),
                    "packaging_unit_surcharge": _money(unit_surcharge),
                    "effective_unit_price": _money(unit_price + unit_surcharge),
                    "merchandise_subtotal": _money(merchandise_amount),
                    "packaging_subtotal": _money(packaging_amount),
                    "line_subtotal": _money(merchandise_amount + packaging_amount),
                    "production_lead_days": production_days,
                    "source": deepcopy(product["source"]),
                }
            )

        data = {
            "quote_status": "simulation_only",
            "currency": "USD",
            "items": lines,
            "merchandise_subtotal": _money(merchandise_total),
            "packaging_subtotal": _money(packaging_total),
            "subtotal": _money(merchandise_total + packaging_total),
            "subtotal_excludes_freight": True,
            "subtotal_excludes_taxes_and_duties": True,
            "destination_country": destination,
            "freight": {
                "status": "pending_confirmation",
                "amount": None,
                "currency": "USD",
                "destination_country": destination,
                "reason": "The demo catalog contains no freight rates.",
            },
            "production_lead_days": max(line["production_lead_days"] for line in lines),
            "production_lead_basis": (
                "Simulated calendar days after order and artwork confirmation; "
                "shipping/transit is excluded."
            ),
            "requested_lead_days": requested_lead_days,
            "requested_delivery_status": (
                "not_requested" if requested_lead_days is None else "requires_confirmation"
            ),
            "transit_lead_days": None,
            "delivery_lead_days": None,
        }

    # Render the commercial breakdown from the same exact decimal strings.
    # A combined unit price must not be mistaken for the goods-only unit price.
    table_rows = [
        "| SKU | 数量（件） | 货品单价（USD/件） | 每件定制包装费（USD） | 货值（USD） | 包装费（USD） | 不含运费小计（USD） |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for line in data["items"]:
        table_rows.append(
            "| " + " | ".join(str(line[key]) for key in (
                "sku", "quantity", "unit_price", "packaging_unit_surcharge",
                "merchandise_subtotal", "packaging_subtotal", "line_subtotal",
            )) + " |"
        )
    data["quotation_markdown"] = "\n".join(table_rows)
    data["price_basis"] = {
        "unit_price": "Goods-only unit price; custom packaging is separate.",
        "effective_unit_price": "Goods unit price plus custom packaging per unit; do not charge packaging twice.",
    }

    if requested_lead_days is not None:
        if requested_lead_days < data["production_lead_days"]:
            data["requested_delivery_status"] = "cannot_meet_production_window"
            warnings.append(
                _issue(
                    "REQUESTED_LEAD_TOO_SHORT",
                    "The requested lead time is shorter than simulated production alone; "
                    "the requested delivery cannot be promised.",
                    field="requested_lead_days",
                )
            )
        else:
            warnings.append(
                _issue(
                    "DELIVERY_DATE_UNCONFIRMED",
                    "Production fits within the requested days, but transit and actual "
                    "delivery remain unconfirmed.",
                    field="requested_lead_days",
                )
            )
    # Document identity comes exclusively from validated, deterministic engine
    # fields. Presentation wording and generation time do not create revisions.
    # Including computed prices also detects catalog edits if its version label
    # was accidentally left unchanged.
    data["document_type"] = "foreign_trade_quote"
    data["document_version"] = 1
    identity_fields = {
        key: value for key, value in data.items()
        if key not in {"quotation_markdown", "price_basis"}
    }
    identity = json.dumps(
        {"catalog_version": _catalog()["catalog_version"], "quote": identity_fields},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    data["quote_id"] = "DEMO-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16].upper()
    return _response(data, warnings=warnings, record_refs=record_refs)
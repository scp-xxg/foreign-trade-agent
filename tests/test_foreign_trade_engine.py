"""Offline behavioral tests for the synthetic office-storage quote engine."""

from copy import deepcopy
from decimal import localcontext
import hashlib
import json
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "extensions"))
from foreign_trade import calculate_quote, get_product, search_products


class ForeignTradeEngineTests(unittest.TestCase):
    def quote(self, quantity=500, **kwargs):
        return calculate_quote([{"sku": "DESK-001", "quantity": quantity}], **kwargs)

    def assert_error(self, result, code):
        self.assertFalse(result["ok"])
        self.assertIsNone(result["data"])
        self.assertIn(code, {error["code"] for error in result["errors"]})
        json.dumps(result, allow_nan=False)

    def test_catalog_is_explicitly_simulated_and_traceable(self):
        result = search_products(limit=50)
        self.assertTrue(result["ok"])
        self.assertTrue(result["is_simulated"])
        self.assertEqual(result["catalog_version"], "office-storage-demo-v1")
        self.assertEqual(result["data"]["total_matches"], 8)
        self.assertEqual(len(result["source"]["record_refs"]), 8)
        for product in result["data"]["products"]:
            with self.subTest(sku=product["sku"]):
                self.assertTrue(product["is_simulated"])
                self.assertEqual(product["currency"], "USD")
                self.assertEqual(product["source"]["type"], "synthetic_demo_catalog")
                self.assertIn(product["sku"], product["source"]["record_ref"])
                self.assertEqual(product["price_tiers"][0]["min_quantity"], product["moq"])
                self.assertIsNone(product["price_tiers"][-1]["max_quantity"])
                for left, right in zip(product["price_tiers"], product["price_tiers"][1:]):
                    self.assertEqual(left["max_quantity"] + 1, right["min_quantity"])

    def test_search_supports_sku_chinese_words_and_categories(self):
        for kwargs, expected in [
            ({"query": "  desk-001 "}, ["DESK-001"]),
            ({"query": "模块化"}, ["DESK-001"]),
            ({"query": "desk organizer"}, ["DESK-001", "DESK-002"]),
            ({"query": "modular desk organizer"}, ["DESK-001"]),
            ({"category": "文件收纳", "limit": 50}, ["FILE-001", "FILE-002"]),
            ({"category": "FILE-STORAGE", "limit": 50}, ["FILE-001", "FILE-002"]),
            ({"query": "unlisted gadget"}, []),
            ({"category": "unlisted-category"}, []),
        ]:
            with self.subTest(kwargs=kwargs):
                result = search_products(**kwargs)
                self.assertTrue(result["ok"])
                self.assertEqual([p["sku"] for p in result["data"]["products"]], expected)

    def test_search_limit_preserves_total_matches(self):
        result = search_products(limit=2)["data"]
        self.assertEqual(result["total_matches"], 8)
        self.assertEqual(result["returned_count"], 2)
        self.assertEqual(len(result["products"]), 2)

    def test_search_rejects_nonstring_filters_and_invalid_limit(self):
        for kwargs, code in [
            ({"query": None}, "INVALID_QUERY"),
            ({"category": []}, "INVALID_CATEGORY"),
            *[({"limit": limit}, "INVALID_LIMIT") for limit in (True, 2.0, "2", 0, -1, 51)],
        ]:
            with self.subTest(kwargs=kwargs):
                self.assert_error(search_products(**kwargs), code)

    def test_get_product_normalizes_sku_and_returns_packaging_rules(self):
        result = get_product(" desk-001 ")
        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["sku"], "DESK-001")
        self.assertEqual(result["data"]["moq"], 100)
        self.assertTrue(result["data"]["packaging"]["standard"]["included_in_price"])
        self.assertEqual(result["data"]["packaging"]["custom"]["unit_surcharge"], "0.30")
        self.assertEqual(result["data"]["packaging"]["custom"]["moq"], 500)

    def test_get_product_handles_unknown_or_missing_sku(self):
        self.assert_error(get_product("MISSING-001"), "UNKNOWN_SKU")
        for sku in (None, "", " ", True, 100, []):
            with self.subTest(sku=sku):
                self.assert_error(get_product(sku), "INVALID_SKU")

    def test_requested_baseline_quotes_are_exact(self):
        for quantity, expected in [(500, "2400.00"), (2000, "8400.00")]:
            with self.subTest(quantity=quantity):
                result = self.quote(quantity)
                self.assertTrue(result["ok"])
                self.assertEqual(result["data"]["subtotal"], expected)
                self.assertEqual(result["data"]["packaging_subtotal"], "0.00")

    def test_tier_boundaries_use_entire_line_quantity(self):
        expected = {
            100: ("5.20", "520.00"),
            499: ("5.20", "2594.80"),
            500: ("4.80", "2400.00"),
            1999: ("4.80", "9595.20"),
            2000: ("4.20", "8400.00"),
        }
        for quantity, (price, subtotal) in expected.items():
            with self.subTest(quantity=quantity):
                result = self.quote(quantity)["data"]
                self.assertEqual(result["items"][0]["unit_price"], price)
                self.assertEqual(result["subtotal"], subtotal)

    def test_invalid_quantities_never_generate_partial_prices(self):
        for quantity in (None, True, False, 500.0, 0.5, "500", 0, -100, [], {}):
            with self.subTest(quantity=quantity):
                self.assert_error(self.quote(quantity), "INVALID_QUANTITY")

    def test_quantity_below_product_moq_is_rejected(self):
        self.assert_error(self.quote(99), "BELOW_MOQ")
        self.assertTrue(self.quote(100)["ok"])

    def test_custom_packaging_has_separate_cost_and_production_time(self):
        result = calculate_quote(
            [{"sku": "DESK-001", "quantity": 500, "custom_packaging": True}]
        )["data"]
        self.assertEqual(result["merchandise_subtotal"], "2400.00")
        self.assertEqual(result["packaging_subtotal"], "150.00")
        self.assertEqual(result["subtotal"], "2550.00")
        self.assertEqual(result["production_lead_days"], 18)
        self.assertEqual(result["items"][0]["effective_unit_price"], "5.10")
        self.assertEqual(result["items"][0]["packaging_unit_surcharge"], "0.30")

    def test_custom_packaging_moq_and_unsupported_products_are_errors(self):
        result = calculate_quote(
            [{"sku": "DESK-001", "quantity": 499, "custom_packaging": True}]
        )
        self.assert_error(result, "BELOW_CUSTOM_PACKAGING_MOQ")
        for sku, quantity in [("DRAWER-001", 150), ("MONITOR-001", 50)]:
            with self.subTest(sku=sku):
                self.assert_error(
                    calculate_quote([{"sku": sku, "quantity": quantity, "custom_packaging": True}]),
                    "CUSTOM_PACKAGING_UNSUPPORTED",
                )

    def test_custom_packaging_must_be_boolean(self):
        for value in ("false", "true", 0, 1, None, [], {}):
            with self.subTest(value=value):
                self.assert_error(
                    calculate_quote(
                        [{"sku": "DESK-001", "quantity": 500, "custom_packaging": value}]
                    ),
                    "INVALID_CUSTOM_PACKAGING",
                )

    def test_duplicates_are_rejected_before_tier_calculation(self):
        result = calculate_quote(
            [{"sku": "DESK-001", "quantity": 250}, {"sku": " desk-001 ", "quantity": 250}]
        )
        self.assert_error(result, "DUPLICATE_SKU")
        self.assertEqual(len(result["source"]["record_refs"]), 1)

    def test_unknown_item_invalid_shape_and_price_overrides_are_rejected(self):
        for items, code in [
            ([], "INVALID_ITEMS"),
            (None, "INVALID_ITEMS"),
            ({}, "INVALID_ITEMS"),
            (({"sku": "DESK-001", "quantity": 500},), "INVALID_ITEMS"),
            ([None], "INVALID_ITEM"),
            ([{}], "INVALID_SKU"),
            ([{"sku": "NOT-REAL", "quantity": 500}], "UNKNOWN_SKU"),
            (
                [{"sku": "DESK-001", "quantity": 500, "unit_price": "0.01"}],
                "UNSUPPORTED_ITEM_FIELDS",
            ),
        ]:
            with self.subTest(items=items):
                self.assert_error(calculate_quote(items), code)

    def test_mixed_valid_and_invalid_lines_do_not_create_partial_quote(self):
        result = calculate_quote(
            [{"sku": "DESK-001", "quantity": 500}, {"sku": "FILE-001", "quantity": 99}]
        )
        self.assert_error(result, "BELOW_MOQ")
        self.assertEqual(result["errors"][0]["item_index"], 1)

    def test_multiple_lines_sum_goods_and_packaging_with_longest_production(self):
        items = [
            {"sku": "DESK-001", "quantity": 500, "custom_packaging": True},
            {"sku": "FILE-001", "quantity": 500},
            {"sku": "MONITOR-001", "quantity": 50},
        ]
        result = calculate_quote(items, "Germany")["data"]
        self.assertEqual(result["merchandise_subtotal"], "4725.00")
        self.assertEqual(result["packaging_subtotal"], "150.00")
        self.assertEqual(result["subtotal"], "4875.00")
        self.assertEqual(result["production_lead_days"], 25)
        reversed_result = calculate_quote(list(reversed(items)), "Germany")["data"]
        for field in ("merchandise_subtotal", "packaging_subtotal", "subtotal", "production_lead_days"):
            self.assertEqual(result[field], reversed_result[field])

    def test_freight_is_unknown_for_every_destination(self):
        for destination in ("", "  ", "Germany", "US", "Atlantis"):
            with self.subTest(destination=destination):
                result = self.quote(destination_country=destination)
                data = result["data"]
                self.assertTrue(result["ok"])
                self.assertTrue(data["subtotal_excludes_freight"])
                self.assertTrue(data["subtotal_excludes_taxes_and_duties"])
                self.assertEqual(data["freight"]["status"], "pending_confirmation")
                self.assertIsNone(data["freight"]["amount"])
                self.assertIsNone(data["transit_lead_days"])
                self.assertIsNone(data["delivery_lead_days"])
                self.assertEqual(data["subtotal"], "2400.00")
                codes = {warning["code"] for warning in result["warnings"]}
                self.assertIn("FREIGHT_UNCONFIRMED", codes)
                self.assertEqual("DESTINATION_REQUIRED" in codes, not destination.strip())

    def test_invalid_destination_type_is_an_error(self):
        for destination in (None, 1, True, [], {}):
            with self.subTest(destination=destination):
                self.assert_error(self.quote(destination_country=destination), "INVALID_DESTINATION")

    def test_requested_deadline_never_promises_delivery(self):
        for days, status, warning in [
            (14, "cannot_meet_production_window", "REQUESTED_LEAD_TOO_SHORT"),
            (15, "requires_confirmation", "DELIVERY_DATE_UNCONFIRMED"),
            (30, "requires_confirmation", "DELIVERY_DATE_UNCONFIRMED"),
        ]:
            with self.subTest(days=days):
                result = self.quote(requested_lead_days=days)
                self.assertTrue(result["ok"])
                self.assertEqual(result["data"]["requested_delivery_status"], status)
                self.assertIn(warning, {w["code"] for w in result["warnings"]})
        self.assertEqual(self.quote()["data"]["requested_delivery_status"], "not_requested")

    def test_invalid_requested_days_are_rejected(self):
        for days in (0, -1, 15.0, True, "15", [], {}):
            with self.subTest(days=days):
                self.assert_error(
                    self.quote(requested_lead_days=days), "INVALID_REQUESTED_LEAD_DAYS"
                )

    def test_decimal_results_do_not_depend_on_callers_decimal_context(self):
        with localcontext() as context:
            context.prec = 2
            result = calculate_quote(
                [{"sku": "DESK-001", "quantity": 1999, "custom_packaging": True}]
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["merchandise_subtotal"], "9595.20")
        self.assertEqual(result["data"]["packaging_subtotal"], "599.70")
        self.assertEqual(result["data"]["subtotal"], "10194.90")

    def test_large_integer_quote_retains_all_digits(self):
        result = self.quote(10**30)["data"]
        self.assertEqual(result["subtotal"], "4200000000000000000000000000000.00")

    def test_input_and_return_values_cannot_mutate_catalog(self):
        items = [{"sku": "DESK-001", "quantity": 500}]
        original = deepcopy(items)
        quote = calculate_quote(items)
        self.assertEqual(items, original)
        quote["data"]["items"][0]["applied_price_tier"]["unit_price"] = "0.01"
        detail = get_product("DESK-001")
        detail["data"]["price_tiers"][1]["unit_price"] = "0.02"
        search = search_products()
        search["data"]["products"][0]["packaging"]["custom"]["unit_surcharge"] = "0.03"
        self.assertEqual(self.quote()["data"]["subtotal"], "2400.00")
        self.assertEqual(
            get_product("DESK-001")["data"]["packaging"]["custom"]["unit_surcharge"], "0.30"
        )

    def test_results_are_deterministic_json_and_source_file_is_unchanged(self):
        catalog_path = (
            Path(__file__).resolve().parents[1] / "extensions" / "foreign_trade" / "catalog.json"
        )
        before = hashlib.sha256(catalog_path.read_bytes()).hexdigest()
        first = self.quote(destination_country="France", requested_lead_days=30)
        second = self.quote(destination_country="France", requested_lead_days=30)
        self.assertEqual(first, second)
        self.assertEqual(json.loads(json.dumps(first, allow_nan=False)), first)
        self.assertEqual(before, hashlib.sha256(catalog_path.read_bytes()).hexdigest())

    def test_quoting_requires_no_network_or_model(self):
        with patch("socket.socket", side_effect=AssertionError("network is forbidden")):
            result = self.quote()
            self.assertTrue(result["ok"])
            self.assertTrue(search_products(query="收纳")["ok"])
            self.assertTrue(get_product("DESK-001")["ok"])


if __name__ == "__main__":
    unittest.main()

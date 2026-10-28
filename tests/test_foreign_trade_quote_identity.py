"""Export identity is derived from the successful engine quote, never model text."""
from copy import deepcopy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "extensions"))
from foreign_trade import engine


class QuoteIdentityTests(unittest.TestCase):
    def quote(self, **changes):
        arguments = {
            "items": [{"sku": "DESK-001", "quantity": 500, "custom_packaging": False}],
            "destination_country": "Spain",
            "requested_lead_days": None,
        }
        arguments.update(changes)
        return engine.calculate_quote(**arguments)

    def test_success_is_explicitly_identified_as_exportable_quote(self):
        result = self.quote()
        self.assertTrue(result["ok"])
        data = result["data"]
        self.assertEqual(data["document_type"], "foreign_trade_quote")
        self.assertEqual(data["document_version"], 1)
        self.assertRegex(data["quote_id"], r"^DEMO-[0-9A-F]{16}$")
        self.assertEqual(data["subtotal"], "2400.00")

    def test_identity_is_stable_for_equivalent_normalized_inputs(self):
        expected = self.quote()["data"]["quote_id"]
        self.assertEqual(self.quote()["data"]["quote_id"], expected)
        normalized = self.quote(
            items=[{"quantity": 500, "sku": " desk-001 "}],
            destination_country=" Spain ",
        )
        self.assertEqual(normalized["data"]["quote_id"], expected)

    def test_each_commercial_revision_changes_identity(self):
        baseline = self.quote()["data"]["quote_id"]
        changes = [
            {"items": [{"sku": "DESK-001", "quantity": 1000}]},
            {"items": [{"sku": "DESK-001", "quantity": 500, "custom_packaging": True}]},
            {"destination_country": "France"},
            {"requested_lead_days": 10},
            {"requested_lead_days": 30},
        ]
        revisions = set()
        for change in changes:
            with self.subTest(change=change):
                result = self.quote(**change)
                self.assertTrue(result["ok"])
                self.assertNotEqual(result["data"]["quote_id"], baseline)
                revisions.add(result["data"]["quote_id"])
        self.assertEqual(len(revisions), len(changes))

    def test_catalog_version_is_part_of_identity(self):
        baseline = self.quote()["data"]["quote_id"]
        catalog = deepcopy(engine._catalog())
        catalog["catalog_version"] = "office-storage-demo-v2"
        with patch.object(engine, "_catalog", return_value=catalog):
            self.assertNotEqual(self.quote()["data"]["quote_id"], baseline)

    def test_computed_price_is_part_of_identity_even_if_version_unchanged(self):
        baseline = self.quote()["data"]["quote_id"]
        catalog = deepcopy(engine._catalog())
        product = next(item for item in catalog["products"] if item["sku"] == "DESK-001")
        tier = next(tier for tier in product["price_tiers"] if tier["min_quantity"] == 500)
        tier["unit_price"] = "4.81"
        with patch.object(engine, "_catalog", return_value=catalog):
            self.assertNotEqual(self.quote()["data"]["quote_id"], baseline)

    def test_invalid_quote_never_has_export_data_or_identity(self):
        for items in [[], [{"sku": "DESK-001", "quantity": 1}], [{"sku": "UNKNOWN", "quantity": 500}]]:
            with self.subTest(items=items):
                result = self.quote(items=items)
                self.assertFalse(result["ok"])
                self.assertIsNone(result["data"])
                self.assertNotIn("quote_id", result)
                self.assertNotIn("document_type", result)

    def test_other_tool_payloads_are_not_marked_as_quotes(self):
        for result in [engine.search_products("desk"), engine.get_product("DESK-001")]:
            self.assertTrue(result["ok"])
            self.assertNotIn("quote_id", result["data"])
            self.assertNotIn("document_type", result["data"])


if __name__ == "__main__":
    unittest.main()

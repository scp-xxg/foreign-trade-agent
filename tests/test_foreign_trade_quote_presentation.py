"""The displayed quote must separate merchandise price from packaging charges."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "extensions"))
from foreign_trade.engine import calculate_quote

class QuotePresentationTests(unittest.TestCase):
    def test_custom_packaging_is_not_folded_into_goods_price(self):
        quote = calculate_quote([{"sku": "DESK-001", "quantity": 1000, "custom_packaging": True}], "Spain")
        row = quote["data"]["quotation_markdown"].splitlines()[2]
        cells = [x.strip() for x in row.strip("|").split("|")]
        self.assertEqual(cells, ["DESK-001", "1000", "4.80", "0.30", "4800.00", "300.00", "5100.00"])
        self.assertEqual(quote["data"]["items"][0]["effective_unit_price"], "5.10")
        self.assertIn("货品单价", quote["data"]["quotation_markdown"])

    def test_standard_packaging_has_no_additional_charge(self):
        quote = calculate_quote([{"sku": "DESK-001", "quantity": 500}], "Spain")
        cells = [x.strip() for x in quote["data"]["quotation_markdown"].splitlines()[2].strip("|").split("|")]
        self.assertEqual(cells, ["DESK-001", "500", "4.80", "0.00", "2400.00", "0.00", "2400.00"])
        self.assertTrue(quote["data"]["subtotal_excludes_freight"])

if __name__ == "__main__":
    unittest.main()

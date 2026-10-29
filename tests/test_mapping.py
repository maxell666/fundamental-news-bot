import unittest

from mapping import get_market_impact


class MappingTests(unittest.TestCase):
    def test_named_dow_value_is_not_automatically_assigned_to_nasdaq(self):
        _, assets, bias, category = get_market_impact(
            "Caterpillar tops quarterly profit estimates", category="EQUITIES"
        )
        self.assertIn("CAT", assets)
        self.assertIn("US30", assets)
        self.assertNotIn("NAS100", assets)
        self.assertEqual((bias, category), ("À confirmer", "EQUITIES"))

    def test_actual_gold_move_keeps_the_matching_asset(self):
        _, assets, _, _ = get_market_impact("Gold slides as inflation accelerates", category="MARKET")
        self.assertEqual(assets, ["XAUUSD"])

    def test_falling_oil_is_not_translated_into_an_automatic_bullish_impact(self):
        impacts, assets, bias, _ = get_market_impact("Oil prices plunge 5%", category="MARKET")
        self.assertIn("USOIL", assets)
        self.assertIn("UKOIL", assets)
        self.assertFalse(any("haussier" in impact for impact in impacts))
        self.assertEqual(bias, "À confirmer")


if __name__ == "__main__":
    unittest.main()

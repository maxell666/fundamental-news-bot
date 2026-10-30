import unittest
from unittest.mock import patch

from mapping import get_market_impact, priority_label
from portfolio import PortfolioAssessment, TRACKED_ASSETS


class MappingTests(unittest.TestCase):
    def impact(self, title, category="MACRO", description=""):
        return get_market_impact(description or title, title=title, category=category)

    def combined(self, title, category="MACRO", description=""):
        impacts, assets, bias, actual_category = self.impact(title, category, description)
        self.assertIsNone(bias)
        self.assertEqual(actual_category, category)
        self.assertTrue(set(assets) <= set(TRACKED_ASSETS))
        self.assertTrue(all(line.startswith("• ") for line in impacts))
        self.assertFalse(any(word in " ".join(impacts).lower() for word in ("à surveiller", "sensible", "réaction à confirmer")))
        return " ".join(impacts), assets

    def test_us10y_rise_changes_discount_rate_without_automatic_usd_strength(self):
        text, assets = self.combined("US 10-year Treasury yields rise to 4.5%", "MARKET")
        self.assertIn("NAS100", assets)
        self.assertIn("coût d'actualisation accru", text)
        self.assertIn("prime de terme", text)
        self.assertIn("aucun sens de change", text)
        self.assertNotIn("dollar se renforce", text)
        self.assertIn("GER30", assets)

    def test_us10y_fall_reduces_discount_rate(self):
        text, _ = self.combined("US 10-year Treasury yields fall to 4%", "MARKET")
        self.assertIn("rendements obligataires US en baisse", text)
        self.assertIn("coût d'actualisation réduit", text)

    def test_treasury_price_rally_inverts_yield_direction(self):
        text, assets = self.combined("US 10-year Treasury prices rally", "MARKET")
        self.assertIn("NAS100", assets)
        self.assertIn("rendements obligataires US en baisse", text)
        self.assertNotIn("US10Y en hausse", text)

    def test_treasury_price_fall_inverts_yield_direction(self):
        text, _ = self.combined("US 10-year Treasury prices fall", "MARKET")
        self.assertIn("US10Y en hausse", text)

    def test_us_inflation_above_consensus_has_correct_fx_legs(self):
        impacts, assets, bias, _ = self.impact("US CPI rises to 3.2% vs 3.0% expected")
        pair_line = next(line for line in impacts if "EUR/USD ; GBP/USD" in line)
        chf_line = next(line for line in impacts if line.startswith("• USD/CHF"))
        self.assertIn("baisse possible", pair_line)
        self.assertIn("hausse possible", chf_line)
        self.assertIn("si", pair_line)
        self.assertIn("NAS100", assets)
        self.assertIsNone(bias)

    def test_us_inflation_below_consensus_has_inverse_channel(self):
        impacts, _, _, _ = self.impact("US PCE 0.2% vs 0.3% forecast")
        self.assertIn("hausse possible", next(line for line in impacts if "EUR/USD ; GBP/USD" in line))
        self.assertIn("baisse possible", next(line for line in impacts if line.startswith("• USD/CHF")))
        self.assertIn("soutien possible", " ".join(impacts))

    def test_negative_inflation_numbers_keep_their_sign(self):
        text, _ = self.combined("US CPI -0.1% vs -0.2% expected")
        self.assertIn("au-dessus du consensus", text)
        self.assertNotIn("sous le consensus", text)

    def test_inflation_higher_than_previous_is_not_consensus_surprise(self):
        text, _ = self.combined("US CPI rises to 3.2% from 3.0% previously")
        self.assertIn("chiffre précédent", text)
        self.assertIn("écart au consensus", text)
        self.assertNotIn("baisse possible", text)
        self.assertNotIn("hausse possible", text)
        self.assertNotIn("au-dessus du consensus", text)

    def test_conflicting_headline_and_core_inflation_does_not_produce_one_arrow(self):
        text, _ = self.combined("US headline CPI below expectations but core CPI above forecasts")
        self.assertIn("contradictoires", text)
        self.assertIn("sans flèche unique", text)
        self.assertNotIn("baisse possible", text)
        self.assertNotIn("hausse possible", text)

    def test_conflicting_numeric_core_and_headline_results_are_mixed(self):
        text, _ = self.combined("US CPI 0.4% vs 0.3% expected; core CPI 0.2% vs 0.3% expected")
        self.assertIn("contradictoires", text)

    def test_fed_cut_describes_conditional_fx_and_discount_channels(self):
        text, assets = self.combined("Fed cuts interest rates by 25 basis points")
        self.assertIn("déjà intégré", text)
        self.assertIn("hausse possible si le différentiel de taux affaiblit le dollar", text)
        self.assertIn("baisse possible si le dollar s'affaiblit", text)
        self.assertIn("actualisation moins coûteux", text)
        self.assertNotIn("surprise", text)
        self.assertIn("GER30", assets)

    def test_ecb_hike_maps_euro_and_dax_only(self):
        text, assets = self.combined("ECB raises interest rates by 25 basis points")
        self.assertEqual(assets, ["EURUSD", "GER30"])
        self.assertIn("soutien possible à l'euro", text)
        self.assertIn("financement et actualisation plus coûteux", text)
        self.assertIn("DAX", text)

    def test_boe_cut_maps_sterling_leg_only(self):
        text, assets = self.combined("Bank of England cuts interest rates")
        self.assertEqual(assets, ["GBPUSD"])
        self.assertIn("pression possible sur la livre", text)

    def test_snb_hike_is_usdchf_down_not_up(self):
        text, assets = self.combined("SNB hikes interest rates")
        self.assertEqual(assets, ["USDCHF"])
        self.assertIn("baisse possible de USD/CHF", text)
        self.assertNotIn("hausse possible de USD/CHF", text)

    def test_snb_cut_is_usdchf_up(self):
        text, _ = self.combined("SNB cuts interest rates")
        self.assertIn("hausse possible de USD/CHF", text)

    def test_unchanged_rate_needs_consensus_and_forward_guidance(self):
        text, assets = self.combined("Fed leaves interest rates unchanged")
        self.assertTrue(assets)
        self.assertIn("maintient son taux", text)
        self.assertIn("écart au consensus", text)
        self.assertNotIn("baisse possible", text)
        self.assertNotIn("hausse possible", text)

    def test_hypothetical_cut_is_not_rendered_as_an_actual_decision(self):
        text, _ = self.combined("Fed signals rate cuts later this year")
        self.assertNotIn("baisse du taux directeur", text)
        self.assertNotIn("hausse possible", text)

    def test_official_support_for_cuts_is_a_communication_not_a_rate_cut(self):
        text, _ = self.combined("Fed's Warsh says rate cuts are appropriate")
        self.assertNotIn("baisse du taux directeur", text)
        self.assertNotIn("hausse possible", text)

    def test_jobs_report_keeps_profit_and_interest_channels_separate(self):
        text, _ = self.combined("US nonfarm payrolls rise 200000 vs 150000 expected")
        self.assertIn("ventes et bénéfices", text)
        self.assertIn("relever les taux attendus", text)
        self.assertIn("aucun sens automatique", text)

    def test_gdp_report_does_not_convert_growth_to_a_stock_prediction(self):
        text, _ = self.combined("US GDP grows 3.4% vs 3.2% expected")
        self.assertIn("ventes et bénéfices", text)
        self.assertIn("aucun sens automatique", text)

    def test_oil_production_cut_maps_energy_cost_and_trade_balance(self):
        text, assets = self.combined("OPEC cuts oil production by 1 million barrels a day", "ENERGY")
        self.assertIn("offre pétrolière réduite", text)
        self.assertIn("marges", text)
        self.assertIn("facture d'importation", text)
        self.assertIn("GER30", assets)
        self.assertNotIn("USDCHF", assets)

    def test_crude_inventory_build_does_not_say_energy_costs_rise(self):
        text, _ = self.combined("US crude oil inventories rise by 4 million barrels", "ENERGY")
        self.assertIn("coût énergétique potentiellement réduit", text)
        self.assertNotIn("renchérissement", text)
        self.assertIn("si cette évolution rend le pétrole moins cher", text)

    def test_actual_falling_oil_reaches_held_assets_without_oil_ticker(self):
        text, assets = self.combined("Oil prices plunge 5%", "MARKET")
        self.assertIn("pétrole en baisse", text)
        self.assertTrue(assets)
        self.assertNotIn("USOIL", assets)
        self.assertNotIn("UKOIL", assets)

    def test_actual_nasdaq_move_does_not_claim_other_indices_also_fell(self):
        text, assets = self.combined("Nasdaq falls 3% as Treasury yields rise", "MARKET")
        self.assertEqual(assets, ["NAS100"])
        self.assertIn("baisse observée", text)
        self.assertNotIn("SP500", text)
        self.assertNotIn("US10Y en hausse", text)

    def test_nasdaq_and_dow_can_have_opposite_observed_directions(self):
        text, assets = self.combined("Nasdaq falls 2%, Dow rises 1%", "MARKET")
        self.assertEqual(assets, ["NAS100", "US30"])
        self.assertIn("• NAS100 : baisse observée", text)
        self.assertIn("• US30 : hausse observée", text)

    def test_weak_company_guidance_is_conditionally_limited_to_held_indices(self):
        text, assets = self.combined("Nvidia cuts profit guidance after weak earnings", "EQUITIES")
        self.assertEqual(assets, ["SP500", "NAS100", "US30"])
        self.assertIn("lecture macro conditionnelle", text)
        self.assertIn("perspectives de bénéfices revues à la baisse", text)
        self.assertIn("poids dans ces indices", text)
        self.assertIn("sans prédire leur direction globale", text)
        self.assertNotIn("GER30", text)
        self.assertNotIn("NVDA", assets)

    def test_dow_member_has_no_fabricated_nasdaq_or_dax_exposure(self):
        text, assets = self.combined("JPMorgan reports earnings above expectations", "EQUITIES")
        self.assertEqual(assets, ["SP500", "US30"])
        self.assertIn("au-dessus du consensus", text)
        self.assertNotIn("NAS100", text)

    def test_tariffs_are_cost_and_trade_channels_not_fed_decisions(self):
        text, assets = self.combined("US imposes new tariffs on EU imports", "TRADE")
        self.assertIn("coûts d'importation", text)
        self.assertIn("GER30", assets)
        self.assertNotIn("communication de la Fed", text)
        self.assertNotIn("hausse possible", text)

    def test_routine_canadian_gdp_is_outside_this_portfolio(self):
        self.assertEqual(self.impact("Canada GDP rises to 3%")[:3], ([], [], None))

    def test_gold_only_story_has_no_fallback_held_assets(self):
        self.assertEqual(self.impact("Gold slides 5%", "MARKET")[:3], ([], [], None))

    def test_unknown_company_and_unrelated_subject_are_not_sp500_fallbacks(self):
        for title, category in (("SmallCo reports record profit", "EQUITIES"), ("Award-winning film celebrates life", "FONDAMENTAL")):
            with self.subTest(title=title):
                self.assertEqual(self.impact(title, category)[:3], ([], [], None))

    def test_usdchf_refuges_are_ambiguous_even_when_us_inflation_is_hot(self):
        gate = PortfolioAssessment(True, tuple(TRACKED_ASSETS), ("USD_DATA", "GLOBAL_RISK"), "Two factual channels")
        with patch("mapping.assess_portfolio", return_value=gate):
            impacts, _, _, _ = self.impact("US CPI above expectations amid flight to safety")
        chf_line = next(line for line in impacts if line.startswith("• USD/CHF"))
        self.assertIn("tous deux", chf_line)
        self.assertNotIn("hausse possible", chf_line)
        self.assertNotIn("baisse possible", chf_line)

    def test_major_regulatory_charge_does_not_predict_an_index_decline(self):
        gate = PortfolioAssessment(True, ("SP500", "NAS100"), ("REGULATORY",), "Confirmed material fine")
        with patch("mapping.assess_portfolio", return_value=gate):
            text, assets = self.combined("Meta fined $25bn for privacy violations", "EQUITIES")
        self.assertEqual(assets, ["SP500", "NAS100"])
        self.assertIn("bénéfices et la trésorerie", text)
        self.assertIn("poids dans ces indices", text)
        self.assertNotIn("baisse observée", text)

    def test_unknown_driver_does_not_make_a_generic_impact(self):
        gate = PortfolioAssessment(True, ("EURUSD",), ("UNKNOWN",), "Unsupported")
        with patch("mapping.assess_portfolio", return_value=gate):
            self.assertEqual(self.impact("An unclassified event")[:3], ([], [], None))

    def test_gate_cannot_introduce_a_foreign_asset(self):
        gate = PortfolioAssessment(True, ("XAUUSD", "EURUSD"), ("USD_DATA",), "Malformed scope")
        with patch("mapping.assess_portfolio", return_value=gate):
            _, assets, _, _ = self.impact("US CPI above expectations")
        self.assertEqual(assets, ["EURUSD"])

    def test_legacy_category_inference_uses_title_before_unrelated_description(self):
        _, _, _, category = get_market_impact("Meta fined $25bn in an unrelated case", title="Fed cuts interest rates")
        self.assertEqual(category, "MACRO")

    def test_inflation_does_not_borrow_a_gdp_or_eps_forecast_from_description(self):
        title = "US CPI rises to 3.2% from 3.0% previously"
        for summary in (
            "US GDP 3.4% vs 3.2% expected",
            "Nvidia reports earnings above expectations",
            title + " US GDP 3.4% vs 3.2% expected",
            "UK inflation came in below expectations last month",
        ):
            with self.subTest(summary=summary):
                text, _ = self.combined(title, description=summary)
                self.assertNotIn("inflation au-dessus du consensus", text)
                self.assertNotIn("inflation sous le consensus", text)
                self.assertNotIn("hausse possible", text)
                self.assertNotIn("baisse possible", text)

    def test_same_indicator_current_summary_can_supply_the_missing_forecast(self):
        text, _ = self.combined("US CPI rises to 3.2%", description="US CPI 3.2% vs 3.0% expected")
        self.assertIn("inflation au-dessus du consensus", text)

    def test_explicit_headline_consensus_is_not_replaced_by_another_country(self):
        text, _ = self.combined("US CPI above forecasts", description="UK core CPI below forecasts")
        self.assertIn("inflation au-dessus du consensus", text)
        self.assertNotIn("contradictoires", text)

    def test_opposing_core_component_in_same_report_is_preserved(self):
        text, _ = self.combined("US headline CPI above forecasts", description="US core CPI below forecasts")
        self.assertIn("contradictoires", text)
        self.assertNotIn("hausse possible", text)

    def test_other_inflation_indicator_is_not_cpi_consensus(self):
        text, _ = self.combined("US CPI rises to 3.2% from 3.0% previously", description="US PCE 0.4% vs 0.3% expected")
        self.assertNotIn("inflation au-dessus du consensus", text)

    def test_unrelated_pce_in_same_headline_is_not_cpi_consensus(self):
        text, _ = self.combined("US CPI rises from 3% to 3.2%; PCE 0.4% vs 0.3% expected")
        self.assertNotIn("inflation au-dessus du consensus", text)

    def test_different_inflation_periods_and_units_do_not_create_an_arrow(self):
        for title in (
            "US CPI y/y above forecasts for m/m inflation",
            "US core CPI y/y 3.2% vs 0.3% m/m expected",
            "US CPI 0.3% vs 20 bp forecast",
        ):
            with self.subTest(title=title):
                text, _ = self.combined(title)
                self.assertNotIn("hausse possible", text)
                self.assertNotIn("baisse possible", text)

    def test_previous_report_month_is_not_current_cpi_surprise(self):
        text, _ = self.combined("US October CPI rises to 3.2%", description="US September CPI above forecasts")
        self.assertNotIn("inflation au-dessus du consensus", text)

    def test_negated_forecast_comparison_never_becomes_an_above_consensus_fact(self):
        for title in ("US CPI fails to beat expectations", "US CPI is not above forecasts"):
            with self.subTest(title=title):
                text, _ = self.combined(title)
                self.assertNotIn("inflation au-dessus du consensus", text)
                self.assertNotIn("hausse possible", text)
                self.assertNotIn("baisse possible", text)

    def test_us10y_direction_is_not_borrowed_from_two_year_yield(self):
        text, _ = self.combined("US10Y falls as 2-year Treasury yields rise", "MARKET")
        self.assertIn("en baisse", text)
        self.assertNotIn("US10Y en hausse", text)
        self.assertNotIn("coût d'actualisation accru", text)

    def test_two_year_yield_is_not_named_us10y(self):
        text, _ = self.combined("US Treasury 2-year yields rise to 4.5%", "MARKET")
        self.assertIn("rendements obligataires US en hausse", text)
        self.assertNotIn("US10Y", text)

    def test_standalone_us10y_quote_has_a_yield_direction(self):
        text, _ = self.combined("US10Y rises to 4.5%", "MARKET")
        self.assertIn("US10Y en hausse", text)

    def test_policy_action_stays_with_the_primary_bank(self):
        cases = (
            ("SNB hikes rates while Fed cuts interest rates", "BNS", "USDCHF"),
            ("Bank of England raises interest rates after Fed cuts rates", "BoE", "GBPUSD"),
            ("ECB raises rates while Fed cuts borrowing costs", "BCE", "EURUSD"),
            ("Fed raises rates, ECB cuts rates", "Fed", "EURUSD"),
        )
        for title, bank, asset in cases:
            with self.subTest(title=title):
                text, assets = self.combined(title)
                self.assertIn(asset, assets)
                self.assertIn(bank + " : hausse du taux directeur", text)
                self.assertNotIn(bank + " : baisse du taux directeur", text)

    def test_opposite_earnings_and_guidance_are_explicitly_mixed(self):
        for title in (
            "Nvidia beats earnings estimates but cuts revenue guidance",
            "Nvidia earnings below consensus but raises profit guidance",
            "Nvidia beats earnings estimates, cuts revenue guidance",
        ):
            with self.subTest(title=title):
                text, _ = self.combined(title, "EQUITIES")
                self.assertIn("contrastés", text)
                self.assertIn("sans sens unique", text)
                self.assertNotIn("contribution bénéficiaire de la société potentiellement accrue", text)

    def test_revenue_beat_does_not_claim_a_profit_beat(self):
        text, _ = self.combined("Nvidia reports revenue above expectations", "EQUITIES")
        self.assertIn("chiffre d'affaires au-dessus du consensus", text)
        self.assertIn("bénéfices dépend notamment des coûts", text)
        self.assertNotIn("contribution bénéficiaire de la société potentiellement accrue", text)

    def test_direct_chf_cross_move_is_not_extended_to_other_fx_pairs(self):
        for title in (
            "Dollar falls against Swiss franc",
            "Swiss franc rises against dollar after SNB rate hike",
        ):
            with self.subTest(title=title):
                text, assets = self.combined(title, "MARKET")
                self.assertEqual(assets, ["USDCHF"])
                self.assertIn("• USD/CHF : baisse observée", text)
                self.assertNotIn("EUR/USD", text)
                self.assertNotIn("GBP/USD", text)

    def test_fx_display_uses_slash_but_returned_ids_remain_canonical(self):
        text, assets = self.combined("Fed cuts interest rates")
        self.assertIn("EUR/USD ; GBP/USD", text)
        self.assertIn("USD/CHF", text)
        self.assertIn("EURUSD", assets)
        self.assertNotIn("EUR/USD", assets)

    def test_ceasefire_explains_deescalation_not_an_increase_in_risk_premium(self):
        gate = PortfolioAssessment(True, ("GER30", "USDCHF", "SP500", "NAS100", "US30"), ("GLOBAL_RISK",), "Confirmed nationwide ceasefire")
        with patch("mapping.assess_portfolio", return_value=gate):
            text, _ = self.combined("Iran and Israel agree nationwide ceasefire", "GEO")
        self.assertIn("réduction possible de la prime de risque", text)
        self.assertNotIn("potentiellement accrus", text)
        self.assertNotIn("hausse observée", text)

    def test_invasion_keeps_an_escalation_channel_without_fabricated_observed_move(self):
        gate = PortfolioAssessment(True, ("GER30", "USDCHF", "SP500", "NAS100", "US30"), ("GLOBAL_RISK",), "Confirmed invasion")
        with patch("mapping.assess_portfolio", return_value=gate):
            text, _ = self.combined("Russia launches invasion of Ukraine", "GEO")
        self.assertIn("escalade géopolitique", text)
        self.assertIn("ne prouve pas une baisse observée", text)

    def test_boj_carry_trade_shock_is_a_funding_channel_not_geopolitics(self):
        gate = PortfolioAssessment(True, ("GER30", "USDCHF", "SP500", "NAS100", "US30"), ("GLOBAL_RISK",), "Surprise BoJ decision")
        with patch("mapping.assess_portfolio", return_value=gate):
            text, _ = self.combined("BOJ delivers surprise rate hike as carry trades unwind")
        self.assertIn("financement et carry trades", text)
        self.assertNotIn("géopolitique", text)

    def test_common_messages_remain_bounded_without_copying_full_source_content(self):
        for title, category in (("Fed cuts interest rates", "MACRO"), ("US CPI above forecasts", "MACRO"), ("OPEC cuts oil production by 1 million barrels a day", "ENERGY")):
            with self.subTest(title=title):
                text, _ = self.combined(title, category, "Untrusted source content. " * 500)
                self.assertLessEqual(len(text), 2400)
                self.assertNotIn("Untrusted source content", text)

    def test_real_reuters_nasdaq_low_has_a_level_reading_without_a_session_drop(self):
        title = "Nasdaq hits near three-month low as Amazon, Intel deepen AI capex concerns - Reuters"
        text, assets = self.combined(title, "MARKET")
        self.assertEqual(assets, ["NAS100"])
        self.assertIn("niveau proche d'un creux signalé", text)
        self.assertIn("ne donne pas la variation de la séance", text)
        self.assertNotIn("baisse observée", text)
        self.assertNotIn("%", text)

    def test_benchmark_high_is_an_observed_level_not_an_invented_daily_gain(self):
        text, assets = self.combined("S&P 500 hits near record high", "MARKET")
        self.assertEqual(assets, ["SP500"])
        self.assertIn("niveau proche d'un sommet signalé", text)
        self.assertNotIn("hausse observée", text)

    def test_other_benchmark_clause_cannot_erase_or_expand_primary_low(self):
        gate = PortfolioAssessment(True, ("NAS100",), ("OBSERVED_MOVE",), "Primary benchmark")
        with patch("mapping.assess_portfolio", return_value=gate):
            text, assets = self.combined("Nasdaq hits near three-month low while DAX rises", "MARKET")
        self.assertEqual(assets, ["NAS100"])
        self.assertIn("niveau proche d'un creux signalé", text)
        self.assertNotIn("GER30", text)
        self.assertNotIn("hausse observée", text)

    def test_unknown_benchmark_level_does_not_get_a_generic_portfolio(self):
        self.assertEqual(self.impact("SmallCo index hits a three-month low", "MARKET")[:3], ([], [], None))

    def test_priority_label_remains_compatible(self):
        self.assertEqual([priority_label(value) for value in (4, 5, 9)], ["WATCH", "HIGH", "CRITICAL"])


if __name__ == "__main__":
    unittest.main()

import unittest

from portfolio import TRACKED_ASSETS, assess_portfolio


class PortfolioTests(unittest.TestCase):
    def assert_assets(self, title, expected, description="", category=None):
        result = assess_portfolio(title, description, category)
        self.assertEqual(set(result.assets), set(expected), result)
        self.assertEqual(result.relevant, bool(expected), result)
        self.assertTrue(result.reason)
        self.assertEqual(len(result.assets), len(set(result.assets)))
        self.assertTrue(set(result.assets) <= set(TRACKED_ASSETS))
        return result

    def test_us_data_and_fed_cover_usd_legs_and_the_three_us_indices(self):
        targets = ("EURUSD", "GBPUSD", "USDCHF", "SP500", "NAS100", "US30")
        for title in (
            "US GDP Advance for the 3rd quarter 3.4% vs 3.2% estimate",
            "Robust consumer spending, AI-related investment power US economy in third quarter",
            "PCE inflation slows more than expected",
            "US headline CPI below expectations but core CPI above forecasts",
            "Powell says interest rates could remain high",
        ):
            with self.subTest(title=title):
                self.assert_assets(title, targets, category="MACRO")
        result = self.assert_assets("US unemployment rate rises to 4.3%", targets, category="MACRO")
        self.assertEqual(result.drivers, ("USD_DATA",))
        for title in (
            "Fed holds interest rates steady in last decision before midterms",
            "The full statement from the Federal Reserve rate decision. Hikes by 25 basis points",
        ):
            with self.subTest(title=title):
                self.assert_assets(title, TRACKED_ASSETS, category="MACRO")

    def test_core_economies_map_only_their_direct_currency_and_index_links(self):
        for title, expected in (
            ("German inflation slows in October", ("EURUSD", "GER30")),
            ("Euro zone economy grows 0.4% in Q3", ("EURUSD", "GER30")),
            ("ECB keeps rates unchanged", ("EURUSD", "GER30")),
            ("UK retail sales fall 0.5%", ("GBPUSD",)),
            ("Bank of England raises interest rates", ("GBPUSD",)),
            ("SNB hikes interest rates", ("USDCHF",)),
            ("Swiss CPI inflation slows to 1.2%", ("USDCHF",)),
            ("SNB intervenes to weaken the Swiss franc", ("USDCHF",)),
        ):
            with self.subTest(title=title):
                self.assert_assets(title, expected, category="MACRO")

    def test_summary_identifies_a_bare_rate_decision_but_never_replaces_a_foreign_subject(self):
        self.assert_assets("Interest rates held at 2.5%", ("EURUSD", "GER30"),
                           "The European Central Bank kept its deposit rate unchanged.", "MACRO")
        for title in (
            "Canada GDP for August 0.0% vs 0.2% estimate",
            "Australia inflation rises to 4.3%",
            "New Zealand GDP falls 0.4%",
        ):
            with self.subTest(title=title):
                self.assert_assets(title, (), "The Federal Reserve kept US rates unchanged earlier this week.", "MACRO")

    def test_routine_foreign_macro_and_central_bank_accounting_are_outside_the_universe(self):
        for title in (
            "Spain Q3 GDP growth slows slightly",
            "French output shrinks and inflation accelerates",
            "BOJ governor Ueda says will stick to rate hike path in response to latest macro developments",
            "BoJ declares underlying inflation at 2% target, lifts FY2027 price forecast as rates held",
            "Swiss central bank posts bumper $23bn profit thanks to gold, foreign assets",
        ):
            with self.subTest(title=title):
                self.assert_assets(title, (), category="MACRO")

    def test_japan_requires_a_real_surprise_or_linked_global_transmission(self):
        expected = ("GER30", "USDCHF", "SP500", "NAS100", "US30")
        self.assert_assets("BOJ unexpectedly raises interest rates", expected, category="MACRO")
        self.assert_assets("BOJ rate rise triggers global stock selloff and carry trade unwind", expected, category="MACRO")
        self.assert_assets("BOJ governor Ueda says rates will stay on hold", (),
                           "Meanwhile global stocks plunge after weak Microsoft earnings.", "MACRO")
        self.assert_assets("BOJ raises rates", expected,
                           "The BOJ decision triggers a global selloff as yen carry trades unwind.", "MACRO")

    def test_chinese_activity_has_a_german_export_channel_but_politics_alone_does_not(self):
        self.assert_assets("China PMI falls to 48.0", ("GER30",), category="MACRO")
        self.assert_assets("China GDP contracts and sparks Wall Street selloff", ("GER30", "SP500", "NAS100", "US30"), category="MACRO")
        self.assert_assets("China's Communist Party conclave on toughening discipline sees record expulsions", ())

    def test_observed_us_treasury_yields_and_bond_prices_are_both_rate_channels(self):
        targets = TRACKED_ASSETS
        for title in (
            "US 10-year Treasury yields rise to 4.5%",
            "US 10-year Treasury bond prices rally as yields fall",
            "10-year US Treasury prices fall",
            "(Some good news!) Treasuries rally as AI selloff drives flight to safety, 10-year yield at one-month low",
            "US Treasury 10-year auction tails by 2 basis points",
        ):
            with self.subTest(title=title):
                result = self.assert_assets(title, targets, category="MARKET")
                self.assertEqual(result.drivers, ("US10Y",))
        self.assert_assets("US 10-year Treasury yields expected to rise next week", (), category="MARKET")
        self.assert_assets("US Treasury announces date of its next 10-year auction", (), category="MACRO")

    def test_energy_supply_and_price_shocks_have_conditional_index_and_cost_channels(self):
        expected = ("EURUSD", "GBPUSD", "GER30", "SP500", "NAS100", "US30")
        for title in (
            "Iran closes Strait of Hormuz to shipping",
            "Tanker in Strait of Hormuz hit by limpet mines, security sources say",
            "US imposes new sanctions on Russian oil exports",
            "Russia extends diesel export ban",
            "OPEC cuts oil output",
            "US crude inventories fall by 8 million barrels",
            "Brent jumps 5% after pipeline outage",
        ):
            with self.subTest(title=title):
                result = self.assert_assets(title, expected, category="ENERGY")
                self.assertEqual(result.drivers, ("OIL",))
        for title in (
            "Oil prices rise 0.2% in quiet trading",
            "Oil spill hits UAE beaches after tanker collision",
            "Woman scared to turn heating on due to oil cost",
        ):
            with self.subTest(title=title):
                self.assert_assets(title, (), category="ENERGY")

    def test_actual_trade_exposure_is_independent_of_the_originating_country(self):
        targets = ("EURUSD", "GBPUSD", "USDCHF", "SP500", "NAS100", "US30")
        for title in (
            "White House lifts tariffs on some Canadian goods",
            "Canada lifts tariffs on US imports",
            "Trump cuts tariffs on Chinese imports",
        ):
            with self.subTest(title=title):
                self.assert_assets(title, targets, category="TRADE")
        self.assert_assets("US imposes new tariffs on EU imports", TRACKED_ASSETS, category="TRADE")

    def test_verified_secondary_dax_components_require_a_material_event(self):
        for company in ("BMW", "Mercedes-Benz", "Volkswagen", "BASF", "Deutsche Bank"):
            with self.subTest(company=company):
                self.assert_assets(company + " shares plunge 15%", ("GER30",), category="EQUITIES")
                self.assert_assets(company + " reports profits above estimates", (), category="EQUITIES")
        self.assert_assets("BMW to acquire an automotive supplier for €8 billion", ("GER30",), category="EQUITIES")
        self.assert_assets("Porsche shares plunge 20%", (), category="EQUITIES")

    def test_material_company_links_are_curated_not_inferred_from_a_ticker_or_country(self):
        for title, expected in (
            ("Microsoft profits soar after layoffs", ("SP500", "NAS100", "US30")),
            ("Amazon AWS posts 39% revenue growth", ("SP500", "NAS100", "US30")),
            ("Intel plummets over 28% as weak forecast overshadows earnings beat", ("SP500", "NAS100")),
            ("Caterpillar tops quarterly profit estimates", ("SP500", "US30")),
            ("ExxonMobil beats quarterly profit estimates", ("SP500",)),
            ("SAP posts record quarterly revenue", ("GER30",)),
        ):
            with self.subTest(title=title):
                self.assert_assets(title, expected, category="EQUITIES")
        for title in (
            "Iradimed Co earnings matched, revenue topped estimates",
            "ADT reports record profits",
            "Fortinet profits rise 28%",
            "Apple customers report revenue gains",
        ):
            with self.subTest(title=title):
                self.assert_assets(title, (), category="EQUITIES")
        self.assert_assets("Fortinet shares plunge 25%", ("SP500", "NAS100"), category="EQUITIES")

    def test_announced_guidance_survives_conditional_wording_and_price_predictions_do_not(self):
        expected = ("SP500", "NAS100", "US30")
        for title in (
            "Amazon says profits could fall next quarter",
            "Amazon forecasts revenue of $50bn next quarter",
            "Amazon expects to report higher revenue next quarter",
        ):
            with self.subTest(title=title):
                result = self.assert_assets(title, expected, category="EQUITIES")
                self.assertEqual(result.drivers, ("GUIDANCE",))
        for title in (
            "Amazon to report Q3 earnings after the bell",
            "Analysts expect Intel shares to fall 28%",
            "Nvidia shares forecast to plunge 12%",
        ):
            with self.subTest(title=title):
                self.assert_assets(title, (), category="EQUITIES")

    def test_exceptional_regulatory_charge_and_acquisition_are_separate_company_drivers(self):
        result = self.assert_assets("Meta fined $25bn for privacy violations", ("SP500", "NAS100"), category="EQUITIES")
        self.assertEqual(result.drivers, ("REGULATORY",))
        self.assert_assets("Meta fined $20 million for privacy violations", (), category="EQUITIES")
        result = self.assert_assets("DoorDash to buy Instacart in $17bn deal", ("SP500", "NAS100"), category="EQUITIES")
        self.assertEqual(result.drivers, ("CORPORATE",))
        self.assert_assets("Unknown Startup buys Instacart for $17bn", (), category="EQUITIES")

    def test_observed_tracked_instruments_use_only_the_requested_identifiers(self):
        for title, expected in (
            ("EUR/USD trades lower", ("EURUSD",)),
            ("GBPUSD falls 1%", ("GBPUSD",)),
            ("USD/CHF rises 0.5%", ("USDCHF",)),
            ("GER40 edges higher", ("GER30",)),
            ("S&P 500 falls 2%", ("SP500",)),
            ("Nasdaq tumbles at open as Amazon, Intel add to AI spending woes", ("NAS100",)),
            ("DAX rises while Nasdaq falls", ("GER30", "NAS100")),
            ("Software stocks slide as Fortinet, ServiceNow fail to meet lofty investor expectations", ("SP500", "NAS100")),
            ("Dollar falls against Swiss franc", ("USDCHF",)),
            ("US dollar falls against the euro", ("EURUSD",)),
            ("Dollar rises against yen", ()),
            ("Dollar falls broadly", ("EURUSD", "GBPUSD", "USDCHF")),
        ):
            with self.subTest(title=title):
                self.assert_assets(title, expected, category="MARKET")
        self.assert_assets("USD/CHF expected to rise", (), category="MARKET")

    def test_metals_local_stories_and_historical_sport_never_create_a_portfolio_link(self):
        for title in (
            "Gold hits four-month low on Fed hike fears",
            "Gold falls below $4,000 as inflation concerns keep bullion under pressure",
            "UK needs to be ready for emergencies and hostile acts, warns Streeting",
            "Russia to host first Olympic federation world event since Ukraine invasion",
            "UK energy poised for more deals amid high taxes and oil prices",
        ):
            with self.subTest(title=title):
                self.assert_assets(title, ())

    def test_confirmed_strategic_war_is_relevant_without_a_market_price_in_the_title(self):
        expected = ("GER30", "USDCHF", "SP500", "NAS100", "US30")
        for title in ("Russia invades Ukraine", "US declares war on Iran",
                      "Russia deploys tactical nuclear weapons in Belarus"):
            with self.subTest(title=title):
                result = self.assert_assets(title, expected, category="GEO")
                self.assertEqual(result.drivers, ("GLOBAL_RISK",))

    def test_national_ceasefire_and_its_breakdown_are_material_without_assuming_a_direction(self):
        expected = ("GER30", "USDCHF", "SP500", "NAS100", "US30")
        for title in ("Iran and Israel agree ceasefire", "Iran-Israel ceasefire collapses"):
            with self.subTest(title=title):
                self.assert_assets(title, expected, category="GEO")

    def test_war_hypotheses_denials_historical_sport_and_local_truces_are_excluded(self):
        for title in (
            "Russia may invade Ukraine",
            "US considers declaring war on Iran",
            "US threatens to declare war on Iran",
            "US may declare war on Iran",
            "Russia denies it has invaded Ukraine",
            "Russia hosts Olympic event since Ukraine invasion",
            "Fictional film shows Russia invades Ukraine",
            "Iran and Israel agree temporary humanitarian ceasefire for a train evacuation",
            "Iran and Israel agree local truce around a village",
        ):
            with self.subTest(title=title):
                self.assert_assets(title, (), category="GEO")


if __name__ == "__main__":
    unittest.main()

import unittest

from filter import assess_news, contains_any, is_relevant
from mapping import get_market_impact
from scoring import compute_score


REJECTED = (
    "UK needs to be ready for emergencies and hostile acts, warns Streeting",
    "Woman 'scared to turn heating on' due to oil cost",
    "Woman ‘scared to turn heating on’ due to oil cost",
    "Award-winning film celebrates life in China",
    "Man killed in shark attack off Australia's north-east coast",
    "I survived a missile strike in the Strait of Hormuz",
    "Childminder facing severe financial burden as heating oil costs rise",
    "Buy now or wait and hope? Families face gamble on heating oil",
    "Home heating oil jumps £100 in three weeks",
    "Heating oil customers to get compensation after price hikes",
    "Sailors stressed and exhausted after months trapped by Strait of Hormuz blockade",
    "Iran's sabre-rattling should not intimidate UK, Wes Streeting says",
    "Britain must prepare for war, minister warns",
    "UK urged to stockpile supplies for emergencies",
    "Iran warns of military escalation after missile attack",
    "Israel warns it will retaliate if UK imposes sanctions",
    "Fed expected to cut interest rates next month",
    "Interest rates hold expected but Bank of England facing tough choices",
    "Analysts discuss CPI inflation report",
    "Will the Fed cut interest rates?",
    "Why oil prices rise during a war",
    "How an oil tanker attack could affect markets",
    "OPEC considers oil production cuts",
    "OPEC plans to cut oil output next month",
    "Iran could close the Strait of Hormuz",
    "Iran threatens to close Strait of Hormuz",
    "Iran offers US deal to reopen Strait of Hormuz in seven days",
    "US and Iran begin talks on initial peace deal in Switzerland",
    "US wants Iran to pledge to stop shooting at ships in Strait of Hormuz",
    "Iran releases footage of missiles launched at Israel",
    "World chess chief faces endgame after EU announces Russia war sanctions",
    "India's first bank rate hike since 2023 signals growing inflation concerns",
    "China celebrates new film awards",
    "Gaza families tell their stories",
    "New political debate on defence spending",
    "Powell to speak at conference",
    "BBC reports on the Iran war",
    "Watch: why has the Federal Reserve raised interest rates?",
    "Analysis: why oil prices rise after a war",
    "Shell profits double as oil prices rise due to Iran war",
    "Fed may cut interest rates next month",
)

SELECTED = (
    "Federal Reserve cuts interest rates by 25 basis points",
    "Fed holds interest rates steady",
    "ECB raises interest rates to 4%",
    "Bank of England keeps rates unchanged",
    "Bank of Japan raises interest rates",
    "Fed announces first rate cut in four years",
    "ECB interest rates unchanged",
    "Fed cuts interest rates in May",
    "US CPI inflation rises in May",
    "Powell signals further rate cuts",
    "ECB rules out rate cuts this year",
    "US CPI inflation rises to 3.5%",
    "US inflation eases to 3.5% as gasoline prices fall",
    "PCE inflation slows more than expected",
    "Nonfarm payrolls rise by 200,000, beating forecasts",
    "US economy adds 200,000 jobs in March",
    "US unemployment rises to 4.3%",
    "US GDP contracts in first quarter",
    "UK retail sales fall sharply",
    "OPEC agrees to cut oil production",
    "OPEC+ announces increase in oil output",
    "Saudi Arabia shuts key oil pipeline after drone attack",
    "Russia halts gas exports to Europe",
    "Iran closes Strait of Hormuz to shipping",
    "Strait of Hormuz reopens to shipping",
    "Suez Canal blocked by container ship",
    "US imposes new sanctions on Russian oil exports",
    "EU lifts sanctions on Iran",
    "US announces 25% tariffs on imports from China",
    "Iran and Israel agree ceasefire to end war",
    "Israel and Lebanon agree to ceasefire contingent on Hezbollah stopping attacks",
    "Iran ceasefire collapses after new attacks",
    "Israel launches missile attack on Iran",
    "Russia invades Ukraine",
    "US declares war on Iran",
    "Houthis attack oil tanker in Red Sea",
    "Iranian missiles hit US military base",
    "Iran and US report new wave of air strikes in Gulf",
    "US strikes Iranian oil tanker",
    "Oil prices fall after OPEC agrees to increase production",
    "Brent surges 8% after oil supply disruption",
    "Gold jumps as Treasury yields fall",
)


class RelevanceTests(unittest.TestCase):
    def test_real_feed_previews_and_discussions_are_not_decisions(self):
        for title in (
            "Economic data spotlight: Fed rate hike bets survived Warsh, but can they survive US PCE inflation?",
            "The market is pricing in a 78% chance of a Bank of Canada rate hike",
            "Kremlin aide says discussions underway with US to lift sanctions on Russian investment fund",
            "Germany's trade struggles with China set to put Asia-Pacific deficit on course for record high",
            "investingLive Americas FX news wrap 28 Oct: Fed holds rates, yield curve steepens",
        ):
            with self.subTest(title=title):
                self.assertFalse(is_relevant(title), assess_news(title))

    def test_rate_decision_requires_a_policy_predicate_in_a_reference_economy(self):
        cases = (
            ("Australia’s inflation rate rises to 4.3%, fuelling fears of fifth interest rate hike this year",
             "The CPI release comes ahead of the Reserve Bank of Australia decision next week.", 8),
            ("European Central Bank keeps key interest rate on hold at 2.5%", "", 9),
            ("FOMC decision Oct 28: Rates left unchanged", "", 9),
            ("Bank of Canada rate decision: Hike to 2.50%", "", 9),
            ("The full statement from the Bank of Canada rate decision for October 2026. Hikes by 25 basis points", "", 9),
            ("Egypt’s central bank raises key interest rates by 100 basis points", "The Fed left US rates unchanged.", 0),
            ("Bank of Egypt raises key interest rates", "The Fed held rates unchanged.", 0),
        )
        for title, description, score in cases:
            with self.subTest(title=title):
                self.assertEqual(compute_score(title, description), score, assess_news(title, description))

    def test_sanctions_need_a_strategic_target_or_financial_channel(self):
        for title in (
            "US imposes sanctions on Rwanda's defense ministry over Congo conflict",
            "US sanctions Rwanda's defence ministry over DR Congo conflict",
        ):
            with self.subTest(title=title):
                self.assertFalse(is_relevant(title, "Congo accuses Rwanda of backing rebels and plundering minerals."))
        for title in (
            "US sanctions Russian oil companies",
            "EU lifts sanctions on Iran",
            "US imposes sanctions on Russian investment fund",
        ):
            with self.subTest(title=title):
                self.assertEqual(compute_score(title), 8, assess_news(title))

    def test_real_major_company_and_sector_headlines_are_not_missed(self):
        for title, score in (
            ("Caterpillar tops quarterly profit view, but unchanged growth target dents shares", 8),
            ("ServiceNow shares plunge 25% after earnings revive AI disruption fears", 7),
            ("Fortinet profits beat analyst estimates", 8),
            ("Alphabet falls 13%, putting it on course for its biggest ever post-earnings drop", 7),
            ("Software stocks slide as Fortinet, ServiceNow fail to meet lofty investor expectations", 6),
            ("Robust consumer spending, AI-related investment power US economy in third quarter", 7),
        ):
            with self.subTest(title=title):
                self.assertEqual(compute_score(title), score, assess_news(title))

    def test_actual_missed_earnings_and_acquisition_headlines(self):
        cases = (
            ("Microsoft profits soar days after announcing thousands of layoffs", 8),
            ("Doordash to buy Instacart in $17bn deal it says will expand customer options", 7),
        )
        for title, score in cases:
            with self.subTest(title=title):
                result = assess_news(title)
                self.assertEqual(result.score, score)
                self.assertEqual(result.category, "EQUITIES")

    def test_official_monetary_guidance_is_news_despite_conditional_wording(self):
        for title in (
            "Powell says Fed could hold rates higher for longer",
            "Fed chair Powell says interest rates may stay high",
            "Lagarde warns inflation could remain above target",
            "Bank of England governor says rate cuts are not guaranteed",
        ):
            with self.subTest(title=title):
                result = assess_news(title)
                self.assertEqual(result.score, 7, result)
                self.assertEqual(result.category, "MACRO")
        for title in (
            "Analysts expect Fed to cut interest rates next month",
            "Investors bet Fed could cut interest rates",
            "Will Powell signal a rate cut?",
            "Powell to speak at conference",
        ):
            with self.subTest(title=title):
                self.assertFalse(is_relevant(title), assess_news(title))

    def test_material_company_results_guidance_and_prices(self):
        for title, score in (
            ("Apple sales beat estimates", 8),
            ("Broadcom posts record quarterly revenue", 8),
            ("JPMorgan reports higher profits", 8),
            ("Nvidia cuts revenue forecast", 7),
            ("AMD raises outlook", 7),
            ("Amazon warns profits may fall", 7),
            ("Meta shares plunge 12% after a $500m fine", 7),
        ):
            with self.subTest(title=title):
                result = assess_news(title)
                self.assertEqual(result.score, score, result)
                self.assertEqual(result.category, "EQUITIES")
        for title in (
            "Microsoft profits could rise next year",
            "Analysts expect Microsoft profits to rise next year",
            "How Nvidia could boost its sales",
            "Analysts expect US to cut tariffs on Canada",
            "Apple buys a small startup for $20m",
            "DoorDash in preliminary talks to buy Instacart in $17bn deal",
            "DoorDash could buy Instacart in $17bn deal",
        ):
            with self.subTest(title=title):
                self.assertFalse(is_relevant(title), assess_news(title))

    def test_national_fiscal_events_use_summary_for_scope(self):
        title = "Healey unveils £100 for energy bills and bank tax in first Budget"
        self.assertFalse(is_relevant(title))
        result = assess_news(title, "The UK chancellor announced a new bank tax in his national Budget.")
        self.assertEqual(result.score, 7)
        self.assertEqual(result.category, "FISCAL")
        result = assess_news(
            "Budget 2026: Key points at a glance",
            "The UK chancellor unveiled a new bank tax and public spending measures.",
        )
        self.assertEqual(result.score, 7)
        self.assertEqual(result.category, "FISCAL")
        self.assertFalse(is_relevant(
            "Chancellor begins to deliver his first Budget",
            "The UK speech will discuss tax and public spending.",
        ))
        for title in (
            "Council unveils new tax in its Budget",
            "UK mayor raises local taxes in city Budget",
            "Ed Davey: It's a £76bn stealth tax rise",
            "Will I get the £100 energy payment?",
            "What does the UK Budget mean for your family?",
        ):
            with self.subTest(title=title):
                self.assertFalse(is_relevant(title, "The UK chancellor announced tax measures."))

    def test_family_context_does_not_block_actual_national_policy(self):
        result = assess_news("Chancellor cuts income tax to help families with heating bills")
        self.assertEqual(result.score, 7, result)
        self.assertEqual(result.category, "FISCAL")
        result = assess_news(
            "Chancellor to cut tariffs on some food and freeze fuel duty to give families 'breathing space'"
        )
        self.assertEqual(result.score, 8, result)
        self.assertEqual(result.category, "TRADE")

    def test_national_growth_data_without_gdp_abbreviation(self):
        result = assess_news("US economy grew 3% last quarter")
        self.assertEqual(result.score, 8, result)
        self.assertEqual(result.category, "MACRO")

    def test_market_movement_is_linked_to_the_asset(self):
        for title in (
            "European stocks edge lower after weak earnings",
            "UK gilt yields jump after national Budget",
            "Oil jumps as supply concerns intensify",
            "Markets: Gold futures surge after data release",
        ):
            with self.subTest(title=title):
                result = assess_news(title)
                self.assertEqual(result.score, 6, result)
                self.assertEqual(result.category, "MARKET")
        for title in (
            "Oil spill hits UAE beaches",
            "Gold mining company shares jump",
            "Gas bills rise for families",
        ):
            with self.subTest(title=title):
                self.assertFalse(is_relevant(title), assess_news(title))

    def test_historical_invasions_do_not_turn_sport_or_culture_into_alerts(self):
        for title in (
            "Russia to host first Olympic federation world event since Ukraine invasion",
            "Russia hosts first world sporting event during Ukraine invasion",
            "Russia's first Olympic event since it invaded Ukraine",
            "Russia to host world event since the invasion of Ukraine",
            "Museum opens exhibition about Russia's invasion of Ukraine",
            "Russia opens Ukraine invasion exhibition",
            "Russia launches exhibition about Ukraine invasion",
        ):
            with self.subTest(title=title):
                self.assertEqual(compute_score(title, "Russian missiles hit Ukraine and oil prices surge."), 0)

    def test_real_events_are_preserved_with_historical_or_sporting_background(self):
        for title, score in (
            ("Russia invades Ukraine for the first time since 2022", 9),
            ("Russia begins a new invasion of Ukraine", 9),
            ("Russia launches a new invasion of Ukraine", 9),
            ("Russian invasion of Ukraine begins", 9),
            ("Iran fires ballistic missiles at US military base", 9),
            ("Iran launches missile attack on US military base during Olympic Games", 9),
            ("Fed cuts interest rates for first time since 2020", 9),
            ("White House cuts tariffs on Canadian goods for first time since 2020", 8),
            ("Gold hits highest level since Ukraine invasion", 6),
            ("Since Russia invaded Ukraine, US imposes new sanctions on Russian banks", 8),
        ):
            with self.subTest(title=title):
                self.assertEqual(compute_score(title), score, assess_news(title))

    def test_a_possible_new_invasion_is_not_confirmed(self):
        for title in ("Russia may begin an invasion of Ukraine", "Russia might start an invasion of Ukraine"):
            with self.subTest(title=title):
                self.assertFalse(is_relevant(title), assess_news(title))

    def test_trade_actors_and_confirmed_policy_variants(self):
        for title in (
            "White House lifts tariffs on some Canadian goods as midterm elections loom",
            "Canada lifts tariffs on US imports",
            "Ottawa scraps import duties on US goods",
            "Trump slashes tariffs on Chinese imports after trade talks fail",
            "European Commission doubles tariffs on Chinese electric vehicles",
            "US imposes tariffs on foreign film imports",
            "China introduces export controls on rare earths",
            "EU import duties on Chinese goods come into force",
        ):
            with self.subTest(title=title):
                self.assertEqual(compute_score(title), 8, assess_news(title))

    def test_confirmed_events_survive_speculation_in_the_background_clause(self):
        cases = (
            ("US imposes tariffs on China after negotiations fail", 8),
            ("US lifts tariffs while trade talks continue", 8),
            ("After trade talks fail, US imposes tariffs on China", 8),
            ("Fed cuts interest rates but warns it may hold next month", 9),
            ("Oil prices plunge as traders weigh OPEC production cuts", 6),
            ("US stocks drop after trade talks fail", 6),
            ("Dow sinks as investors weigh possible Fed rate cuts", 6),
            ("Dollar strengthens as traders weigh interest rate cuts", 6),
        )
        for title, score in cases:
            with self.subTest(title=title):
                self.assertEqual(compute_score(title), score, assess_news(title))

    def test_background_cannot_supply_the_main_announcement(self):
        for title in (
            "US discusses tariffs after China lifts sanctions",
            "White House considers lifting tariffs on Canadian goods",
            "White House raises concerns over tariffs on Canadian goods",
            "Trump threatens to impose tariffs if trade talks fail",
            "US imposes tariffs if negotiations fail",
            "Minister speaks after Fed cuts interest rates",
            "How US stocks could rise after a trade deal",
            "Oil prices could plunge as trade talks fail",
        ):
            with self.subTest(title=title):
                self.assertFalse(is_relevant(title), assess_news(title))

    def test_other_major_central_banks_are_recognized(self):
        for title in (
            "Bank of Canada cuts interest rates by 25 basis points",
            "Reserve Bank of Australia holds rates steady",
            "Swiss National Bank slashes interest rates to 0%",
            "RBI raises interest rates",
        ):
            with self.subTest(title=title):
                self.assertEqual(compute_score(title), 9, assess_news(title))

    def test_exceptional_confirmed_megacap_penalties(self):
        for title in (
            "Meta fined $25bn for 'lies' over user data privacy",
            "Apple fined €5.5 billion after regulator talks fail",
            "Google ordered to pay $10 billion in antitrust case",
            "Microsoft hit with $8bn fine",
            "Meta handed a record $25bn privacy fine",
            "Apple fined 6 billion euros over privacy",
            "Meta wins appeal as $25bn fine overturned",
        ):
            with self.subTest(title=title):
                self.assertEqual(compute_score(title), 7, assess_news(title))
        self.assertEqual(compute_score("Meta $25bn fine overturned by court"), 7)

    def test_routine_or_hypothetical_company_stories_stay_blocked(self):
        for title in (
            "Meta faces $25bn fine over privacy",
            "Meta may be fined $25bn over privacy",
            "Meta could be fined $25bn over privacy",
            "Meta fined $500m over privacy",
            "Meta fined $500m after a $25bn investment",
            "Meta fined $500m and announces $25bn investment",
            "Meta fined $3bn over privacy",
            "Local retailer fined $25bn",
            "Meta announces $25bn investment in data centres",
            "Barclays cutting 5,000 jobs as it increases reliance on AI",
            "White House says Melania Trump brokered truce for Ukraine city",
            "Websites taken down worldwide as critical cyber-security update issued",
        ):
            with self.subTest(title=title):
                self.assertFalse(is_relevant(title), assess_news(title))

    def test_new_alerts_have_assets_without_an_automatic_direction(self):
        for title, category, required in (
            ("White House lifts tariffs on some Canadian goods", "TRADE", "NAS100"),
            ("US imposes new sanctions on Russian oil exports", "TRADE", "USOIL"),
            ("Meta fined $25bn for privacy violations", "EQUITIES", "NAS100"),
        ):
            with self.subTest(title=title):
                impacts, assets, bias, actual = get_market_impact(title, title=title)
                self.assertEqual(actual, category)
                self.assertIn(required, assets)
                self.assertEqual(bias, "À confirmer")
                self.assertFalse(any("haussier" in impact for impact in impacts))

    def test_context_does_not_reclassify_a_macro_headline_as_equities(self):
        title = "Fed cuts interest rates"
        context = title + " Meta fined $25bn in an unrelated case."
        _, _, _, category = get_market_impact(context, title=title)
        self.assertEqual(category, "MACRO")

    def test_local_inflation_is_not_a_macro_alert(self):
        for title in (
            "Island inflation rate rises to 3%, figures show",
            "Jersey inflation rises to 3%",
            "Isle of Man inflation falls to 2%",
            "Regional inflation rises sharply",
        ):
            with self.subTest(title=title):
                self.assertFalse(is_relevant(title, "The local figure is compared with UK inflation."))

    def test_macro_geography_can_come_from_summary(self):
        title = "Inflation and government borrowing highest for a year ahead of next week's Budget"
        self.assertFalse(is_relevant(title))
        self.assertTrue(is_relevant(title, "New UK figures show prices and public borrowing rose."))

    def test_local_pollution_is_not_a_strategic_attack(self):
        titles = (
            "Oil spill washes up on UAE beaches after tanker strike",
            "Oil spill hits UAE beaches after tanker collision",
            "Oil slick hits UAE beaches after oil tanker collision",
            "Oil spill washes up on UAE beaches after tanker collision",
            "Oil spill after tanker collision closes beaches near Strait of Hormuz",
            "Oil spill closes beach near major oil terminal",
            "Oil spill hits Iran coast after tanker collision",
            "Storm hits oil tanker off Iran coast",
            "Wave strikes tanker off Iran coast",
        )
        summary = "Iran and the US exchanged missile attacks in the Gulf. Oil prices surged."
        for title in titles:
            with self.subTest(title=title):
                self.assertFalse(is_relevant(title, summary))
                self.assertEqual(compute_score(title, summary), 0)

    def test_incidents_with_explicit_supply_or_price_effect_are_preserved(self):
        titles = (
            "Tanker collision closes Strait of Hormuz to shipping",
            "Oil spill halts oil exports from UAE",
            "Oil exports halted after tanker collision",
            "Oil spill forces closure of major oil terminal",
            "Oil spill shuts key pipeline",
            "Pipeline shut after oil spill",
            "Oil spill disrupts oil supply",
            "Oil spill halts oil exports from UAE, prices rise",
            "Oil prices surge 8% after tanker collision",
            "Brent jumps after oil spill halts exports",
        )
        for title in titles:
            with self.subTest(title=title):
                self.assertTrue(is_relevant(title), assess_news(title))

    def test_rejects_noise_and_hypothetical_announcements(self):
        for title in REJECTED:
            with self.subTest(title=title):
                assessment = assess_news(title)
                self.assertFalse(assessment.relevant, assessment)
                self.assertEqual(compute_score(title), 0)

    def test_preserves_concrete_market_events(self):
        for title in SELECTED:
            with self.subTest(title=title):
                assessment = assess_news(title)
                self.assertTrue(assessment.relevant, assessment)
                self.assertGreaterEqual(compute_score(title), 5)

    def test_user_examples_stay_blocked_with_market_context_in_summary(self):
        summary = (
            "Iran launches missile attacks amid military escalation. Oil prices "
            "surge as shipping is disrupted in the Strait of Hormuz."
        )
        for title in REJECTED[:3]:
            with self.subTest(title=title):
                self.assertFalse(is_relevant(title, summary))
                self.assertEqual(compute_score(title, summary), 0)

    def test_summary_cannot_create_an_event_missing_from_title(self):
        self.assertFalse(is_relevant(
            "Minister speaks about international affairs",
            "The US imposes tariffs on China and Iran closes the Strait of Hormuz.",
        ))

    def test_summary_can_identify_bank_for_explicit_rate_decision(self):
        self.assertTrue(is_relevant(
            "Interest rates held at 4%", "The Bank of England keeps policy unchanged."
        ))

    def test_whole_words(self):
        for text, fragment in (("award", "war"), ("Gaza", "gas"),
                               ("celebrates", "rates"), ("federation", "fed")):
            with self.subTest(text=text):
                self.assertFalse(contains_any(text, (fragment,)))
        self.assertTrue(contains_any("FED cuts rates", ("fed",)))

    def test_html_and_case_normalization(self):
        self.assertTrue(is_relevant("<b>FED</b> CUTS INTEREST RATES"))
        self.assertTrue(is_relevant("S&amp;P 500 plunges 5%"))

    def test_empty_titles(self):
        for title in (None, "", "   "):
            with self.subTest(title=title):
                self.assertEqual(compute_score(title), 0)

    def test_mapping_does_not_match_fragments(self):
        for title in ("Gaza", "Award-winning film celebrates life"):
            with self.subTest(title=title):
                impacts, assets, bias, category = get_market_impact(title)
                self.assertEqual(assets, [])
                self.assertEqual(category, "FONDAMENTAL")


if __name__ == "__main__":
    unittest.main()

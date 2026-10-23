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

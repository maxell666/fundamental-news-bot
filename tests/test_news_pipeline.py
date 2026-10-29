import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from news_pipeline import evaluate_news, rank_eligible, story_key, write_audit


NOW = datetime(2026, 10, 29, 15, 0, tzinfo=timezone.utc)


def relevant(*args):
    return SimpleNamespace(score=8, reason="Décision commerciale", category="TRADE", relevant=True)


def article(title="US imposes tariffs", url="https://example.com/news", published="2026-10-29T14:00:00Z"):
    return {"title": title, "url": url, "source": "Source test", "published_at": published, "desc": ""}


class NewsPipelineTests(unittest.TestCase):
    def test_monetary_leadership_change_is_not_hidden_by_the_rate_duplicate(self):
        rows = evaluate_news([
            article("ECB keeps rates steady as Lagarde announces exit amid oil worries", "https://example.com/a"),
            article("European Central Bank keeps key interest rate on hold at 2.5%", "https://example.com/b"),
            article("Fed holds rates steady as Powell could step down next year", "https://example.com/c"),
            article("Federal Reserve holds interest rates steady", "https://example.com/d"),
        ], {}, now=NOW)
        chosen = rank_eligible(rows, now=NOW)
        self.assertEqual(len(chosen), 3)
        self.assertIn("direction", rows[0]["event_note"])
        self.assertIsNone(rows[0]["event_key"])
        self.assertEqual(sum(row["event_base"] == "rates:fed:hold:2026-10-29" for row in chosen), 1)

    def test_same_rate_decision_from_different_sources_is_sent_once(self):
        rows = evaluate_news([
            article("ECB keeps rates steady", "https://first.example/ecb", "2026-10-29T14:40:00Z"),
            article("European Central Bank keeps key interest rate on hold at 2.50%", "https://second.example/ecb", "2026-10-29T14:48:00Z"),
        ], {}, now=NOW)
        selected = rank_eligible(rows, now=NOW)
        self.assertEqual(len(selected), 1)
        self.assertIn("2.50%", selected[0]["title"])
        self.assertEqual(selected[0]["event_value"], {"rate": "2.5"})
        self.assertEqual(rows[0]["decision"], "duplicate_event")
        self.assertEqual(rows[0]["event_key"], rows[1]["event_key"])

    def test_an_unspecified_newer_copy_keeps_the_known_rate_for_persistence(self):
        rows = evaluate_news([
            article("ECB keeps key rate at 2.5%", "https://first.example/ecb", "2026-10-29T14:40:00Z"),
            article("ECB keeps rates steady", "https://second.example/ecb", "2026-10-29T14:48:00Z"),
        ], {}, now=NOW)
        chosen = rank_eligible(rows, now=NOW)
        self.assertEqual(len(chosen), 1)
        self.assertEqual(chosen[0]["title"], "ECB keeps rates steady")
        self.assertEqual(chosen[0]["event_value"], {"rate": "2.5"})

    def test_rate_level_and_change_in_basis_points_are_complementary(self):
        rows = evaluate_news([
            article("Bank of Canada rate decision: Hike to 2.50%", "https://first.example/boc"),
            article("The full statement from the Bank of Canada rate decision. Hikes by 25 basis points", "https://second.example/boc"),
        ], {}, now=NOW)
        chosen = rank_eligible(rows, now=NOW)
        self.assertEqual(len(chosen), 1)
        self.assertEqual(chosen[0]["event_value"], {"rate": "2.5", "change_bps": "25"})

    def test_opposite_actions_and_new_explicit_values_remain_distinct(self):
        rows = evaluate_news([
            article("ECB keeps rates at 2.5%", "https://example.com/a"),
            article("ECB keeps rates at 2.75%", "https://example.com/b"),
            article("ECB keeps rates steady", "https://example.com/c"),
            article("ECB raises interest rates to 2.75%", "https://example.com/d"),
            article("ECB cuts interest rates to 2.5%", "https://example.com/e"),
        ], {}, now=NOW)
        chosen = rank_eligible(rows, now=NOW)
        self.assertEqual(len(chosen), 4)
        self.assertEqual(len({row["event_key"] for row in chosen}), 4)
        self.assertEqual(rows[2]["decision"], "duplicate_event")

    def test_negative_policy_rates_are_distinct_from_positive_rates(self):
        rows = evaluate_news([
            article("SNB holds interest rates at -0.25%", "https://example.com/a"),
            article("Swiss National Bank holds rates at 0.25%", "https://example.com/b"),
        ], {}, now=NOW)
        chosen = rank_eligible(rows, now=NOW)
        self.assertEqual(len(chosen), 2)
        self.assertEqual({row["event_value"]["rate"] for row in chosen}, {"-0.25", "0.25"})

    def test_gdp_growth_value_and_quarter_control_event_duplicates(self):
        rows = evaluate_news([
            article("Third-quarter U.S. GDP increases a better-than-expected 3.4%", "https://example.com/a"),
            article("US GDP Advance for the 3rd quarter 3.4% vs 3.2% estimate", "https://example.com/b"),
            article("Robust consumer spending, AI-related investment power US economy in third quarter", "https://example.com/c"),
            article("US GDP rises 3.5% in third quarter", "https://example.com/d"),
            article("US GDP rises 3.4% in second quarter", "https://example.com/e"),
        ], {}, now=NOW)
        chosen = rank_eligible(rows, now=NOW)
        self.assertEqual(len(chosen), 3)
        self.assertEqual({row["event_base"] for row in chosen}, {"gdp:us:2026:q3", "gdp:us:2026:q2"})
        self.assertEqual(rows[2]["decision"], "duplicate_event")

    def test_major_acquisition_duplicates_require_same_parties_and_amount(self):
        rows = evaluate_news([
            article("DoorDash to acquire Instacart for $17 billion", "https://example.com/a"),
            article("DoorDash to buy Instacart in $17bn deal", "https://example.com/b"),
            article("DoorDash to buy Instacart for $18bn", "https://example.com/c"),
            article("Microsoft to buy Instacart for $17bn", "https://example.com/d"),
        ], {}, now=NOW)
        chosen = rank_eligible(rows, now=NOW)
        self.assertEqual(len(chosen), 3)
        self.assertEqual(rows[1]["decision"], "duplicate_event")
        self.assertEqual(rows[0]["event_value"], {"amount_billion": "17", "currency": "USD"})

    def test_event_history_is_read_only_expires_and_preserves_new_values(self):
        first = evaluate_news([article("ECB keeps rates at 2.5%")], {}, now=NOW)
        row = rank_eligible(first, now=NOW)[0]
        history = {row["event_key"]: {"sent_at": "2026-10-29T14:30:00Z", "value": row["event_value"], "base": row["event_base"]}}
        snapshot = json.loads(json.dumps(history))
        current = evaluate_news([
            article("European Central Bank keeps rates steady", "https://example.com/a"),
            article("ECB keeps rates at 2.75%", "https://example.com/b"),
        ], {}, now=NOW)
        chosen = rank_eligible(current, seen_events=history, now=NOW)
        self.assertEqual(len(chosen), 1)
        self.assertIn("2.75%", chosen[0]["title"])
        self.assertEqual(history, snapshot)
        repeated = evaluate_news([article("ECB keeps rates at 2.5%")], {}, now=NOW)
        self.assertEqual(rank_eligible(repeated, history, now=NOW), [])
        expired = {key: dict(value, sent_at="2026-10-28T14:30:00Z") for key, value in history.items()}
        fresh_rows = evaluate_news([article("ECB keeps rates at 2.5%")], {}, now=NOW)
        self.assertEqual(len(rank_eligible(fresh_rows, expired, now=NOW)), 1)

    def test_generic_summaries_cannot_suppress_new_explicit_information(self):
        rows = evaluate_news([article("ECB keeps rates steady")], {}, now=NOW)
        row = rank_eligible(rows, now=NOW)[0]
        history = {row["event_key"]: {"sent_at": "2026-10-29T14:00:00Z", "value": {}, "base": row["event_base"]}}
        detailed = evaluate_news([article("ECB keeps rates at 2.5%")], {}, now=NOW)
        self.assertEqual(len(rank_eligible(detailed, history, now=NOW)), 1)

    def test_unrelated_market_movements_have_no_generic_cooldown(self):
        rows = evaluate_news([
            article("Gold jumps 1%", "https://example.com/a"),
            article("Gold falls 2%", "https://example.com/b"),
            article("Oil rises 3%", "https://example.com/c"),
        ], {}, now=NOW)
        chosen = rank_eligible(rows, now=NOW)
        self.assertEqual(len(chosen), 3)
        self.assertTrue(all(row["event_key"] is None for row in chosen))

    def test_fresh_seen_tracking_duplicates_and_old_articles_are_distinguished(self):
        articles = [
            article(url="https://example.com/seen?utm_source=rss"),
            article("Fed cuts rates", "https://example.com/fed"),
            article("Fed cuts rates - Reuters", "https://other.example/fed"),
            article("Old announcement", "https://example.com/old", "2026-10-27T14:00:00Z"),
            article("No publication date", "https://example.com/undated", None),
            article("Future date", "https://example.com/future", "2026-10-30T14:00:00Z"),
        ]
        state = {"seen": ["https://example.com/seen?at_campaign=rss"], "seen_titles": {}}
        rows = evaluate_news(articles, state, now=NOW, assessor=relevant)
        self.assertEqual([row["decision"] for row in rows], ["seen", "eligible", "duplicate", "stale", "undated", "future"])
        self.assertEqual(len(rank_eligible(rows)), 1)
        self.assertEqual(state["seen_titles"], {})

    def test_an_old_or_undated_copy_cannot_hide_a_fresh_copy(self):
        rows = evaluate_news([
            article(published=None), article(url="https://other.example/same"),
        ], {}, now=NOW, assessor=relevant)
        self.assertEqual([r["decision"] for r in rows], ["undated", "eligible"])

    def test_seen_title_prevents_reposting_from_another_provider(self):
        rows = evaluate_news([article("Fed cuts rates", "https://other.example/fed")],
                             {"seen_titles": {story_key("Fed cuts rates - Reuters"): "2026-10-29T14:00:00Z"}}, now=NOW, assessor=relevant)
        self.assertEqual(rows[0]["decision"], "seen")

    def test_recurring_headline_is_not_blocked_forever(self):
        rows = evaluate_news([article("ECB holds rates")],
                             {"seen_titles": {story_key("ECB holds rates"): "2026-09-01T12:00:00Z"}},
                             now=NOW, assessor=relevant)
        self.assertEqual(rows[0]["decision"], "eligible")
        self.assertNotEqual(story_key("US stocks +0.5%"), story_key("US stocks -0.5%"))

    def test_richer_summary_can_recover_a_rejected_copy(self):
        def classify(title, desc):
            return relevant() if desc else SimpleNamespace(score=0, reason="Acteur manquant", category="FISCAL", relevant=False)
        first, second = article(), article(url="https://other.example/story")
        second["desc"] = "The US Treasury announced the policy."
        rows = evaluate_news([first, second], {}, now=NOW, assessor=classify)
        self.assertEqual([r["decision"] for r in rows], ["rejected", "eligible"])

    def test_threshold_and_rejection_reasons_remain_auditable(self):
        def classify(title, desc):
            score = 0 if title == "Local anecdote" else 4
            return SimpleNamespace(score=score, reason="Pas de canal de marché" if score == 0 else "Priorité modérée",
                                   category="FONDAMENTAL", relevant=score > 0)
        rows = evaluate_news([article("Local anecdote"), article("Minor event", "https://example.com/minor")],
                             {}, now=NOW, assessor=classify)
        self.assertEqual([r["decision"] for r in rows], ["rejected", "below_threshold"])
        self.assertEqual(rows[0]["reason"], "Pas de canal de marché")

    def test_audit_contains_each_decision_without_internal_state(self):
        rows = evaluate_news([article()], {}, now=NOW, assessor=relevant)
        rows[0]["decision"] = "dry_run_selected"
        with tempfile.TemporaryDirectory() as directory:
            report = write_audit(rows, [{"source": "Source test", "status": "ok"}], dry_run=True, directory=directory)
            saved = json.loads((Path(directory) / "news_audit.json").read_text())
            self.assertEqual(saved, report)
            self.assertEqual(saved["summary"]["decisions"], {"dry_run_selected": 1})
            self.assertNotIn("article", saved["items"][0])
            self.assertNotIn("story_key", saved["items"][0])
            self.assertTrue((Path(directory) / "news_audit.csv").exists())


if __name__ == "__main__":
    unittest.main()

import contextlib
import io
import os
import unittest
from unittest.mock import patch

with patch.dict(os.environ, {"BOT_TOKEN": "test-token", "CHAT_ID": "test-chat"}):
    import bot


def article(title, url, desc=""):
    return {"title": title, "url": url, "desc": desc, "source": "Test RSS"}


class SelectionPipelineTests(unittest.TestCase):
    def run_bot(self, articles, seen=(), limit=60, threshold=5):
        state = {"seen": list(seen), "translations": {}}
        with contextlib.ExitStack() as stack:
            # Une régression ne doit jamais déclencher un appel réel.
            stack.enter_context(patch("requests.sessions.Session.request",
                                      side_effect=AssertionError("Accès réseau interdit dans les tests")))
            stack.enter_context(patch.object(bot, "debug_deepl_usage"))
            stack.enter_context(patch.object(bot, "load_state", return_value=state))
            saved = stack.enter_context(patch.object(bot, "save_state"))
            stack.enter_context(patch.object(bot, "fetch_reuters", return_value=articles))
            stack.enter_context(patch.object(bot, "USE_NEWSAPI", False))
            stack.enter_context(patch.object(bot, "MAX_ARTICLES_PER_RUN", limit))
            stack.enter_context(patch.object(bot, "MIN_SCORE_SEND", threshold))
            stack.enter_context(patch.object(bot, "has_deepl_key", return_value=True))
            translated = stack.enter_context(patch.object(bot, "translate_text", side_effect=lambda t: "FR " + t))
            sent = stack.enter_context(patch.object(bot, "send_telegram"))
            output = stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            bot.main()
            saved.assert_called_once_with(state)
            return state, translated, sent, output.getvalue()

    def test_user_examples_never_translated_or_sent(self):
        state, translated, sent, output = self.run_bot([
            article("UK needs to be ready for emergencies and hostile acts, warns Streeting", "https://test/uk",
                    "Iran missile attacks and military escalation threaten oil supplies."),
            article("Woman 'scared to turn heating on' due to oil cost", "https://test/woman",
                    "Oil prices surge after Iran launches attacks in Strait of Hormuz."),
        ])
        translated.assert_not_called()
        sent.assert_not_called()
        self.assertEqual(state["seen"], [])
        self.assertIn("Avertissement général", output)
        self.assertIn("Témoignage", output)

    def test_seen_articles_do_not_consume_limit(self):
        state, translated, sent, _ = self.run_bot([
            article("Fed cuts interest rates", "https://test/seen"),
            article("Oil prices plunge 5%", "https://test/new"),
        ], seen=["https://test/seen"], limit=1)
        sent.assert_called_once()
        translated.assert_called_once_with("Oil prices plunge 5%")
        self.assertEqual(state["seen"], ["https://test/seen", "https://test/new"])

    def test_local_oil_spill_is_not_translated_or_sent(self):
        state, translated, sent, output = self.run_bot([
            article("Oil spill washes up on UAE beaches after tanker strike", "https://test/bbc-spill",
                    "A tanker was struck near the Gulf amid Iran and US military tensions."),
            article("Oil spill hits UAE beaches after tanker collision", "https://test/spill",
                    "Iran and US missile attacks have disrupted shipping in the Gulf."),
        ])
        translated.assert_not_called()
        sent.assert_not_called()
        self.assertEqual(state["seen"], [])
        self.assertIn("Pollution ou accident local", output)

    def test_filter_version_is_visible_in_logs(self):
        _, _, _, output = self.run_bot([])
        self.assertIn("pertinence-v2", output)

    def test_deduplication_and_priority(self):
        news = article("Fed cuts interest rates", "https://test/fed")
        state, translated, sent, _ = self.run_bot([
            article("Oil prices plunge 5%", "https://test/oil"), news, news,
        ], limit=1)
        sent.assert_called_once()
        translated.assert_called_once_with(news["title"])
        self.assertEqual(state["seen"], [news["url"]])

    def test_configured_threshold_still_applies(self):
        _, translated, sent, _ = self.run_bot([
            article("Oil prices plunge 5%", "https://test/oil"),
            article("US CPI inflation rises to 3.5%", "https://test/cpi"),
        ], threshold=8)
        sent.assert_called_once()
        translated.assert_called_once_with("US CPI inflation rises to 3.5%")


if __name__ == "__main__":
    unittest.main()

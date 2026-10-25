import contextlib
import io
import os
import unittest
from unittest.mock import Mock, patch

with patch.dict(os.environ, {"BOT_TOKEN": "12345:test_token_for_unit_tests_only", "CHAT_ID": "test-chat"}):
    import bot


def article(title, url, desc=""):
    return {"title": title, "url": url, "desc": desc, "source": "Test RSS"}


class TelegramTokenTests(unittest.TestCase):
    def test_invalid_secret_format_stops_before_any_request(self):
        for token in ("", "bot12345:fake_token", "12345:token with spaces", "ghp_unit_test_value"):
            with self.subTest(case="vide" if not token else "format incorrect"), \
                    patch.object(bot, "BOT_TOKEN", token), patch.object(bot.requests, "get") as get, \
                    self.assertRaises(RuntimeError) as error:
                bot.verify_telegram_token()
            get.assert_not_called()
            if token:
                self.assertNotIn(token, str(error.exception))

    def test_valid_token_identifies_bot_without_sending_message(self):
        identity = {"id": 12345, "is_bot": True, "username": "test_news_bot"}
        response = Mock(status_code=200)
        response.json.return_value = {"ok": True, "result": identity}
        with patch.object(bot.requests, "get", return_value=response) as get, \
                patch.object(bot.requests, "post") as post, \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(bot.verify_telegram_token(), identity)
        self.assertTrue(get.call_args.args[0].endswith("/getMe"))
        post.assert_not_called()
        self.assertIn("Telegram authentifié : @test_news_bot", output.getvalue())
        self.assertNotIn(bot.BOT_TOKEN, output.getvalue())

    def test_refused_token_does_not_expose_response_or_token(self):
        response = Mock(status_code=401)
        response.text = "Sensitive response containing " + bot.BOT_TOKEN
        with patch.object(bot.requests, "get", return_value=response), \
                contextlib.redirect_stdout(io.StringIO()) as output, \
                self.assertRaisesRegex(RuntimeError, "HTTP 401") as error:
            bot.verify_telegram_token()
        self.assertNotIn(bot.BOT_TOKEN, str(error.exception))
        self.assertNotIn(bot.BOT_TOKEN, output.getvalue())
        self.assertIn("format Telegram valide", output.getvalue())
        response.json.assert_not_called()

    def test_network_error_does_not_expose_token_in_url(self):
        error_url = f"https://api.telegram.org/bot{bot.BOT_TOKEN}/getMe"
        with patch.object(bot.requests, "get", side_effect=bot.requests.ConnectionError(error_url)), \
                self.assertRaisesRegex(RuntimeError, "Connexion Telegram impossible") as error:
            bot.verify_telegram_token()
        self.assertNotIn(bot.BOT_TOKEN, str(error.exception))
        self.assertTrue(error.exception.__suppress_context__)

    def test_invalid_identity_or_response_is_not_accepted(self):
        for payload in ({"ok": False}, {"ok": True, "result": {"is_bot": False}}, [],
                        {"ok": True, "result": {"is_bot": True, "username": "unexpected:secret"}}):
            response = Mock(status_code=200)
            response.json.return_value = payload
            with self.subTest(payload=payload), patch.object(bot.requests, "get", return_value=response), \
                    self.assertRaises(RuntimeError):
                bot.verify_telegram_token()
        response.json.side_effect = ValueError(bot.BOT_TOKEN)
        with patch.object(bot.requests, "get", return_value=response), \
                self.assertRaisesRegex(RuntimeError, "Réponse Telegram illisible") as error:
            bot.verify_telegram_token()
        self.assertNotIn(bot.BOT_TOKEN, str(error.exception))

    def test_invalid_token_stops_before_news_fetch_or_send(self):
        with patch.object(bot, "verify_telegram_token", side_effect=RuntimeError("Token refusé")), \
                patch.object(bot, "fetch_reuters") as fetch, \
                patch.object(bot, "send_telegram") as send, \
                contextlib.redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError):
            bot.main()
        fetch.assert_not_called()
        send.assert_not_called()


class TelegramSendTests(unittest.TestCase):
    def test_confirmed_send_does_not_log_private_response(self):
        response = Mock(status_code=200)
        response.text = "PRIVATE RESPONSE " + bot.BOT_TOKEN + " " + bot.CHAT_ID
        response.json.return_value = {"ok": True, "result": {"message_id": 42, "chat": {"id": bot.CHAT_ID}}}
        with patch.object(bot.requests, "post", return_value=response) as post, \
                contextlib.redirect_stdout(io.StringIO()) as output:
            bot.send_telegram("Test unitaire sans envoi réel")
        post.assert_called_once()
        self.assertEqual(post.call_args.kwargs["data"]["chat_id"], bot.CHAT_ID)
        self.assertIn("envoi confirmé", output.getvalue())
        self.assertNotIn(bot.BOT_TOKEN, output.getvalue())
        self.assertNotIn(bot.CHAT_ID, output.getvalue())
        self.assertNotIn("PRIVATE RESPONSE", output.getvalue())

    def test_refused_send_does_not_expose_response_or_authentication_url(self):
        response = Mock(status_code=403)
        response.text = bot.BOT_TOKEN + " " + bot.CHAT_ID
        with patch.object(bot.requests, "post", return_value=response), \
                contextlib.redirect_stdout(io.StringIO()) as output, \
                self.assertRaisesRegex(RuntimeError, "HTTP 403") as error:
            bot.send_telegram("Test")
        response.json.assert_not_called()
        for private in (bot.BOT_TOKEN, bot.CHAT_ID):
            self.assertNotIn(private, output.getvalue() + str(error.exception))

    def test_interrupted_send_has_no_automatic_retry_or_secret_in_error(self):
        url = f"https://api.telegram.org/bot{bot.BOT_TOKEN}/sendMessage"
        with patch.object(bot.requests, "post", side_effect=bot.requests.ConnectionError(url)) as post, \
                self.assertRaisesRegex(RuntimeError, "connexion interrompue") as error:
            bot.send_telegram("Test")
        post.assert_called_once()
        self.assertNotIn(bot.BOT_TOKEN, str(error.exception))
        self.assertTrue(error.exception.__suppress_context__)

    def test_http_success_alone_does_not_confirm_a_send(self):
        for payload in ({"ok": False}, [], {"ok": True}, {"ok": True, "result": {}}):
            response = Mock(status_code=200)
            response.json.return_value = payload
            with self.subTest(payload=payload), patch.object(bot.requests, "post", return_value=response), \
                    contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(RuntimeError, "non confirmé"):
                bot.send_telegram("Test")
        response.json.side_effect = ValueError(bot.BOT_TOKEN)
        with patch.object(bot.requests, "post", return_value=response), \
                contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(RuntimeError, "illisible") as error:
            bot.send_telegram("Test")
        self.assertNotIn(bot.BOT_TOKEN, str(error.exception))
        self.assertTrue(error.exception.__suppress_context__)


class SelectionPipelineTests(unittest.TestCase):
    def run_bot(self, articles, seen=(), limit=60, threshold=5):
        state = {"seen": list(seen), "translations": {}}
        with contextlib.ExitStack() as stack:
            # Une régression ne doit jamais déclencher un appel réel.
            stack.enter_context(patch("requests.sessions.Session.request",
                                      side_effect=AssertionError("Accès réseau interdit dans les tests")))
            stack.enter_context(patch.object(bot, "verify_telegram_token"))
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
        self.assertIn("pertinence-v2.3", output)

    def test_olympic_event_with_historical_war_context_is_not_sent(self):
        state, translated, sent, _ = self.run_bot([
            article(
                "Russia to host first Olympic federation world event since Ukraine invasion",
                "https://test/olympic-event",
                "The first sporting event since Russia launched its invasion of Ukraine.",
            ),
        ])
        translated.assert_not_called()
        sent.assert_not_called()
        self.assertEqual(state["seen"], [])

    def test_recovered_real_headlines_are_sent_once_with_the_original_noise_blocked(self):
        tariff = article(
            "White House lifts tariffs on some Canadian goods as midterm elections loom",
            "https://test/white-house-tariffs",
        )
        penalty = article("Meta fined $25bn for 'lies' over user data privacy", "https://test/meta-fine")
        news = [tariff, penalty, tariff,
                article("Oil spill washes up on UAE beaches after tanker strike", "https://test/spill"),
                article("Woman 'scared to turn heating on' due to oil cost", "https://test/woman"),
                article("UK needs to be ready for emergencies and hostile acts, warns Streeting", "https://test/uk")]
        state, translated, sent, _ = self.run_bot(news)
        self.assertEqual(sent.call_count, 2)
        self.assertEqual(translated.call_count, 2)
        self.assertEqual(state["seen"], [tariff["url"], penalty["url"]])
        self.assertIn("TRADE", sent.call_args_list[0].args[0])
        self.assertIn("EQUITIES", sent.call_args_list[1].args[0])
        _, translated, sent, _ = self.run_bot(news, seen=state["seen"])
        translated.assert_not_called()
        sent.assert_not_called()

    def test_local_inflation_is_not_translated_or_sent(self):
        _, translated, sent, output = self.run_bot([
            article("Island inflation rate rises to 3%, figures show", "https://test/local-cpi",
                    "The island's latest figure is compared with UK inflation."),
        ])
        translated.assert_not_called()
        sent.assert_not_called()
        self.assertIn("Statistique économique locale", output)

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

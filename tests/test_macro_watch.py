"""Offline safety and latency tests for the isolated Chicago PMI observer."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import macro_watch as watcher


T0 = datetime(2026, 10, 30, 13, 45, tzinfo=timezone.utc)
OLD_HTML = "<p>Released September 30, 2026</p><p>The Chicago Business Barometer rose 2.0 points to 58.8 in September.</p>"
NEW_HTML = "<p>Released October 30, 2026</p><p>The Chicago Business Barometer fell 1.8 points to 57.0 in October.</p>"
FUTURE_HTML = "<p>Released November 30, 2026</p><p>The Chicago Business Barometer fell 1.8 points to 57.0 in November.</p>"
IDENTITY = {"is_bot": True, "username": watcher.EXPECTED_BOT}
ISM_T0 = datetime(2026, 11, 2, 15, 0, tzinfo=timezone.utc)


def config(**changes):
    data = dict(event_id="chicago-pmi-2026-10", title="Chicago PMI", country="USD", period="2026-10",
                scheduled_at="2026-10-30T13:45:00Z", source_url=watcher.CHICAGO_SOURCE_URL,
                calendar_url=watcher.CALENDAR_URL, poll_seconds=10, max_poll_seconds=180, warmup_seconds=600)
    return watcher.EventConfig.from_dict({**data, **changes})


def calendar(forecast="55.8", previous="58.8", **changes):
    event = dict(title="Chicago PMI", country="USD", date="2026-10-30T09:45:00-04:00",
                 forecast=forecast, previous=previous)
    return json.dumps([{**event, **changes}])


def ism_config(**changes):
    return watcher.EventConfig.from_dict({
        "kind": "ism_manufacturing", "event_id": "ism-manufacturing-2026-10",
        "title": "ISM Manufacturing PMI", "country": "USD", "period": "2026-10",
        "scheduled_at": "2026-11-02T15:00:00Z", "source_url": watcher.ism_source_url("2026-10"),
        "check_source_url": watcher.ism_source_url("2026-09"), **changes,
    })


def ism_calendar(**changes):
    return json.dumps([{
        "title": "ISM Manufacturing PMI", "country": "USD", "date": "2026-11-02T10:00:00-05:00",
        "forecast": "54.7", "previous": "54.5", **changes,
    }])


def ism_report(month="October", year=2026, actual="55.1"):
    # Synthetic structural fixture, not a saved official release.
    return (f"<h1>Manufacturing PMI at {actual}%</h1>"
            f"<h2>{month} {year} ISM Manufacturing PMI Report</h2>"
            f"<p>The Manufacturing PMI registered {actual} percent in {month}.</p>")


class FakeClock:
    def __init__(self, at):
        self.at = at
        self.sleeps = []

    def now(self):
        return self.at

    def sleep(self, seconds):
        if seconds <= 0:
            raise AssertionError("Observer must progress rather than hot-loop")
        self.sleeps.append(seconds)
        self.at += timedelta(seconds=seconds)


class WatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state_path = Path(self.tmp.name) / "macro_test_state.json"
        self.audit_path = Path(self.tmp.name) / "audit.json"
        self.clock = FakeClock(T0 - timedelta(seconds=60))
        self.sent = []
        self.requests = []
        self.source_responses = [watcher.HTTPResult(200, NEW_HTML)]
        self.calendar_response = watcher.HTTPResult(200, calendar())

    def fetch(self, url):
        self.requests.append((url, self.clock.now()))
        if url == watcher.CALENDAR_URL:
            return self.calendar_response
        if len(self.source_responses) == 1:
            return self.source_responses[0]
        return self.source_responses.pop(0)

    def run_watch(self, **changes):
        kwargs = dict(state_path=self.state_path, audit_path=self.audit_path,
                      clock=self.clock.now, sleep=self.clock.sleep, fetch=self.fetch,
                      verify=lambda: dict(IDENTITY), send=self.sent.append)
        return watcher.run_watch(config(), **{**kwargs, **changes})

    def state(self):
        return json.loads(self.state_path.read_text())

    def saved_armed(self, **changes):
        data = dict(event_id=config().event_id, scheduled_at=watcher.timestamp(T0), status="armed",
                    forecast="55.8", previous="58.8", forecast_at=watcher.timestamp(T0 - timedelta(seconds=30)))
        watcher.write_json(self.state_path, {**data, **changes})

    def test_expected_release_freezes_before_time_and_sends_only_once(self):
        report = self.run_watch()
        self.assertEqual(report["outcome"], "result_sent")
        self.assertEqual(len(self.sent), 1)
        self.assertIn("Publié : 57,0", self.sent[0])
        self.assertIn("Consensus enregistré avant annonce : 55,8", self.sent[0])
        self.assertIn("Surprise : +1,2", self.sent[0])
        self.assertIn("TEST MACRO", self.sent[0])
        self.assertEqual(self.state()["status"], "completed")
        self.assertEqual(len([x for x in self.requests if x[0] == watcher.CALENDAR_URL]), 2)
        self.assertTrue(all(moment < T0 for url, moment in self.requests if url == watcher.CALENDAR_URL))
        self.assertTrue(all(moment >= T0 for url, moment in self.requests if url == watcher.CHICAGO_SOURCE_URL))
        previous_requests = list(self.requests)
        rerun = self.run_watch()
        self.assertEqual(rerun["outcome"], "already_reserved_or_finished")
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(previous_requests, self.requests)

    def test_checkpoint_observes_pending_on_disk_before_post(self):
        events = []

        def checkpoint(state):
            self.assertEqual(state["status"], "send_pending")
            self.assertEqual(self.state()["status"], "send_pending")
            self.assertEqual(self.sent, [])
            events.append("checkpoint")

        def send(message):
            self.assertEqual(events, ["checkpoint"])
            self.assertEqual(self.state()["status"], "send_pending")
            events.append("post")
            self.sent.append(message)

        self.run_watch(checkpoint=checkpoint, send=send)
        self.assertEqual(events, ["checkpoint", "post"])

    def test_checkpoint_failure_prevents_post_and_future_retry(self):
        def unavailable_checkpoint(state):
            raise RuntimeError("private transport URL must never reach the audit")

        report = self.run_watch(checkpoint=unavailable_checkpoint)
        self.assertEqual(report["outcome"], "send_checkpoint_unconfirmed")
        self.assertEqual(self.sent, [])
        self.assertEqual(self.state()["status"], "send_pending")
        self.run_watch()
        self.assertEqual(self.sent, [])
        self.assertNotIn("private transport", self.audit_path.read_text())

    def test_uncertain_post_is_never_retried(self):
        attempts = []

        def broken_send(message):
            attempts.append(message)
            raise RuntimeError("connection lost after acceptance might have occurred")

        report = self.run_watch(send=broken_send)
        self.assertEqual(report["outcome"], "telegram_post_unconfirmed_no_retry")
        self.assertEqual(self.state()["status"], "send_uncertain")
        self.run_watch(send=broken_send)
        self.assertEqual(len(attempts), 1)

    def test_older_page_never_becomes_the_new_result(self):
        self.source_responses = [watcher.HTTPResult(200, OLD_HTML)]
        report = self.run_watch()
        self.assertEqual(report["outcome"], "unavailable_notice_sent")
        self.assertEqual(len(self.sent), 1)
        self.assertIn("résultat indisponible", self.sent[0])
        self.assertNotIn("58,8", self.sent[0])
        self.assertEqual(self.state()["status"], "failed")
        self.assertEqual(self.state()["failure_reason"], "release_not_detected_in_window")
        source_requests = [moment for url, moment in self.requests if url == watcher.CHICAGO_SOURCE_URL]
        self.assertLessEqual(len(source_requests), 19)
        self.assertEqual(source_requests[-1], T0 + timedelta(seconds=180))

    def test_future_or_ambiguous_release_is_rejected(self):
        for html in (FUTURE_HTML, NEW_HTML + "<p>Released October 29, 2026</p>"):
            with self.subTest(html=html):
                self.state_path.unlink(missing_ok=True)
                self.clock.at = T0 - timedelta(seconds=1)
                self.sent.clear()
                self.source_responses = [watcher.HTTPResult(200, html)]
                report = self.run_watch()
                self.assertEqual(report["outcome"], "unavailable_notice_sent")
                self.assertNotIn("Publié :", self.sent[0])
                self.assertTrue(all(attempt["outcome"] == "ambiguous_or_unexpected_release_rejected"
                                    for attempt in report["source_attempts"]))

    def test_start_after_release_does_not_retroactively_fetch_consensus(self):
        self.clock.at = T0 + timedelta(seconds=3)
        report = self.run_watch()
        self.assertEqual(self.requests, [])
        self.assertIn("consensus", self.sent[0].lower())
        self.assertEqual(report["failure_reason"], "pre_release_consensus_missing")

    def test_previously_frozen_snapshot_allows_resuming_after_release(self):
        self.clock.at = T0 + timedelta(seconds=3)
        self.saved_armed()
        report = self.run_watch()
        self.assertEqual(report["outcome"], "result_sent")
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0][0], watcher.CHICAGO_SOURCE_URL)

    def test_post_release_snapshot_is_not_accepted(self):
        self.clock.at = T0 + timedelta(seconds=3)
        self.saved_armed(forecast_at=watcher.timestamp(T0))
        report = self.run_watch()
        self.assertEqual(report["failure_reason"], "pre_release_consensus_missing")
        self.assertEqual(self.requests, [])

    def test_calendar_response_crossing_release_is_not_frozen(self):
        self.clock.at = T0 - timedelta(seconds=1)

        def late_calendar(url):
            self.requests.append((url, self.clock.now()))
            self.clock.sleep(2)
            return self.calendar_response

        report = self.run_watch(fetch=late_calendar)
        self.assertEqual(report["failure_reason"], "pre_release_consensus_missing")
        self.assertNotIn("forecast", self.state())

    def test_outside_exact_date_or_window_does_no_network_and_no_state(self):
        for at in (T0 - timedelta(days=1), T0.replace(year=2027),
                   T0 - timedelta(seconds=601), T0 + timedelta(seconds=181)):
            with self.subTest(at=at):
                self.clock.at = at
                result = self.run_watch(verify=lambda: self.fail("must not authenticate"))
                self.assertEqual(result["outcome"], "outside_event_window")
                self.assertFalse(self.state_path.exists())
                self.assertEqual(self.requests, [])

    def test_wrong_bot_identity_blocks_all_sending(self):
        result = self.run_watch(verify=lambda: {"is_bot": True, "username": "other_bot"})
        self.assertEqual(result["outcome"], "telegram_identity_unconfirmed")
        self.assertEqual(self.sent, [])
        self.assertEqual(self.requests, [])

    def test_backup_can_retry_transient_validation_before_any_post(self):
        def unavailable_validation():
            raise RuntimeError("credential-bearing transport error")

        first = self.run_watch(verify=unavailable_validation)
        self.assertEqual(first["outcome"], "telegram_validation_unavailable")
        self.assertEqual(self.state()["status"], "armed")
        self.assertEqual(self.sent, [])
        self.assertEqual(self.requests, [])
        second = self.run_watch()
        self.assertEqual(second["outcome"], "result_sent")
        self.assertEqual(len(self.sent), 1)
        self.assertNotIn("failure_reason", self.state())
        self.assertNotIn("credential-bearing", self.audit_path.read_text())

    def test_source_refusal_is_not_retried_and_failure_is_checkpointed(self):
        self.source_responses = [watcher.HTTPResult(403)]
        checkpoints = []
        report = self.run_watch(checkpoint=lambda state: checkpoints.append(state))
        self.assertEqual(report["outcome"], "unavailable_notice_sent")
        self.assertEqual(len([url for url, _ in self.requests if url == watcher.CHICAGO_SOURCE_URL]), 1)
        self.assertEqual(checkpoints[0]["message_kind"], "unavailable")
        self.assertEqual(len(self.sent), 1)

    def test_429_retry_after_is_honored(self):
        self.source_responses = [watcher.HTTPResult(429, headers={"Retry-After": "45"}),
                                 watcher.HTTPResult(200, NEW_HTML)]
        report = self.run_watch()
        self.assertEqual(report["outcome"], "result_sent")
        requests = [at for url, at in self.requests if url == watcher.CHICAGO_SOURCE_URL]
        self.assertEqual((requests[1] - requests[0]).total_seconds(), 45)

    def test_retry_after_past_deadline_makes_no_additional_request(self):
        self.source_responses = [watcher.HTTPResult(503, headers={"Retry-After": "3600"}),
                                 watcher.HTTPResult(200, NEW_HTML)]
        report = self.run_watch()
        self.assertEqual(report["outcome"], "unavailable_notice_sent")
        self.assertEqual(len([url for url, _ in self.requests if url == watcher.CHICAGO_SOURCE_URL]), 1)
        self.assertEqual(self.clock.at, T0 + timedelta(seconds=180))

    def test_calendar_retry_after_prevents_premature_refresh(self):
        self.calendar_response = watcher.HTTPResult(429, headers={"Retry-After": "3600"})
        self.run_watch()
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0][0], watcher.CALENDAR_URL)

    def test_late_source_response_is_rejected(self):
        self.clock.at = T0
        self.saved_armed()

        def slow_source(url):
            self.clock.sleep(181)
            return watcher.HTTPResult(200, NEW_HTML)

        result = self.run_watch(fetch=slow_source)
        self.assertEqual(result["outcome"], "unavailable_notice_sent")
        self.assertNotIn("Publié :", self.sent[0])

    def test_checkpoint_time_counts_toward_result_deadline(self):
        self.clock.at = T0 + timedelta(seconds=175)
        self.saved_armed()
        result = self.run_watch(checkpoint=lambda _: self.clock.sleep(10))
        self.assertEqual(result["outcome"], "checkpoint_exceeded_result_deadline")
        self.assertEqual(self.sent, [])
        self.assertEqual(self.state()["status"], "failed")

    def test_timing_distinguishes_detection_api_acceptance_and_phone(self):
        self.clock.at = T0 + timedelta(seconds=10)
        self.saved_armed()

        def slow_send(message):
            self.clock.sleep(2)
            self.sent.append(message)

        report = self.run_watch(send=slow_send)
        self.assertEqual(report["first_seen_at"], watcher.timestamp(T0 + timedelta(seconds=10)))
        self.assertEqual(report["telegram_accepted_at"], watcher.timestamp(T0 + timedelta(seconds=12)))
        self.assertEqual(report["telegram_scheduled_to_accepted_seconds"], 12)
        self.assertFalse(report["telegram_receipt_measured"])
        self.assertEqual(self.state()["telegram_api_latency_seconds"], 2)

    def test_malformed_state_blocks_instead_of_resetting(self):
        self.state_path.write_text("broken json")
        with self.assertRaises(watcher.WatchError):
            self.run_watch()
        self.assertEqual(self.sent, [])
        self.saved_armed(status=[])
        with self.assertRaises(watcher.WatchError):
            self.run_watch()


class PublicCheckTests(unittest.TestCase):
    def test_public_check_inspects_old_release_without_state_or_telegram(self):
        urls = []

        def fetch(url):
            urls.append(url)
            return watcher.HTTPResult(200, calendar() if url == watcher.CALENDAR_URL else OLD_HTML)

        with patch("macro_watch._default_verify", side_effect=AssertionError("No Telegram")):
            report = watcher.run_check(config(), fetch=fetch, clock=lambda: T0 - timedelta(days=1))
        self.assertEqual(urls, [watcher.CALENDAR_URL, watcher.CHICAGO_SOURCE_URL])
        self.assertEqual(report["forecast"], "55.8")
        self.assertEqual(report["previous"], "58.8")
        self.assertEqual(report["source_period"], "2026-09")
        self.assertEqual(report["source_actual"], "58.8")
        self.assertFalse(report["ready"])
        self.assertEqual(report["errors"], [])

    def test_exact_calendar_time_country_and_title_are_required(self):
        for changes in ({"country": "EUR"}, {"title": "Manufacturing PMI"},
                        {"date": "2025-10-30T09:45:00-04:00"},
                        {"date": "2026-10-30T09:46:00-04:00"},
                        {"date": "2026-10-30T13:45:00"}):
            with self.subTest(changes=changes), self.assertRaises(watcher.WatchError):
                watcher.calendar_values(calendar(**changes), config())

    def test_pmi_values_reject_percentages_empty_and_wrong_units(self):
        for number in ("55.8%", "", "55K", "nan", "Infinity", "-1", "101", 55.8, None):
            with self.subTest(number=number), self.assertRaises(watcher.WatchError):
                watcher.pmi_number(number)
        self.assertEqual(watcher.pmi_number("55.8"), Decimal("55.8"))

    def test_duplicate_exact_events_are_ambiguous(self):
        events = json.loads(calendar()) * 2
        with self.assertRaises(watcher.WatchError):
            watcher.calendar_values(json.dumps(events), config())

    def test_http_date_retry_after(self):
        response = watcher.HTTPResult(429, headers={"retry-after": "Fri, 30 Oct 2026 13:46:00 GMT"})
        self.assertEqual(watcher.retry_delay(response, T0, 10), 60)

    def test_config_refuses_unbounded_polling_and_unknown_sources(self):
        for changes in ({"poll_seconds": 1}, {"max_poll_seconds": 3600},
                        {"warmup_seconds": 3600}, {"source_url": "https://elsewhere.invalid"}):
            with self.subTest(changes=changes), self.assertRaises(watcher.WatchError):
                config(**changes)

    def test_git_checkpoint_captures_output_and_never_posts(self):
        with patch("macro_watch.subprocess.run") as run:
            run.return_value.returncode = 0
            watcher.git_checkpoint({"status": "send_pending"})
            commands = [call.args[0] for call in run.call_args_list]
            self.assertEqual(commands[0], ["git", "add", "--", "macro_test_state.json"])
            self.assertEqual(commands[-1], ["git", "push", "origin", "HEAD:main"])
            self.assertTrue(all(call.kwargs["capture_output"] for call in run.call_args_list))
        with patch("macro_watch.subprocess.run") as run:
            run.return_value.returncode = 1
            with self.assertRaises(watcher.WatchError):
                watcher.git_checkpoint({})
            self.assertEqual(run.call_count, 1)


class ISMWatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "macro_test_state.json"
        self.audit_path = Path(self.tmp.name) / "audit.json"
        self.clock = FakeClock(ISM_T0 - timedelta(seconds=300))
        self.sent = []
        self.requests = []
        self.source = watcher.HTTPResult(200, ism_report())

    def fetch(self, url):
        self.requests.append((url, self.clock.now()))
        return watcher.HTTPResult(200, ism_calendar()) if url == watcher.CALENDAR_URL else self.source

    def state(self):
        return json.loads(self.path.read_text())

    def run_watch(self, *, event=None, **changes):
        kwargs = dict(state_path=self.path, audit_path=self.audit_path, clock=self.clock.now,
                      sleep=self.clock.sleep, fetch=self.fetch, verify=lambda: IDENTITY,
                      send=self.sent.append)
        return watcher.run_watch(event or ism_config(), **{**kwargs, **changes})

    def armed_state(self, **changes):
        watcher.write_json(self.path, {
            "event_id": ism_config().event_id, "scheduled_at": watcher.timestamp(ISM_T0), "status": "armed",
            "forecast": "54.7", "previous": "54.5", "forecast_at": watcher.timestamp(ISM_T0 - timedelta(seconds=60)),
            **changes,
        })

    def test_ism_release_in_following_month_uses_target_only(self):
        report = self.run_watch()
        self.assertEqual(report["outcome"], "result_sent")
        self.assertEqual(len(self.sent), 1)
        self.assertIn("ISM", self.sent[0])
        self.assertNotIn("Chicago", self.sent[0])
        self.assertEqual(self.state()["actual"], "55.1")
        self.assertTrue(all(url in {watcher.CALENDAR_URL, ism_config().source_url} for url, _ in self.requests))
        self.assertNotIn(ism_config().check_source_url, [url for url, _ in self.requests])

    def test_old_reference_or_old_year_never_sends_an_ism_result(self):
        for body in (ism_report(month="September"), ism_report(year=2025), "<h1>October</h1>"):
            with self.subTest(body=body):
                self.path.unlink(missing_ok=True)
                self.clock.at = ISM_T0 - timedelta(seconds=30)
                self.sent.clear()
                self.source = watcher.HTTPResult(200, body)
                report = self.run_watch(event=ism_config(max_poll_seconds=10))
                self.assertEqual(report["outcome"], "unavailable_notice_sent")
                self.assertEqual(len(self.sent), 1)
                self.assertIn("ISM Manufacturing PMI : résultat indisponible", self.sent[0])
                self.assertIn("10 secondes", self.sent[0])
                self.assertNotIn("180 secondes", self.sent[0])

    def test_armed_snapshot_is_durable_before_waiting_or_final_send(self):
        checkpoints = []

        def arm(state):
            self.assertEqual(self.state(), state)
            self.assertEqual(state["status"], "armed")
            self.assertLess(watcher.parse_time(state["forecast_at"]), ISM_T0)
            self.assertLess(self.clock.now(), ISM_T0)
            self.assertIn("startup_confirmed_at", state)
            self.assertEqual(self.sent, [])
            checkpoints.append(state)

        report = self.run_watch(arm_checkpoint=arm)
        self.assertEqual(report["outcome"], "result_sent")
        self.assertEqual(len(checkpoints), 1)
        self.assertEqual(checkpoints[0]["forecast"], "54.7")
        self.assertIn("startup_confirmed_at", report)

    def test_failed_arm_checkpoint_blocks_run_and_can_be_retried_by_backup(self):
        def broken(state):
            raise RuntimeError("private failure")

        report = self.run_watch(arm_checkpoint=broken)
        self.assertEqual(report["outcome"], "arm_checkpoint_unconfirmed")
        self.assertEqual(self.state()["status"], "armed")
        self.assertNotIn("startup_confirmed_at", self.state())
        self.assertEqual(self.sent, [])
        self.assertTrue(all(url == watcher.CALENDAR_URL for url, _ in self.requests))
        report = self.run_watch(arm_checkpoint=lambda _: None)
        self.assertEqual(report["outcome"], "result_sent")

    def test_startup_notice_and_result_each_have_separate_durable_reservations(self):
        checkpoints = []

        def arm(state):
            self.assertEqual(state, self.state())
            checkpoints.append(("arm", state.get("startup_notice_status")))

        def final(state):
            self.assertEqual(self.state()["status"], "send_pending")
            checkpoints.append(("final", state["message_kind"]))

        def send(message):
            if not self.sent:
                self.assertEqual(self.state()["status"], "armed")
                self.assertEqual(self.state()["startup_notice_status"], "pending")
                self.assertEqual(checkpoints[-1], ("arm", "pending"))
                self.assertLess(self.clock.now(), ISM_T0)
            else:
                self.assertEqual(checkpoints[-1], ("final", "result"))
            self.sent.append(message)

        report = self.run_watch(event=ism_config(notify_start=True), arm_checkpoint=arm, checkpoint=final, send=send)
        self.assertEqual(report["outcome"], "result_sent")
        self.assertEqual(len(self.sent), 2)
        self.assertIn("TEST DÉMARRÉ", self.sent[0])
        self.assertIn("16:00:00 (Paris)", self.sent[0])
        self.assertIn("54.7", self.sent[0])
        self.assertEqual(self.state()["startup_notice_status"], "confirmed")
        self.run_watch(event=ism_config(notify_start=True), arm_checkpoint=arm, checkpoint=final, send=send)
        self.assertEqual(len(self.sent), 2)

    def test_uncertain_startup_post_is_not_retried_but_result_can_still_be_sent(self):
        attempts = []

        def send(message):
            attempts.append(message)
            if len(attempts) == 1:
                raise RuntimeError("Telegram delivery uncertain")

        report = self.run_watch(event=ism_config(notify_start=True), arm_checkpoint=lambda _: None, send=send)
        self.assertEqual(report["outcome"], "result_sent")
        self.assertEqual(self.state()["startup_notice_status"], "uncertain")
        self.assertEqual(len(attempts), 2)
        self.assertIn("TEST DÉMARRÉ", attempts[0])
        self.assertNotIn("TEST DÉMARRÉ", attempts[1])

    def test_startup_503_is_reported_honestly_and_can_recover_at_publication(self):
        official = []

        def fetch(url):
            if url == watcher.CALENDAR_URL:
                return watcher.HTTPResult(200, ism_calendar())
            official.append(self.clock.now())
            return watcher.HTTPResult(503) if len(official) == 1 else watcher.HTTPResult(200, ism_report())

        report = self.run_watch(event=ism_config(notify_start=True), arm_checkpoint=lambda _: None, fetch=fetch)
        self.assertEqual(report["outcome"], "result_sent")
        self.assertEqual(official, [ISM_T0 - timedelta(seconds=300), ISM_T0])
        self.assertEqual(len(self.sent), 2)
        self.assertIn("TEST DÉMARRÉ", self.sent[0])
        self.assertIn("indisponible (HTTP 503)", self.sent[0])
        self.assertEqual(self.state()["startup_source_http_status"], 503)
        self.assertEqual(self.state()["startup_source_readability"], "unavailable")

    def test_startup_retry_after_beyond_deadline_prevents_any_official_poll(self):
        official = []

        def fetch(url):
            if url == watcher.CALENDAR_URL:
                return watcher.HTTPResult(200, ism_calendar())
            official.append(self.clock.now())
            return watcher.HTTPResult(503, headers={"Retry-After": "600"})

        report = self.run_watch(event=ism_config(notify_start=True), arm_checkpoint=lambda _: None, fetch=fetch)
        self.assertEqual(report["outcome"], "unavailable_notice_sent")
        self.assertEqual(official, [ISM_T0 - timedelta(seconds=300)])
        self.assertEqual(report["source_attempts"], [])
        self.assertEqual(self.clock.now(), ISM_T0 + timedelta(seconds=180))
        self.assertEqual(len(self.sent), 2)
        self.assertEqual(watcher.parse_time(self.state()["source_not_before"]), ISM_T0 + timedelta(seconds=300))

    def test_startup_source_get_never_extracts_a_result_before_t0(self):
        parse = watcher.parse_release

        def parse_after_release(config, body):
            self.assertGreaterEqual(self.clock.now(), ISM_T0)
            return parse(config, body)

        with patch("macro_watch.parse_release", side_effect=parse_after_release):
            result = self.run_watch(event=ism_config(notify_start=True), arm_checkpoint=lambda _: None)
        self.assertEqual(result["outcome"], "result_sent")
        self.assertEqual(self.state()["first_seen_at"], watcher.timestamp(ISM_T0))

    def test_saved_pending_confirmed_or_uncertain_startup_is_never_repeated(self):
        for status in ("pending", "confirmed", "uncertain"):
            with self.subTest(status=status):
                self.clock.at = ISM_T0 - timedelta(seconds=30)
                self.sent.clear()
                self.requests.clear()
                self.armed_state(startup_notice_status=status,
                                 startup_confirmed_at=watcher.timestamp(ISM_T0 - timedelta(seconds=60)))
                report = self.run_watch(event=ism_config(notify_start=True), arm_checkpoint=lambda _: None)
                self.assertEqual(report["outcome"], "result_sent")
                self.assertEqual(len(self.sent), 1)
                self.assertNotIn("TEST DÉMARRÉ", self.sent[0])
                self.assertEqual(len([url for url, _ in self.requests if url == ism_config().source_url]), 1)

    def test_startup_pending_checkpoint_failure_prevents_only_its_post(self):
        calls = []

        def arm(state):
            calls.append(state)
            if state.get("startup_notice_status") == "pending":
                raise RuntimeError("Checkpoint failed before POST")

        report = self.run_watch(event=ism_config(notify_start=True), arm_checkpoint=arm)
        self.assertEqual(report["outcome"], "result_sent")
        self.assertEqual(report["startup_notice_outcome"], "checkpoint_unconfirmed_no_post")
        self.assertEqual(len(self.sent), 1)
        self.assertNotIn("TEST DÉMARRÉ", self.sent[0])

    def test_startup_not_sent_without_remote_checkpoint_or_after_announcement(self):
        report = self.run_watch(event=ism_config(notify_start=True))
        self.assertEqual(report["outcome"], "startup_checkpoint_required")
        self.assertEqual(self.sent, [])
        self.clock.at = ISM_T0 + timedelta(seconds=1)
        self.armed_state()
        report = self.run_watch(event=ism_config(notify_start=True), arm_checkpoint=lambda _: None)
        self.assertEqual(report["outcome"], "result_sent")
        self.assertEqual(len(self.sent), 1)
        self.assertNotIn("TEST DÉMARRÉ", self.sent[0])


class ISMPublicCheckTests(unittest.TestCase):
    def test_expected_future_calendar_absence_and_placeholder_are_not_errors(self):
        urls = []

        def fetch(url):
            urls.append(url)
            if url == watcher.CALENDAR_URL:
                return watcher.HTTPResult(200, "[]")
            return watcher.HTTPResult(200, ism_report(month="September", actual="54.5")
                                      if url == ism_config().check_source_url else "<h1>October</h1>")

        report = watcher.run_check(ism_config(), fetch=fetch, clock=lambda: ISM_T0 - timedelta(days=3))
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["calendar_status"], "event_not_listed_yet")
        self.assertEqual(report["source_status"], "target_not_published_yet")
        self.assertEqual(report["historical_source_period"], "2026-09")
        self.assertEqual(report["historical_source_actual"], "54.5")
        self.assertNotIn("forecast", report)
        self.assertNotIn("source_publication_date", report)
        self.assertFalse(report["ready"])
        self.assertEqual(urls, [watcher.CALENDAR_URL, ism_config().source_url, ism_config().check_source_url])

    def test_missing_calendar_at_warmup_is_an_error(self):
        def fetch(url):
            return watcher.HTTPResult(200, "[]" if url == watcher.CALENDAR_URL else ism_report(month="September"))

        report = watcher.run_check(ism_config(), fetch=fetch, clock=lambda: ISM_T0 - timedelta(seconds=600))
        self.assertIn("calendar_event_missing", report["errors"])

    def test_historical_report_cannot_be_accepted_as_target_result(self):
        def fetch(url):
            return watcher.HTTPResult(200, ism_calendar() if url == watcher.CALENDAR_URL else ism_report(month="September"))

        report = watcher.run_check(ism_config(), fetch=fetch, clock=lambda: ISM_T0)
        self.assertFalse(report["ready"])
        self.assertEqual(report["source_status"], "previous_release_only")
        self.assertTrue(report["historical_control_only"])

    def test_ism_config_enforces_next_month_fixed_target_and_control(self):
        self.assertEqual(ism_config().kind, "ism_manufacturing")
        inferred = ism_config(kind="ism_manufacturing")
        self.assertEqual(inferred.period, "2026-10")
        for changes in ({"source_url": watcher.ism_source_url("2026-09")},
                        {"check_source_url": watcher.ism_source_url("2026-08")},
                        {"scheduled_at": "2026-10-30T15:00:00Z"},
                        {"notify_start": "yes"}, {"kind": "unknown"}, {"check_source_url": []}):
            with self.subTest(changes=changes), self.assertRaises(watcher.WatchError):
                ism_config(**changes)
        december = ism_config(event_id="ism-manufacturing-2026-12", period="2026-12",
                              source_url=watcher.ism_source_url("2026-12"),
                              check_source_url=watcher.ism_source_url("2026-11"),
                              scheduled_at="2027-01-04T15:00:00Z")
        self.assertEqual(december.previous_period, "2026-11")

    def test_public_get_rejects_unknown_ism_path_host_or_query_without_network(self):
        for url in ("https://example.invalid/pmi/october/", ism_config().source_url + "?redirect=evil",
                    "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-pmi-reports/services/october/"):
            with self.subTest(url=url), patch("macro_watch.requests.get") as get:
                with self.assertRaises(watcher.WatchError):
                    watcher.public_fetch(url)
                get.assert_not_called()

    def test_git_checkpoint_skips_empty_commit_but_pushes_and_commits_changes(self):
        for codes, expect_commit in (([0, 0, 0, 0], False), ([0, 1, 0, 0, 0], True)):
            with self.subTest(codes=codes), patch("macro_watch.subprocess.run") as run:
                run.side_effect = [Mock(returncode=code) for code in codes]
                watcher.git_checkpoint({"status": "armed"})
                commands = [call.args[0] for call in run.call_args_list]
                self.assertEqual(any(command[1] == "commit" for command in commands), expect_commit)
                self.assertEqual(commands[-1], ["git", "push", "origin", "HEAD:main"])


if __name__ == "__main__":
    unittest.main()

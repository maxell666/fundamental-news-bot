"""Offline route and scheduling checks; no requests leave this test process."""

from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import requests

from macro_watch import EventConfig, timestamp
from scripts import dispatch_macro as dispatcher


T0 = datetime(2026, 10, 30, 13, 45, tzinfo=timezone.utc)
CONFIG = dict(event_id="chicago-pmi-2026-10", title="Chicago PMI", country="USD",
              period="2026-10", scheduled_at="2026-10-30T13:45:00Z",
              poll_seconds=10, max_poll_seconds=180, warmup_seconds=600)


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.config = EventConfig.from_dict(CONFIG)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config_path = Path(self.tmp.name) / "config.json"
        self.state_path = Path(self.tmp.name) / "state.json"
        self.config_path.write_text(json.dumps(CONFIG))
        self.post = Mock(return_value=SimpleNamespace(status_code=204))
        self.output = io.StringIO()

    def state(self, status="armed", **changes):
        return {**dict(event_id=self.config.event_id, scheduled_at=timestamp(T0), status=status), **changes}

    def run_main(self, *, now=None, probe=False, token="ghs_test_token"):
        argv = ["--config", str(self.config_path), "--state", str(self.state_path)]
        if probe:
            argv.append("--probe-check")
        with patch.dict("os.environ", {"GH_TOKEN": token}), redirect_stdout(self.output):
            return dispatcher.main(argv, now=now or T0 - timedelta(seconds=300), post=self.post)

    def test_exact_lead_window_accepts_edges_only(self):
        for seconds in (600, 599, 300, 15):
            with self.subTest(seconds=seconds):
                self.assertTrue(dispatcher.should_dispatch(T0 - timedelta(seconds=seconds), self.config, None))
        for seconds in (601, 14, 0, -1, -3600):
            with self.subTest(seconds=seconds):
                self.assertFalse(dispatcher.should_dispatch(T0 - timedelta(seconds=seconds), self.config, None))

    def test_wrong_day_year_and_naive_clock_block(self):
        for now in (T0 - timedelta(days=1, seconds=300),
                    (T0 - timedelta(seconds=300)).replace(year=2027),
                    (T0 - timedelta(seconds=300)).replace(tzinfo=None)):
            with self.subTest(now=now):
                self.assertFalse(dispatcher.should_dispatch(now, self.config, None))

    def test_aware_time_is_compared_in_utc(self):
        paris_fixed = timezone(timedelta(hours=1))
        now = (T0 - timedelta(seconds=300)).astimezone(paris_fixed)
        self.assertTrue(dispatcher.should_dispatch(now, self.config, None))

    def test_only_valid_armed_state_allows_dispatch(self):
        now = T0 - timedelta(seconds=300)
        self.assertTrue(dispatcher.should_dispatch(now, self.config, self.state()))
        for state in (self.state("send_pending"), self.state("completed"), self.state("send_uncertain"),
                      self.state("failed"), self.state("unknown"), {}, [],
                      self.state(status=[]),
                      self.state(event_id="chicago-pmi-2025-10"),
                      self.state(scheduled_at="2026-10-30T13:46:00.000Z")):
            with self.subTest(state=state):
                self.assertFalse(dispatcher.should_dispatch(now, self.config, state))

    def test_default_mode_requests_watch_on_fixed_route_and_main(self):
        self.assertEqual(self.run_main(), 0)
        self.post.assert_called_once()
        args, kwargs = self.post.call_args
        self.assertEqual(args, (dispatcher.DISPATCH_URL,))
        self.assertEqual(kwargs["json"], {"ref": "main", "inputs": {"mode": "watch"}})
        self.assertFalse(kwargs["allow_redirects"])
        self.assertEqual(kwargs["timeout"], (3, 8))
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer ghs_test_token")
        self.assertIn("Démarrage du workflow non confirmé", self.output.getvalue())
        self.assertNotIn("ghs_test_token", self.output.getvalue())
        self.assertFalse(self.state_path.exists())

    def test_outside_window_needs_neither_token_nor_post(self):
        self.assertEqual(self.run_main(now=T0 + timedelta(seconds=1), token=""), 0)
        self.post.assert_not_called()

    def test_saved_pending_state_makes_no_post(self):
        self.state_path.write_text(json.dumps(self.state("send_pending")))
        self.assertEqual(self.run_main(), 0)
        self.post.assert_not_called()

    def test_malformed_state_blocks_instead_of_resetting(self):
        self.state_path.write_text("invalid json")
        self.assertEqual(self.run_main(), 1)
        self.post.assert_not_called()
        self.assertEqual(self.state_path.read_text(), "invalid json")

    def test_probe_explicitly_requests_check_outside_event_window(self):
        self.assertEqual(self.run_main(now=T0 + timedelta(days=20), probe=True), 0)
        self.post.assert_called_once()
        self.assertEqual(self.post.call_args.kwargs["json"], {"ref": "main", "inputs": {"mode": "check"}})
        self.assertNotIn("watch", self.post.call_args.kwargs["json"]["inputs"].values())

    def test_missing_token_blocks_inside_window(self):
        self.assertEqual(self.run_main(token=""), 1)
        self.post.assert_not_called()

    def test_api_refusal_logs_only_status_and_never_body(self):
        self.post.return_value = SimpleNamespace(status_code=403, text="private body and token")
        self.assertEqual(self.run_main(probe=True), 1)
        self.assertIn("HTTP 403", self.output.getvalue())
        self.assertNotIn("private body", self.output.getvalue())
        self.assertNotIn("ghs_test_token", self.output.getvalue())

    def test_network_uncertainty_is_sanitized_without_retry(self):
        self.post.side_effect = requests.ConnectionError("private_url?token=secret")
        self.assertEqual(self.run_main(probe=True), 1)
        self.post.assert_called_once()
        self.assertNotIn("private_url", self.output.getvalue())
        self.assertNotIn("secret", self.output.getvalue())

    def test_direct_dispatch_rejects_unsupported_mode_and_empty_token(self):
        for mode, token in (("send", "ghs_test"), ("watch", ""), ("check", "broken\r\nheader")):
            with self.subTest(mode=mode, token=token), self.assertRaises(dispatcher.DispatchError):
                dispatcher.dispatch(mode, token, post=self.post)
        self.post.assert_not_called()


if __name__ == "__main__":
    unittest.main()

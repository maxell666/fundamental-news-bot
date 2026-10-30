"""Let the existing cron-job news runner arm the separate dated macro test.

This step never waits for the release and never contacts Telegram. GitHub's
204 confirms acceptance of a dispatch request, not that its watcher started.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from macro_watch import EventConfig, WatchError, read_state, timestamp


DISPATCH_URL = "https://api.github.com/repos/maxell666/fundamental-news-bot/actions/workflows/macro-test.yml/dispatches"


class DispatchError(ValueError):
    """A sanitized dispatch failure, without HTTP bodies or credential URLs."""


def should_dispatch(now: datetime, config: EventConfig, state: dict | None) -> bool:
    """Exact UTC date and T-600..T-15 only; malformed or reserved state blocks."""
    if now.tzinfo is None or now.utcoffset() is None:
        return False
    now = now.astimezone(timezone.utc)
    scheduled = config.scheduled_at.astimezone(timezone.utc)
    if now.date() != scheduled.date():
        return False
    lead = (scheduled - now).total_seconds()
    if not 15 <= lead <= min(config.warmup_seconds, 600):
        return False
    if state is None:
        return True
    return (isinstance(state, dict)
            and state.get("event_id") == config.event_id
            and state.get("scheduled_at") == timestamp(scheduled)
            and state.get("status") == "armed")


def dispatch(mode: str, token: str, *, post=requests.post) -> int:
    """One POST, fixed repository/workflow/ref, with no retry or sensitive log."""
    if mode not in {"watch", "check"}:
        raise DispatchError("Mode de déclenchement non autorisé")
    if not isinstance(token, str) or not token.strip() or "\n" in token or "\r" in token:
        raise DispatchError("Jeton automatique GitHub indisponible")
    try:
        response = post(
            DISPATCH_URL,
            headers={"Authorization": "Bearer " + token.strip(),
                     "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
            json={"ref": "main", "inputs": {"mode": mode}},
            timeout=(3, 8), allow_redirects=False,
        )
    except requests.RequestException:
        raise DispatchError("Déclenchement GitHub non confirmé ; aucun réessai dans ce run") from None
    return response.status_code


def main(argv: list[str] | None = None, *, now: datetime | None = None, post=requests.post) -> int:
    parser = argparse.ArgumentParser(description="Déclencher le watcher macro depuis le run news existant")
    parser.add_argument("--probe-check", action="store_true", help="Tester une fois la route GitHub en mode contrôle sans Telegram")
    parser.add_argument("--config", type=Path, default=REPO_ROOT / "config/macro_active_test.json")
    parser.add_argument("--state", type=Path, default=REPO_ROOT / "macro_test_state.json")
    args = parser.parse_args(argv)
    try:
        mode = "check" if args.probe_check else "watch"
        if mode == "watch":
            config = EventConfig.from_dict(json.loads(args.config.read_text(encoding="utf-8")))
            state = read_state(args.state, config)
            if not should_dispatch(now or datetime.now(timezone.utc), config, state):
                print("Macro : aucun déclenchement nécessaire hors fenêtre ou état déjà réservé.")
                return 0
        status = dispatch(mode, os.environ.get("GH_TOKEN", ""), post=post)
        if status == 204:
            print(f"Macro : requête {mode} acceptée par GitHub (HTTP 204). Démarrage du workflow non confirmé par ce statut.")
            return 0
        print(f"Macro : requête refusée par GitHub (HTTP {status}). Aucun réessai dans ce run.")
        return 1
    except (DispatchError, WatchError, OSError, TypeError, ValueError):
        print("Macro : déclenchement non confirmé (configuration, état ou autorisation GitHub). Aucun réessai dans ce run.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

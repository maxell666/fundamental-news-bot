"""One dated Chicago PMI latency test, independent from the news bot.

Public checks never import the Telegram module. The observer freezes calendar
values before the announcement, accepts only the expected official release,
and durably records a send intent before the sole Telegram POST. No result is
accepted after the three-minute observation window; a failure notice can close
that window without representing a late figure as a timely result.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from typing import Callable
from zoneinfo import ZoneInfo

import requests

from pmi_release import (
    CHICAGO_SOURCE_URL, ReleaseNotReady, ReleaseParseError,
    format_chicago_test_message, inspect_chicago_release, parse_chicago_release,
)


UTC = timezone.utc
CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
EXPECTED_BOT = "Annonces_eco_tribal_bot"
STATE_NAME = "macro_test_state.json"
MAX_BODY_BYTES = 2 * 1024 * 1024
TERMINAL_STATUSES = {"send_pending", "completed", "failed", "send_uncertain"}
ALL_STATUSES = TERMINAL_STATUSES | {"armed"}


class WatchError(ValueError):
    """A safe, fixed-text diagnostic, never a raw HTTP or Telegram error."""


@dataclass(frozen=True)
class HTTPResult:
    status: int
    text: str = ""
    headers: dict | None = None


@dataclass(frozen=True)
class EventConfig:
    event_id: str
    title: str
    country: str
    period: str
    scheduled_at: datetime
    source_url: str = CHICAGO_SOURCE_URL
    calendar_url: str = CALENDAR_URL
    poll_seconds: int = 10
    max_poll_seconds: int = 180
    warmup_seconds: int = 600

    @property
    def deadline(self) -> datetime:
        return self.scheduled_at + timedelta(seconds=self.max_poll_seconds)

    @classmethod
    def from_dict(cls, data: dict) -> "EventConfig":
        try:
            config = cls(**{**data, "scheduled_at": parse_time(data["scheduled_at"])})
        except (TypeError, KeyError, ValueError):
            raise WatchError("Configuration macro incorrecte") from None
        if (config.title != "Chicago PMI" or config.country != "USD"
                or not re.fullmatch(r"chicago-pmi-\d{4}-\d{2}", config.event_id)
                or config.event_id != "chicago-pmi-" + config.period
                or config.scheduled_at.strftime("%Y-%m") != config.period
                or config.source_url != CHICAGO_SOURCE_URL
                or config.calendar_url != CALENDAR_URL
                or type(config.poll_seconds) is not int or not 10 <= config.poll_seconds <= 30
                or type(config.max_poll_seconds) is not int or not 10 <= config.max_poll_seconds <= 180
                or type(config.warmup_seconds) is not int or not 0 <= config.warmup_seconds <= 600):
            raise WatchError("Configuration macro hors des limites du test")
        return config


def parse_time(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Time is not a string")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("Time has no timezone")
    return result.astimezone(UTC)


def timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def utc_now() -> datetime:
    return datetime.now(UTC)


def public_fetch(url: str) -> HTTPResult:
    """Bounded public GET. Never expose requests' URL-bearing exceptions."""
    if url not in {CHICAGO_SOURCE_URL, CALENDAR_URL}:
        raise WatchError("Source publique non autorisée pour ce test")
    try:
        with requests.get(
            url, timeout=(3, 8), stream=True, allow_redirects=False,
            headers={"User-Agent": "FundamentalNewsBot/ChicagoPMI-Test", "Cache-Control": "no-cache"},
        ) as response:
            chunks, size = [], 0
            if response.status_code == 200:
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > MAX_BODY_BYTES:
                        raise WatchError("Réponse publique trop volumineuse")
                    chunks.append(chunk)
            body = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
            return HTTPResult(response.status_code, body, dict(response.headers))
    except requests.RequestException:
        raise WatchError("Connexion à la source publique non confirmée") from None


def pmi_number(value: object) -> Decimal:
    if not isinstance(value, str) or not re.fullmatch(r"\d{1,3}(?:\.\d+)?", value.strip()):
        raise WatchError("Consensus PMI absent ou unité inattendue")
    try:
        number = Decimal(value.strip())
    except InvalidOperation:
        raise WatchError("Consensus PMI illisible") from None
    if not number.is_finite() or not Decimal(0) <= number <= Decimal(100):
        raise WatchError("Consensus PMI hors limites")
    return number


def calendar_values(body: str, config: EventConfig) -> tuple[Decimal, Decimal]:
    try:
        entries = json.loads(body)
    except (ValueError, TypeError):
        raise WatchError("Calendrier public illisible") from None
    if not isinstance(entries, list):
        raise WatchError("Format du calendrier public inattendu")
    matching = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("title") != config.title or entry.get("country") != config.country:
            continue
        try:
            exact_time = parse_time(entry.get("date"))
        except (TypeError, ValueError):
            continue
        if exact_time == config.scheduled_at:
            matching.append(entry)
    if len(matching) != 1:
        raise WatchError("Annonce exacte absente ou ambiguë dans le calendrier")
    return pmi_number(matching[0].get("forecast")), pmi_number(matching[0].get("previous"))


def write_json(path: Path, data: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            temporary = handle.name
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
        # Persist the rename too, before a send intent can be acknowledged.
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary is not None:
            os.unlink(temporary)


def read_state(path: Path, config: EventConfig) -> dict | None:
    if not path.exists():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise WatchError("État macro illisible ; envoi bloqué pour éviter un doublon") from None
    if (not isinstance(state, dict) or state.get("event_id") != config.event_id
            or state.get("scheduled_at") != timestamp(config.scheduled_at)
            or state.get("status") not in ALL_STATUSES):
        raise WatchError("État macro incompatible ; envoi bloqué pour éviter un doublon")
    return state


def retry_delay(response: HTTPResult, now: datetime, default: float) -> float:
    headers = {str(key).lower(): value for key, value in (response.headers or {}).items()}
    value = str(headers.get("retry-after", "")).strip()
    if value.isdigit():
        return max(default, float(value))
    if value:
        try:
            moment = parsedate_to_datetime(value)
            if moment.tzinfo is not None:
                return max(default, (moment.astimezone(UTC) - now).total_seconds())
        except (TypeError, ValueError, OverflowError):
            pass
    return default


def run_check(config: EventConfig, *, fetch: Callable = public_fetch,
              clock: Callable = utc_now, audit_path: Path | None = None) -> dict:
    """One GET per public source; no Telegram import, secrets, or send state."""
    result = {"mode": "check", "event_id": config.event_id,
              "checked_at": timestamp(clock()), "scheduled_at": timestamp(config.scheduled_at),
              "expected_period": config.period, "ready": False, "errors": []}
    try:
        calendar = fetch(config.calendar_url)
        result["calendar_http_status"] = calendar.status
        if calendar.status != 200:
            raise WatchError("Calendrier indisponible")
        forecast, previous = calendar_values(calendar.text, config)
        result.update(forecast=str(forecast), previous=str(previous),
                      consensus_note="Contrôle public uniquement ; le watcher figera sa propre copie avant annonce")
    except (WatchError, OSError, ValueError):
        result["errors"].append("calendar_unavailable_or_invalid")
    try:
        source = fetch(config.source_url)
        result["source_http_status"] = source.status
        if source.status != 200:
            raise WatchError("Source officielle indisponible")
        summary = inspect_chicago_release(source.text)
        result.update(source_period=summary.period, source_actual=str(summary.actual),
                      source_publication_date=summary.publication_date.isoformat())
        try:
            parse_chicago_release(source.text, expected_period=config.period,
                                  expected_release_at=config.scheduled_at)
            result["ready"] = clock() >= config.scheduled_at
        except ReleaseNotReady:
            result["source_status"] = "previous_release_only"
        except ReleaseParseError:
            result["errors"].append("source_not_expected_release")
    except (WatchError, OSError, ReleaseParseError, ValueError):
        result["errors"].append("source_unavailable_or_invalid")
    if audit_path is not None:
        write_json(audit_path, result)
    return result


def _default_verify() -> dict:
    from bot import CHAT_ID, verify_telegram_token
    if not CHAT_ID:
        raise WatchError("Destination Telegram absente")
    return verify_telegram_token()


def _default_send(message: str) -> None:
    from bot import send_telegram
    send_telegram(message)


def git_checkpoint(state: dict) -> None:
    """Push the fixed send-intent file before the external side effect.

    A failed push prevents sending. Output is captured because git diagnostics
    can include authenticated remote URLs. The workflow supplies git identity.
    """
    commands = [
        ["git", "add", "--", STATE_NAME],
        ["git", "commit", "-m", "Reserve Chicago PMI test send [skip ci]", "--", STATE_NAME],
        ["git", "pull", "--rebase", "origin", "main"],
        ["git", "push", "origin", "HEAD:main"],
    ]
    for command in commands:
        try:
            completed = subprocess.run(command, capture_output=True, timeout=30, check=False)
        except (OSError, subprocess.TimeoutExpired):
            raise WatchError("Sauvegarde distante du test non confirmée ; envoi bloqué") from None
        if completed.returncode != 0:
            raise WatchError("Sauvegarde distante du test non confirmée ; envoi bloqué")


def run_watch(config: EventConfig, *, state_path: Path = Path(STATE_NAME),
              audit_path: Path | None = None, clock: Callable = utc_now,
              sleep: Callable = time.sleep, fetch: Callable = public_fetch,
              verify: Callable = _default_verify, send: Callable = _default_send,
              checkpoint: Callable | None = None) -> dict:
    """Observe only this dated event. All I/O and time are injectable for tests."""
    state_path = Path(state_path)
    state = read_state(state_path, config)
    audit = {"mode": "watch", "event_id": config.event_id,
             "scheduled_at": timestamp(config.scheduled_at), "started_at": timestamp(clock()),
             "source_attempts": [], "calendar_attempts": [], "telegram_receipt_measured": False}

    def finish(reason: str) -> dict:
        audit["outcome"] = reason
        audit["finished_at"] = timestamp(clock())
        if state is not None:
            audit["state_status"] = state["status"]
            for key in ("first_seen_at", "telegram_accepted_at", "forecast_at", "failure_reason"):
                if key in state:
                    audit[key] = state[key]
        if audit_path is not None:
            write_json(audit_path, audit)
        return audit

    if state is not None and state["status"] in TERMINAL_STATUSES:
        return finish("already_reserved_or_finished")
    now = clock()
    earliest = config.scheduled_at - timedelta(seconds=config.warmup_seconds)
    if now.date() != config.scheduled_at.date() or not earliest <= now <= config.deadline:
        return finish("outside_event_window")
    if state is None:
        state = {"event_id": config.event_id, "scheduled_at": timestamp(config.scheduled_at), "status": "armed"}
        write_json(state_path, state)
    try:
        identity = verify()
    except Exception:
        # No POST was attempted: the scheduled backup can retry this read-only
        # validation after a transient outage.
        state.update(status="armed", failure_reason="telegram_validation_unavailable")
        write_json(state_path, state)
        return finish("telegram_validation_unavailable")
    if (not isinstance(identity, dict) or identity.get("is_bot") is not True
            or not isinstance(identity.get("username"), str)
            or identity["username"].lower() != EXPECTED_BOT.lower()):
        state.update(status="failed", failure_reason="telegram_identity_unconfirmed")
        write_json(state_path, state)
        return finish("telegram_identity_unconfirmed")
    state.pop("failure_reason", None)

    def wait_until(moment: datetime) -> None:
        # Short waits keep cancellation responsive; never advance past target.
        while clock() < moment:
            sleep(min(30.0, (moment - clock()).total_seconds()))

    def snapshot_valid() -> bool:
        try:
            pmi_number(state["forecast"])
            pmi_number(state["previous"])
            return parse_time(state["forecast_at"]) < config.scheduled_at
        except (KeyError, ValueError, TypeError):
            return False

    def freeze_forecast() -> None:
        if clock() >= config.scheduled_at:
            return
        if (audit.get("calendar_access_refused")
                or (audit.get("calendar_retry_at")
                    and clock() < parse_time(audit["calendar_retry_at"]))):
            return
        attempt = {"requested_at": timestamp(clock())}
        audit["calendar_attempts"].append(attempt)
        try:
            response = fetch(config.calendar_url)
            attempt["http_status"] = response.status
            if response.status != 200:
                if response.status in {401, 403}:
                    audit["calendar_access_refused"] = True
                if response.status in {429, 503}:
                    audit["calendar_retry_at"] = timestamp(
                        clock() + timedelta(seconds=retry_delay(response, clock(), 30)))
                attempt["outcome"] = "unavailable"
                return
            forecast, previous = calendar_values(response.text, config)
            frozen_at = clock()
            if frozen_at >= config.scheduled_at:
                attempt["outcome"] = "response_after_release_not_frozen"
                return
            state.update(forecast=str(forecast), previous=str(previous), forecast_at=timestamp(frozen_at))
            write_json(state_path, state)
            attempt["outcome"] = "frozen_before_release"
        except Exception:
            attempt["outcome"] = "unavailable_or_invalid"

    # At most two calendar GETs. A retry-after refusal cannot create a hot loop.
    if clock() < config.scheduled_at:
        freeze_forecast()
        refresh_at = config.scheduled_at - timedelta(seconds=30)
        if clock() < refresh_at:
            wait_until(refresh_at)
            freeze_forecast()
    wait_until(config.scheduled_at)

    def emit_once(message: str, kind: str, failure: str | None = None) -> dict:
        # The remote checkpoint closes the kill-between-POST-and-commit gap.
        state.update(status="send_pending", message_kind=kind, send_reserved_at=timestamp(clock()))
        if failure:
            state["failure_reason"] = failure
        write_json(state_path, state)
        try:
            if checkpoint is not None:
                checkpoint(dict(state))
        except Exception:
            state["failure_reason"] = "send_checkpoint_unconfirmed"
            write_json(state_path, state)
            return finish("send_checkpoint_unconfirmed")
        # Git checkpoint latency counts towards timeliness, never hidden.
        if kind == "result" and clock() > config.deadline:
            state.update(status="failed", failure_reason="checkpoint_exceeded_result_deadline")
            write_json(state_path, state)
            return finish("checkpoint_exceeded_result_deadline")
        # A close-out failure notice may follow T+180; never on another date or
        # more than 120 seconds later (bounded git checkpoint + Telegram timeouts).
        if (clock().date() != config.scheduled_at.date()
                or clock() > config.deadline + timedelta(seconds=120)):
            state.update(status="failed", failure_reason="send_window_closed")
            write_json(state_path, state)
            return finish("send_window_closed")
        state["telegram_post_started_at"] = timestamp(clock())
        write_json(state_path, state)
        try:
            send(message)
        except Exception:
            state.update(status="send_uncertain", failure_reason="telegram_post_unconfirmed")
            write_json(state_path, state)
            return finish("telegram_post_unconfirmed_no_retry")
        accepted_at = clock()
        state.update(status="completed" if kind == "result" else "failed",
                     telegram_accepted_at=timestamp(accepted_at))
        state["telegram_api_latency_seconds"] = round(
            (accepted_at - parse_time(state["telegram_post_started_at"])).total_seconds(), 3)
        write_json(state_path, state)
        audit["telegram_scheduled_to_accepted_seconds"] = round(
            (accepted_at - config.scheduled_at).total_seconds(), 3)
        return finish("result_sent" if kind == "result" else "unavailable_notice_sent")

    def unavailable(reason: str) -> dict:
        reasons = {
            "pre_release_consensus_missing": "Le consensus et le précédent n’ont pas pu être figés avant l’annonce.",
            "source_access_refused": "La source officielle a refusé l’accès ; les requêtes ont été arrêtées.",
            "release_not_detected_in_window": "Le résultat attendu n’a pas été confirmé dans les 180 secondes suivant l’heure prévue.",
        }
        message = ("🧪 TEST MACRO — Chicago PMI : résultat indisponible\n"
                   f"Période : {config.period}\n"
                   f"Heure prévue (Paris) : {config.scheduled_at.astimezone(ZoneInfo('Europe/Paris')):%d/%m/%Y %H:%M:%S}\n"
                   + reasons[reason] + "\nAucun résultat ni biais n’est déduit.\n"
                   "Ce message clôt uniquement l’essai ; réception sur le téléphone non mesurée.")
        return emit_once(message, "unavailable", reason)

    if not snapshot_valid():
        return unavailable("pre_release_consensus_missing")
    while clock() <= config.deadline and clock().date() == config.scheduled_at.date():
        requested_at = clock()
        attempt = {"requested_at": timestamp(requested_at)}
        audit["source_attempts"].append(attempt)
        delay = float(config.poll_seconds)
        try:
            response = fetch(config.source_url)
        except Exception:
            attempt["outcome"] = "source_request_unconfirmed"
        else:
            attempt["http_status"] = response.status
            now = clock()
            if now > config.deadline:
                attempt["outcome"] = "response_after_deadline_rejected"
                break
            if response.status in {401, 403}:
                attempt["outcome"] = "access_refused_no_retry"
                return unavailable("source_access_refused")
            if response.status in {429, 503}:
                attempt["outcome"] = "backoff"
                delay = retry_delay(response, now, delay)
            elif response.status == 200:
                try:
                    release = parse_chicago_release(response.text, expected_period=config.period,
                                                    expected_release_at=config.scheduled_at)
                except ReleaseNotReady:
                    attempt["outcome"] = "previous_release_only"
                except ReleaseParseError:
                    attempt["outcome"] = "ambiguous_or_unexpected_release_rejected"
                else:
                    observed_at = clock()
                    if observed_at > config.deadline:
                        attempt["outcome"] = "parsing_after_deadline_rejected"
                        break
                    attempt["outcome"] = "expected_release_confirmed"
                    state.update(first_seen_at=timestamp(observed_at), actual=str(release.actual), period=release.period)
                    message = format_chicago_test_message(
                        release, Decimal(state["forecast"]), Decimal(state["previous"]),
                        observed_at=observed_at, forecast_at=parse_time(state["forecast_at"]))
                    return emit_once(message, "result")
            elif 400 <= response.status < 500 and response.status != 404:
                attempt["outcome"] = "access_refused_no_retry"
                return unavailable("source_access_refused")
            else:
                attempt["outcome"] = "not_available_yet"
        remaining = (config.deadline - clock()).total_seconds()
        if remaining <= 0:
            break
        wait_until(clock() + timedelta(seconds=min(delay, remaining)))
        if delay > remaining:
            # Honor the complete Retry-After by making no further request.
            break
    return unavailable("release_not_detected_in_window")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Essai unique Chicago PMI, séparé des alertes news")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Contrôle public sans Telegram ni état d’envoi")
    mode.add_argument("--watch", action="store_true", help="Observer uniquement pendant la fenêtre datée")
    parser.add_argument("--config", default="config/macro_chicago_test.json")
    parser.add_argument("--checkpoint-git", action="store_true", help="Sauvegarder l’intention sur main avant tout envoi")
    args = parser.parse_args(argv)
    try:
        config = EventConfig.from_dict(json.loads(Path(args.config).read_text(encoding="utf-8")))
        if args.check:
            if args.checkpoint_git:
                raise WatchError("Le contrôle public ne sauvegarde aucun état d’envoi")
            report = run_check(config, audit_path=Path("macro_audit/check.json"))
        else:
            report = run_watch(config, audit_path=Path("macro_audit/watch.json"),
                               checkpoint=git_checkpoint if args.checkpoint_git else None)
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        if args.check:
            return 1 if report["errors"] else 0
        return 0 if report["outcome"] in {"result_sent", "already_reserved_or_finished", "outside_event_window"} else 1
    except (WatchError, OSError, ValueError):
        # No traceback: transport exceptions can contain credential-bearing URLs.
        print("Test macro arrêté : configuration, état ou sauvegarde non confirmé. Aucun réessai automatique d’envoi.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

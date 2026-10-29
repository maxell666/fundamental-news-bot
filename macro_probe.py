"""Vérification publique des sources du test ECI, sans aucun envoi."""
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests


ECI_URLS = (
    "https://www.bls.gov/news.release/eci.nr0.htm",
    "https://www.bls.gov/news.release/eci.htm",
)
CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
ECI_API_URL = "https://api.bls.gov/publicAPI/v1/timeseries/data/CIS1010000000000Q?startyear=2026&endyear=2026"
HEADERS = {
    "User-Agent": "fundamental-news-bot/3.0 macro-test (https://github.com/maxell666/fundamental-news-bot)",
    "Accept": "text/html,application/json;q=0.9,text/plain;q=0.8",
}


def get_public(url, headers=None):
    start = time.monotonic()
    response = requests.get(url, timeout=(5, 10), headers={**HEADERS, **(headers or {})}, stream=True)
    try:
        body, length = [], 0
        for chunk in response.iter_content(chunk_size=16384):
            length += len(chunk)
            if length > 2_000_000:
                raise RuntimeError("Réponse officielle trop volumineuse")
            body.append(chunk)
        content = b"".join(body)
        return response.status_code, content, {
            "elapsed_ms": round((time.monotonic() - start) * 1000, 1),
            "received_at": datetime.now(timezone.utc).isoformat(),
            "content_type": response.headers.get("Content-Type", ""),
            "etag": response.headers.get("ETag"),
            "last_modified": response.headers.get("Last-Modified"),
            "retry_after": response.headers.get("Retry-After"),
        }
    finally:
        response.close()


def main():
    directory = Path("macro_audit")
    directory.mkdir(exist_ok=True)
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "sources": []}
    usable = False
    for index, url in enumerate(ECI_URLS):
        item = {"url": url}
        try:
            status, body, timing = get_public(url)
            text = body.decode("utf-8", errors="replace")
            plain = re.sub(r"<[^>]+>", " ", text)
            valid = status == 200 and "compensation costs for civilian workers" in plain.lower()
            item.update({"http_status": status, "release_content": valid, **timing})
            if valid:
                (directory / f"eci_source_{index}.html").write_text(text, encoding="utf-8")
                usable = True
        except (requests.RequestException, RuntimeError):
            item.update({"error": "Source non accessible, détails réseau masqués"})
        report["sources"].append(item)
        print("MACRO_SOURCE", json.dumps(item, ensure_ascii=False))
    try:
        status, body, timing = get_public(CALENDAR_URL)
        entries = json.loads(body) if status == 200 else []
        matches = [item for item in entries if item.get("country") == "USD"
                   and item.get("title") == "Employment Cost Index q/q"]
        report["calendar"] = {"http_status": status, "matches": matches, **timing}
        print("MACRO_CALENDAR", json.dumps(report["calendar"], ensure_ascii=False))
    except (requests.RequestException, ValueError, RuntimeError):
        report["calendar"] = {"error": "Calendrier indisponible"}
        matches = []
    try:
        status, body, timing = get_public(ECI_API_URL)
        payload = json.loads(body) if status == 200 else {}
        series = payload.get("Results", {}).get("series", [])
        valid_api = (payload.get("status") == "REQUEST_SUCCEEDED" and len(series) == 1
                     and series[0].get("seriesID") == "CIS1010000000000Q"
                     and bool(series[0].get("data")))
        report["api"] = {"http_status": status, "valid_series": valid_api,
                         "payload": payload, **timing}
        print("MACRO_API", json.dumps(report["api"], ensure_ascii=False))
        if valid_api:
            (directory / "eci_api.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except (requests.RequestException, ValueError, RuntimeError):
        valid_api = False
        report["api"] = {"error": "API officielle indisponible"}
    report["ready"] = (usable or valid_api) and len(matches) == 1 and bool(matches[0].get("forecast"))
    (directory / "source_probe.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Contrôle d'intégration du relevé public ; aucune interaction Telegram."""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


def validate(report, require_candidates=False):
    now = datetime.now(timezone.utc)
    fresh_sources = []
    for source in report.get("sources", []):
        try:
            date = datetime.fromisoformat(str(source.get("newest_at", "")).replace("Z", "+00:00"))
        except ValueError:
            continue
        if date.tzinfo is None:
            continue
        if (source.get("primary") and not source.get("probe")
                and source.get("status") in ("ok", "warning")
                and -timedelta(minutes=15) <= now - date.astimezone(timezone.utc) <= timedelta(hours=24)):
            fresh_sources.append(source["source"])
    decisions = report.get("summary", {}).get("decisions", {})
    candidates = decisions.get("dry_run_selected", 0) + decisions.get("queued", 0)
    problems = []
    if not report.get("dry_run"):
        problems.append("Le rapport n'est pas une simulation")
    if len(fresh_sources) < 2:
        problems.append("Moins de deux sources de marchés ont fourni des nouvelles récentes")
    if require_candidates and candidates < 1:
        problems.append("Aucune actualité récente pertinente retrouvée dans ce relevé")
    return {"fresh_market_sources": fresh_sources, "candidates": candidates, "problems": problems}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default="audit/news_audit.json")
    parser.add_argument("--require-candidates", action="store_true")
    args = parser.parse_args()
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    result = validate(report, args.require_candidates)
    print("AUDIT_VALIDATION", json.dumps(result, ensure_ascii=False))
    raise SystemExit(1 if result["problems"] else 0)

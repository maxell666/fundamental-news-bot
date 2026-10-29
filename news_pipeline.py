"""Sélection datée et auditée, indépendante de l'envoi et des secrets Telegram."""

import csv
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from filter import FILTER_VERSION, assess_news, contains_any, normalize_text, _event_clause
from sources import canonicalize_url


def story_key(title):
    title = normalize_text(title)
    title = re.sub(r"\s+[-|]\s+(?:reuters|cnbc|investing\.com|bbc(?: news)?|the guardian)$", "", title)
    title = re.sub(r"[^\w%+.-]+", " ", title).strip()
    return hashlib.sha256(title.encode("utf-8")).hexdigest()


def parse_publication(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if date.tzinfo is None:
        return None
    return date.astimezone(timezone.utc)


def evaluate_news(articles, state, *, now=None, threshold=5, max_age_hours=24,
                  allow_undated=False, assessor=assess_news, title_dedup_hours=24):
    """Toutes les entrées reçoivent une décision, y compris les rejets et doublons."""
    now = now or datetime.now(timezone.utc)
    seen_urls = {canonicalize_url(url) for url in state.get("seen", [])}
    seen_titles = {
        key for key, timestamp in (state.get("seen_titles") or {}).items()
        if (date := parse_publication(timestamp)) is not None
        and timedelta(0) <= now - date <= timedelta(hours=title_dedup_hours)
    } if isinstance(state.get("seen_titles"), dict) else set()
    encountered_urls, encountered_titles = set(), set()
    rows = []
    for original in articles:
        article = dict(original)
        title = " ".join(str(article.get("title") or "").split())
        url = canonicalize_url(article.get("canonical_url") or article.get("url", ""))
        article.update({"title": title, "canonical_url": url})
        assessment = assessor(title, article.get("desc", ""))
        key = story_key(title)
        published = parse_publication(article.get("published_at"))
        row = {
            "title": title, "source": article.get("source", ""),
            "url": article.get("url", ""), "canonical_url": url,
            "published_at": published.isoformat().replace("+00:00", "Z") if published else None,
            "score": assessment.score, "category": getattr(assessment, "category", "FONDAMENTAL"),
            "filter_reason": assessment.reason, "story_key": key,
            "description": re.sub(r"<[^>]+>", " ", str(article.get("desc", "")))[:600],
            "decision": "eligible", "reason": assessment.reason,
            "article": article,
        }
        if not title or not url:
            row.update(decision="invalid", reason="Titre ou URL manquant/invalide")
        elif url in seen_urls or key in seen_titles:
            row.update(decision="seen", reason="Déjà envoyé (URL ou titre identique)")
        elif url in encountered_urls or key in encountered_titles:
            row.update(decision="duplicate", reason="Même article présent dans plusieurs flux")
        elif published is None and not allow_undated:
            row.update(decision="undated", reason="Date de publication absente ou invalide")
        elif published is not None and published > now + timedelta(minutes=15):
            row.update(decision="future", reason="Date de publication future incohérente")
        elif published is not None and now - published > timedelta(hours=max_age_hours):
            row.update(decision="stale", reason=f"Publication de plus de {max_age_hours:g} heures")
        elif not assessment.relevant:
            row.update(decision="rejected", reason=assessment.reason)
        elif assessment.score < threshold:
            row.update(decision="below_threshold", reason=f"Priorité sous le seuil configuré ({threshold})")
        if row["decision"] == "eligible":
            encountered_urls.add(url)
            encountered_titles.add(key)
        rows.append(row)
    return rows


def _number(value):
    return format(Decimal(value.replace(",", ".")).normalize(), "f")


def _independent_monetary_news(title):
    people = ("powell", "warsh", "lagarde", "bailey", "ueda", "macklem", "bullock",
              "breman", "orr", "schlegel", "malhotra")
    banks = ("fed", "fomc", "ecb", "boe", "boj", "boc", "rba", "rbnz", "snb", "rbi",
             "federal reserve", "european central bank", "bank of england", "bank of canada")
    actor = "|".join(re.escape(actor) for actor in people + banks)
    personnel = (r"(?:announces?\s+(?:(?:her|his|an?|the|early|unexpected|immediate)\s+){0,3}"
                 r"(?:exit|departure|resignation)|resigns?|steps? down|"
                 r"(?:(?:is|was|has been|will be|to be)\s+)?(?:fired|appointed|replaced)|"
                 r"appoints?|nominates?|replaces?)")
    return bool(re.search(rf"\b(?:{actor})(?:'s)?\s+"
                          rf"(?:(?:chair|governor|president|chief|head)\s+)?{personnel}\b", title))


def _event_signature(row):
    """Familles bornées et factuelles: aucune similitude générale de titres."""
    title = normalize_text(row["title"])
    title = re.sub(r"\s+[-|]\s+(?:reuters|cnbc|investing\.com|bbc(?: news)?|the guardian)$", "", title)
    primary = _event_clause(title)
    published = parse_publication(row.get("published_at"))
    if published is None:
        return None
    date = published.date().isoformat()
    description = row.get("description") or row.get("article", {}).get("desc", "")
    context = normalize_text(f"{title} {description}")

    if row.get("category") == "MACRO" and row.get("score") == 9:
        if _independent_monetary_news(title):
            # La seconde information (départ/nomination) n'est pas contenue dans
            # un simple titre de décision de taux: elle doit rester visible.
            row["event_note"] = "Annonce distincte sur la direction d'une banque centrale"
            return None
        banks = (
            ("fed", ("fed", "fomc", "federal reserve")),
            ("ecb", ("ecb", "european central bank")),
            ("boe", ("boe", "bank of england")),
            ("boj", ("boj", "bank of japan")),
            ("boc", ("boc", "bank of canada")),
            ("rba", ("rba", "reserve bank of australia")),
            ("rbnz", ("rbnz", "reserve bank of new zealand")),
            ("snb", ("snb", "swiss national bank")),
            ("rbi", ("rbi", "reserve bank of india")),
        )
        bank = next((name for name, aliases in banks if contains_any(primary, aliases)), None)
        if bank is None:
            matches = [name for name, aliases in banks if contains_any(context, aliases)]
            bank = matches[0] if len(matches) == 1 else None
        actions = (
            ("hold", r"\b(?:holds?|held|keeps?|kept|maintains?|maintained|unchanged|on hold)\b"),
            ("raise", r"\b(?:raises?|raised|hikes?|hiked|increases?|increased)\b"),
            ("cut", r"\b(?:cuts?|lowered|lowers?|reduces?|reduced|slashes?|slashed)\b"),
        )
        found = [(match.start(), action) for action, pattern in actions
                 if (match := re.search(pattern, primary))]
        if bank and found:
            action = min(found)[1]
            value = {}
            if match := re.search(r"\b(?:at|to)\s+([-+]?[0-9]+(?:[.,][0-9]+)?)\s*%", primary):
                value["rate"] = _number(match.group(1))
            if match := re.search(r"\bby\s+([0-9]+(?:[.,][0-9]+)?)\s+(?:basis points?|bps?)\b", primary):
                value["change_bps"] = _number(match.group(1))
            elif match := re.search(r"\bby\s+([0-9]+(?:[.,][0-9]+)?)\s*(?:%|percentage points?)", primary):
                value["change_bps"] = _number(str(Decimal(match.group(1).replace(",", ".")) * 100))
            return f"rates:{bank}:{action}:{date}", value

    if row.get("category") == "MACRO":
        quarter = None
        if match := re.search(r"\bq([1-4])\b|\b([1-4])(?:st|nd|rd|th)?[- ]+quarter\b", title):
            quarter = int(match.group(1) or match.group(2))
        else:
            quarter = next((number for word, number in (("first", 1), ("second", 2), ("third", 3), ("fourth", 4))
                            if re.search(rf"\b{word}[- ]+quarter\b", title)), None)
        growth_story = contains_any(title, ("gdp",)) or (
            contains_any(title, ("economy", "growth"))
            and contains_any(title, ("consumer spending", "investment", "consumption"))
        )
        economies = (
            ("us", ("us", "u.s.", "united states", "american")),
            ("uk", ("uk", "united kingdom", "british", "britain")),
            ("eurozone", ("eurozone", "euro area")),
            ("china", ("china", "chinese")), ("japan", ("japan", "japanese")),
            ("canada", ("canada", "canadian")), ("australia", ("australia", "australian")),
        )
        country = next((name for name, aliases in economies if contains_any(primary, aliases)), None)
        if growth_story and quarter and country:
            explicit_year = re.search(r"\b(20[0-9]{2})\b", title)
            year = int(explicit_year.group(1)) if explicit_year else published.year - (quarter == 4 and published.month <= 3)
            value = {}
            gdp = re.search(r"\bgdp\b", title)
            if gdp and (match := re.search(r"([-+]?[0-9]+(?:[.,][0-9]+)?)\s*%", title[gdp.end():])):
                value["growth"] = _number(match.group(1))
            return f"gdp:{country}:{year}:q{quarter}", value

    if row.get("category") == "EQUITIES":
        deal = re.match(
            r"^(?P<buyer>.+?)\s+(?:(?:agrees?|agreed)\s+to\s+|to\s+)?"
            r"(?:buy|buys|bought|acquire|acquires|acquired)\s+(?P<target>.+?)"
            r"(?=\s+(?:for|in|at|valued|worth|under|from|as|after|deal)\b|$)", primary,
        )
        if deal:
            buyer, target = (re.sub(r"[^\w]+", " ", deal.group(field)).strip() for field in ("buyer", "target"))
            if (buyer and target and len(buyer.split()) <= 5 and len(target.split()) <= 5
                    and buyer not in ("it", "the company", "the firm")
                    and target not in ("it", "the company", "the firm")):
                value = {}
                if match := re.search(r"([$€£])\s*([0-9]+(?:[.,][0-9]+)?)\s*(?:bn|billion)\b", title):
                    value = {"amount_billion": _number(match.group(2)), "currency": {"$": "USD", "€": "EUR", "£": "GBP"}[match.group(1)]}
                return f"acquisition:{buyer}:{target}:{date}", value
    return None


def _compatible_values(first, second):
    return all(first[key] == second[key] for key in first.keys() & second.keys())


def _event_key(base, value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return base + "|" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def rank_eligible(rows, seen_events=None, now=None):
    """Garde le représentant prioritaire/récent des mêmes événements connus.

    Les valeurs incompatibles restent des événements distincts. Les cas sans
    signature factuelle restent intacts. Ne modifie jamais l'état persistant.
    """
    now = now or datetime.now(timezone.utc)
    ranked = sorted(
        (row for row in rows if row["decision"] == "eligible"),
        key=lambda row: (row["score"], row["published_at"] or ""), reverse=True,
    )
    families, unrelated = {}, []
    for row in ranked:
        row.update(event_key=None, event_value={}, event_base=None)
        signature = _event_signature(row)
        if signature is None:
            unrelated.append(row)
            continue
        base, value = signature
        families.setdefault(base, []).append((row, value))
    history = []
    if isinstance(seen_events, dict):
        for key, record in seen_events.items():
            if not isinstance(record, dict):
                continue
            sent = parse_publication(record.get("sent_at"))
            if sent is None or not timedelta(0) <= now - sent < timedelta(hours=24):
                continue
            value = record.get("value")
            if isinstance(value, dict):
                history.append((record.get("base") or key.split("|", 1)[0], value))
    representatives = list(unrelated)
    for base, candidates in families.items():
        groups, ambiguous = [], []
        # Les données les plus précises forment les groupes en premier. Une
        # valeur inconnue ne peut pas relier deux décisions contradictoires.
        for row, value in sorted(candidates, key=lambda pair: len(pair[1]), reverse=True):
            if not value and len(groups) > 1:
                # Le titre générique n'ajoute aucune valeur; conserver les
                # décisions chiffrées distinctes sans les fusionner entre elles.
                ambiguous.append(row)
                continue
            matches = [group for group in groups if _compatible_values(group["value"], value)]
            exact = [group for group in matches if group["value"] == value]
            if exact or len(matches) == 1:
                group = exact[0] if exact else matches[0]
                group["members"].append(row)
                group["value"].update(value)
            else:
                groups.append({"value": dict(value), "members": [row]})
        for group in groups:
            value = group["value"]
            members = sorted(group["members"], key=lambda row: (row["score"], row["published_at"] or ""), reverse=True)
            key = _event_key(base, value)
            already_sent = any(
                prior_base == base and _compatible_values(prior_value, value)
                and (not value or (prior_value and all(prior_value.get(field) == data for field, data in value.items())))
                for prior_base, prior_value in history
            )
            for index, row in enumerate(members):
                row.update(event_key=key, event_value=dict(value), event_base=base)
                if already_sent or index:
                    row.update(decision="duplicate_event", reason=(
                        "Même événement déjà envoyé dans les dernières 24 heures" if already_sent
                        else "Même événement économique déjà représenté par un article prioritaire/récent"
                    ))
                else:
                    representatives.append(row)
        for row in ambiguous:
            row.update(event_base=base, decision="duplicate_event",
                       reason="Annonce sans nouvelle valeur déjà couverte par des décisions chiffrées distinctes")
    return sorted(representatives, key=lambda row: (row["score"], row["published_at"] or ""), reverse=True)


def summarize(rows):
    return {
        "articles": len(rows),
        "decisions": dict(Counter(row["decision"] for row in rows)),
        "categories": dict(Counter(row["category"] for row in rows if row["score"] > 0)),
        "rejection_reasons": dict(Counter(row["reason"] for row in rows if row["decision"] in
                                         ("rejected", "below_threshold", "stale", "undated", "future"))),
    }


def write_audit(rows, sources, *, dry_run, directory="audit", error=None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    public_rows = [{key: value for key, value in row.items() if key not in ("article", "story_key")}
                   for row in rows]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "filter_version": FILTER_VERSION, "dry_run": dry_run,
        "summary": summarize(rows), "sources": sources, "items": public_rows,
        "error": error,
    }
    (directory / "news_audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (directory / "source_health.json").write_text(json.dumps(sources, ensure_ascii=False, indent=2), encoding="utf-8")
    fields = ["decision", "score", "category", "source", "published_at", "title", "reason", "filter_reason", "url"]
    with (directory / "news_audit.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in public_rows:
            safe = {field: row.get(field, "") for field in fields}
            for field, value in safe.items():
                if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
                    safe[field] = "'" + value
            writer.writerow(safe)
    return report

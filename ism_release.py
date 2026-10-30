"""Strict, offline reading of an official national ISM Manufacturing report.

The reference month comes from the dated report heading. The release clock
time is supplied by the calendar; no posting timestamp is inferred from HTML.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from html.parser import HTMLParser
import re
from zoneinfo import ZoneInfo

from pmi_release import (
    PMIAnalysis, ReleaseNotReady, ReleaseParseError, _BodyText, _number, _utc,
    analyze_chicago,
)


_MONTHS = ("january", "february", "march", "april", "may", "june", "july",
           "august", "september", "october", "november", "december")
_MONTH_RE = "(?:" + "|".join(_MONTHS) + ")"
_MARK = r"\s*[®™]?\s*"
_NUMBER = r"[+-]?\d+(?:\.\d+)?"
_REPORT_RE = re.compile(
    rf"\b(?P<month>{_MONTH_RE})\s+(?P<year>\d{{4}})\s+ISM{_MARK}"
    rf"Manufacturing\s+PMI{_MARK}Report\b", re.IGNORECASE,
)
_HEADLINE_RE = re.compile(
    rf"\bManufacturing\s+PMI{_MARK}at\s+(?P<actual>{_NUMBER})\s*(?:%|percent)(?!\w)",
    re.IGNORECASE,
)
_NARRATIVE_RE = re.compile(
    rf"\b(?:The\s+)?Manufacturing\s+PMI{_MARK}(?:registered|recorded|was)\s+"
    rf"(?:at\s+)?(?P<actual>{_NUMBER})\s*(?:percent|%)\s+in\s+"
    rf"(?P<month>{_MONTH_RE})(?:\s+(?P<year>\d{{4}}))?\b", re.IGNORECASE,
)
_GLANCE_RE = re.compile(
    rf"\bMANUFACTURING\s+AT\s+A\s+GLANCE\s+(?P<month>{_MONTH_RE})\s+(?P<year>\d{{4}})\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ISMSummary:
    period: str
    actual: Decimal
    source_url: str
    previous: Decimal | None = None
    prices: Decimal | None = None
    new_orders: Decimal | None = None
    employment: Decimal | None = None


@dataclass(frozen=True)
class ISMRelease:
    period: str
    actual: Decimal
    released_at: datetime
    source_url: str
    previous: Decimal | None = None
    prices: Decimal | None = None
    new_orders: Decimal | None = None
    employment: Decimal | None = None
    publication_time_confirmed: bool = False


def _validate_period(period: str) -> tuple[int, int]:
    if not isinstance(period, str) or not re.fullmatch(r"\d{4}-(?:0[1-9]|1[0-2])", period):
        raise ValueError("period must have the form YYYY-MM")
    return int(period[:4]), int(period[5:])


def ism_source_url(period: str) -> str:
    _, month = _validate_period(period)
    return ("https://www.ismworld.org/supply-management-news-and-reports/"
            f"reports/ism-pmi-reports/pmi/{_MONTHS[month - 1]}/")


def _reference(match: re.Match) -> str:
    return f"{match['year']}-{_MONTHS.index(match['month'].lower()) + 1:02d}"


def _level(value: str) -> Decimal:
    if not re.fullmatch(_NUMBER, value.strip()):
        raise ReleaseParseError("Invalid ISM index level")
    result = Decimal(value.strip())
    if not Decimal("0") <= result <= Decimal("100"):
        raise ReleaseParseError("ISM index level outside the 0 to 100 range")
    return result


class _Structure(HTMLParser):
    """Capture headings and table cells without relying on CSS or tag offsets."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.headings: list[str] = []
        self.tables: list[list[list[str]]] = []
        self._heading: list[str] | None = None
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._skip: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"head", "script", "style", "template"}:
            self._skip.append(tag)
        if self._skip:
            return
        if re.fullmatch(r"h[1-6]", tag):
            self._heading = []
        elif tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []
        elif self._heading is not None:
            self._heading.append(" ")
        if self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if self._skip:
            if tag == self._skip[-1]:
                self._skip.pop()
            return
        if re.fullmatch(r"h[1-6]", tag) and self._heading is not None:
            self.headings.append(" ".join("".join(self._heading).split()))
            self._heading = None
        elif tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None and self._table is not None:
            self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            self.tables.append(self._table)
            self._table = None
        elif self._heading is not None:
            self._heading.append(" ")
        if self._cell is not None:
            self._cell.append(" ")

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        if self._heading is not None:
            self._heading.append(data)
        if self._cell is not None:
            self._cell.append(data)


def _table_values(tables: list[list[list[str]]], actual: Decimal) -> dict[str, Decimal | None]:
    fields = {"previous": None, "prices": None, "new_orders": None, "employment": None}
    candidates: list[dict[str, Decimal | None]] = []
    for rows in tables:
        named_rows = {}
        for row in rows:
            if row:
                name = re.sub(r"[®™*]", "", row[0]).strip().lower()
                if name in {"manufacturing pmi", "prices", "new orders", "employment"}:
                    if name in named_rows:
                        raise ReleaseParseError("Duplicate ISM aggregate-table row")
                    named_rows[name] = row
        headline = named_rows.get("manufacturing pmi")
        if not headline or len(headline) < 2:
            continue
        if _level(headline[1]) != actual:
            raise ReleaseParseError("ISM aggregate table and headline disagree")
        values = dict(fields)
        if len(headline) >= 3:
            try:
                values["previous"] = _level(headline[2])
            except ReleaseParseError:
                pass
        for row_name, field in (("prices", "prices"), ("new orders", "new_orders"), ("employment", "employment")):
            row = named_rows.get(row_name)
            if row and len(row) >= 2:
                try:
                    values[field] = _level(row[1])
                except ReleaseParseError:
                    pass
        candidates.append(values)
    if candidates and any(candidate != candidates[0] for candidate in candidates[1:]):
        raise ReleaseParseError("Conflicting ISM aggregate tables")
    return candidates[0] if candidates else fields


def inspect_ism_release(html: str) -> ISMSummary:
    """Read a complete dated report; an empty monthly placeholder is not ready."""
    if not isinstance(html, str):
        raise ReleaseParseError("ISM HTML must be text")
    structure, body = _Structure(), _BodyText()
    try:
        for parser in (structure, body):
            parser.feed(html)
            parser.close()
    except Exception as error:
        raise ReleaseParseError("Cannot parse ISM report HTML") from error
    text = body.text()
    reports = [match for heading in structure.headings for match in _REPORT_RE.finditer(heading)]
    headline_values = {_level(match["actual"]) for heading in structure.headings for match in _HEADLINE_RE.finditer(heading)}
    narratives = list(_NARRATIVE_RE.finditer(text))
    if not reports:
        if headline_values or narratives or any(re.search(r"\bservices\s+pmi", heading, re.IGNORECASE) for heading in structure.headings):
            raise ReleaseParseError("Dated Manufacturing PMI report heading is missing")
        raise ReleaseNotReady("Monthly ISM page has no published Manufacturing report yet")
    periods = {_reference(match) for match in reports}
    if len(periods) != 1:
        raise ReleaseParseError("Conflicting ISM report periods")
    period = periods.pop()
    values = set(headline_values)
    for match in narratives:
        if _MONTHS.index(match["month"].lower()) + 1 != int(period[5:]):
            raise ReleaseParseError("ISM narrative and report month disagree")
        if match["year"] and match["year"] != period[:4]:
            raise ReleaseParseError("ISM narrative and report year disagree")
        values.add(_level(match["actual"]))
    if len(values) != 1:
        raise ReleaseParseError("Manufacturing PMI level is missing or conflicting")
    actual = values.pop()
    for match in _GLANCE_RE.finditer(text):
        if _reference(match) != period:
            raise ReleaseParseError("ISM aggregate-table period and report heading disagree")
    return ISMSummary(period=period, actual=actual, source_url=ism_source_url(period),
                      **_table_values(structure.tables, actual))


def parse_ism_release(html: str, *, expected_period: str, expected_release_at: datetime) -> ISMRelease:
    """Require the exact report month/year, published in the following month."""
    year, month = _validate_period(expected_period)
    scheduled = _utc(expected_release_at, "expected_release_at")
    local = scheduled.astimezone(ZoneInfo("America/New_York"))
    next_month = (year + 1, 1) if month == 12 else (year, month + 1)
    if (local.year, local.month) != next_month:
        raise ValueError("Manufacturing report must be scheduled in the following month")
    summary = inspect_ism_release(html)
    if summary.period < expected_period:
        raise ReleaseNotReady(f"ISM page still shows {summary.period}; waiting for {expected_period}")
    if summary.period > expected_period:
        raise ReleaseParseError("ISM page shows an unexpected future report period")
    return ISMRelease(**summary.__dict__, released_at=scheduled)


def analyze_ism(actual: Decimal, forecast: Decimal | None, previous: Decimal | None) -> PMIAnalysis:
    """Use growth/rates channels, with no regional-PMI or observed-price claim."""
    analysis = analyze_chicago(actual, forecast, previous)
    explanations = {
        "activite_plus_forte": "Activité manufacturière américaine supérieure au consensus.",
        "activite_plus_faible": "Activité manufacturière américaine inférieure au consensus.",
    }
    return replace(analysis, explanation=explanations.get(analysis.classification, analysis.explanation))


def format_ism_test_message(
    release: ISMRelease, forecast: Decimal | None, previous: Decimal | None,
    *, observed_at: datetime, forecast_at: datetime,
) -> str:
    """Plain text; detection is relative to schedule, not actual posting time."""
    scheduled = _utc(release.released_at, "released_at")
    observed, frozen = _utc(observed_at, "observed_at"), _utc(forecast_at, "forecast_at")
    if observed < scheduled:
        raise ValueError("Observation precedes the scheduled release")
    if frozen >= scheduled:
        raise ValueError("Consensus must be frozen before the scheduled release")
    analysis = analyze_ism(release.actual, forecast, previous)
    paris = ZoneInfo("Europe/Paris")
    lines = ["🧪 TEST MACRO — ISM manufacturier États-Unis", f"Période : {release.period}", "",
             "✅ Résultat confirmé sur le rapport officiel ISM",
             f"Publié : {_number(analysis.actual)} points",
             f"Consensus enregistré avant annonce : {_number(analysis.forecast)}" if forecast is not None else "Consensus : indisponible",
             f"Précédent enregistré avant annonce : {_number(analysis.previous)}" if previous is not None else "Précédent : indisponible"]
    if analysis.surprise_points is not None:
        lines.append(f"Surprise : {_number(analysis.surprise_points, signed=True)} point(s) vs consensus")
    if analysis.previous_delta_points is not None:
        lines.append(f"Écart au précédent : {_number(analysis.previous_delta_points, signed=True)} point(s)")
    if release.previous is not None and release.previous != analysis.previous:
        lines.append(f"Précédent figurant dans le rapport : {_number(release.previous)}")
    regime = "expansion" if analysis.actual > 50 else "contraction" if analysis.actual < 50 else "seuil neutre"
    lines.append(f"Secteur manufacturier : {regime} (seuil : 50)")
    for field, label in (("new_orders", "Nouvelles commandes"), ("employment", "Emploi"), ("prices", "Prix payés")):
        value = getattr(release, field)
        if value is not None:
            lines.append(f"{label} : {_number(value)} points")
    lines.extend(["", f"Consensus figé le {frozen.astimezone(paris):%d/%m/%Y à %H:%M:%S} (Paris)",
                  f"Heure prévue au calendrier : {scheduled.astimezone(paris):%d/%m/%Y %H:%M:%S} (Paris)",
                  f"Détecté : {observed.astimezone(paris):%H:%M:%S} (Paris), +{(observed - scheduled).total_seconds():.1f} s après l’heure prévue",
                  "", "🧭 Lecture conditionnelle pour tes marchés", analysis.explanation])
    if analysis.surprise_points:
        lines.extend([f"• EUR/USD ; GBP/USD : {analysis.directions['EURUSD']}",
                      f"• USD/CHF : {analysis.directions['USDCHF']}",
                      f"• GER30 ; SP500 ; NAS100 ; US30 : {analysis.directions['GER30']}"])
    if release.prices is not None:
        lines.append("Les prix payés renseignent les tensions sur les intrants ; sans consensus sur cette composante, leur niveau ne mesure pas une surprise inflationniste.")
    return "\n".join(lines + ["", f"🔗 {release.source_url}"])

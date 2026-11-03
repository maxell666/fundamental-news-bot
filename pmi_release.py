"""Read the public ISM Chicago summary without confusing change and level.

The summary gives a release date but no publication time.  ``released_at`` is
therefore the separately supplied scheduled time, never an observed website
publication timestamp.  This module performs no network requests or sends.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
import re
from zoneinfo import ZoneInfo

from portfolio import TRACKED_ASSETS


CHICAGO_SOURCE_URL = "https://chicago.ismworld.org/news-publications/reports/research-survey/"
_MONTHS = {name.lower(): number for number, name in enumerate(
    ("January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"), 1
)}
_MONTH_RE = "(?:" + "|".join(_MONTHS) + ")"
_NUMBER_RE = r"[+-]?\d+(?:\.\d+)?"
_MOVEMENT_RE = (
    r"rebounded|rose|fell|increased|decreased|dropped|dipped|dips|slipped|declined|climbed|"
    r"jumped|advanced|eased|cooled|tempered|edged(?:\s+(?:up|down|higher|lower))?|"
    r"was\s+(?:up|down)|remained(?:\s+unchanged)?|stood"
)
_LEVEL_RE = re.compile(
    r"\b(?:The\s+)?Chicago\s+Business\s+Barometer\s*(?:[™®]|TM)?\s*,?\s*"
    r"(?:produced\s+with\s+MNI\s*,\s*)?"
    r"(?:"
    rf"(?:{_MOVEMENT_RE})(?:\s+(?:by\s+)?{_NUMBER_RE}\s+points?)?"
    rf"(?:\s+from\s+{_NUMBER_RE})?\s+(?:to|at)"
    r"|(?:registered|recorded|was)(?:\s+at)?"
    r")\s+"
    rf"(?P<actual>{_NUMBER_RE})\s+in\s+(?P<month>{_MONTH_RE})"
    r"(?:\s+(?P<year>\d{4}))?\b",
    re.IGNORECASE,
)
_DATE_RE = re.compile(
    rf"\bReleased\s+(?P<month>{_MONTH_RE})\s+(?P<day>\d{{1,2}}),?\s+(?P<year>\d{{4}})\b",
    re.IGNORECASE,
)


class ReleaseParseError(ValueError):
    """The page cannot safely identify a single Chicago PMI result."""


class ReleaseNotReady(ReleaseParseError):
    """The summary still describes an older release."""


@dataclass(frozen=True)
class ChicagoSummary:
    """Validated page contents, with no inferred release clock time."""

    period: str
    actual: Decimal
    publication_date: date
    source_url: str = CHICAGO_SOURCE_URL


@dataclass(frozen=True)
class PMIRelease:
    period: str
    actual: Decimal
    released_at: datetime
    source_url: str = CHICAGO_SOURCE_URL
    publication_time_confirmed: bool = False
    publication_date: date | None = None


@dataclass(frozen=True)
class PMIAnalysis:
    actual: Decimal
    forecast: Decimal | None
    previous: Decimal | None
    surprise_points: Decimal | None
    previous_delta_points: Decimal | None
    classification: str
    directions: dict[str, str]
    confidence: str
    explanation: str


class _BodyText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skipped: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"head", "script", "style", "template"}:
            self.skipped.append(tag)
        if not self.skipped:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if self.skipped:
            if tag == self.skipped[-1]:
                self.skipped.pop()
        else:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self.skipped:
            self.parts.append(data)

    def text(self) -> str:
        raw = "".join(self.parts).replace("\xa0", " ").replace("\u2212", "-")
        return re.sub(r"\s+", " ", raw).strip()


def _utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def inspect_chicago_release(html: str) -> ChicagoSummary:
    """Inspect a dated headline without treating it as the expected new release.

    For diagnostics only. A caller sending a new-release alert must use
    ``parse_chicago_release`` to enforce the expected period and release date.
    """
    if not isinstance(html, str) or not html.strip():
        raise ReleaseParseError("Empty Chicago summary HTML")
    parser = _BodyText()
    try:
        parser.feed(html)
        parser.close()
    except Exception as error:
        raise ReleaseParseError("Cannot parse Chicago summary HTML") from error
    text = parser.text()
    dates: set[date] = set()
    for match in _DATE_RE.finditer(text):
        try:
            dates.add(date(int(match["year"]), _MONTHS[match["month"].lower()], int(match["day"])))
        except ValueError as error:
            raise ReleaseParseError("Invalid Chicago release date") from error
    if len(dates) != 1:
        raise ReleaseParseError("Chicago release date is missing or ambiguous")
    publication_date = dates.pop()
    period = publication_date.strftime("%Y-%m")
    levels: set[Decimal] = set()
    for match in _LEVEL_RE.finditer(text):
        if _MONTHS[match["month"].lower()] != publication_date.month:
            raise ReleaseParseError("Headline month and explicit release date disagree")
        if match["year"] and int(match["year"]) != publication_date.year:
            raise ReleaseParseError("Headline year and explicit release date disagree")
        actual = Decimal(match["actual"])
        if not Decimal("0") <= actual <= Decimal("100"):
            raise ReleaseParseError("Chicago PMI level is outside the 0 to 100 index range")
        levels.add(actual)
    if len(levels) != 1:
        raise ReleaseParseError("Chicago headline level is missing or ambiguous")
    return ChicagoSummary(period=period, actual=levels.pop(), publication_date=publication_date)


def parse_chicago_release(
    html: str,
    *,
    expected_period: str = "2026-10",
    expected_release_at: datetime,
) -> PMIRelease:
    """Require a headline level and a consistent explicit 'Released' date.

    Only the Chicago Business Barometer headline is parsed: point changes,
    subindices and the neutral 50 threshold cannot become the reported level.
    Older releases raise ``ReleaseNotReady``; future or ambiguous content raises
    ``ReleaseParseError``.  No website publication time is inferred from HTML.
    """
    if not isinstance(expected_period, str) or not re.fullmatch(r"\d{4}-(?:0[1-9]|1[0-2])", expected_period):
        raise ValueError("expected_period must have the form YYYY-MM")
    scheduled_at = _utc(expected_release_at, "expected_release_at")
    scheduled_date = scheduled_at.astimezone(ZoneInfo("America/New_York")).date()
    if scheduled_date.strftime("%Y-%m") != expected_period:
        raise ValueError("Expected period and scheduled release month disagree")
    summary = inspect_chicago_release(html)
    if summary.period > expected_period or summary.publication_date > scheduled_date:
        raise ReleaseParseError("Chicago summary describes an unexpected future release")
    if summary.period < expected_period or summary.publication_date < scheduled_date:
        raise ReleaseNotReady(f"Chicago summary still shows {summary.publication_date.isoformat()}")
    return PMIRelease(
        period=summary.period,
        actual=summary.actual,
        released_at=scheduled_at,
        publication_date=summary.publication_date,
    )


def _decimal(value: Decimal | str | int, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (Decimal, str, int)):
        raise TypeError(f"{field} must be Decimal, a decimal string or an integer")
    try:
        result = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"Invalid decimal {field}") from error
    if not result.is_finite() or not Decimal("0") <= result <= Decimal("100"):
        raise ValueError(f"{field} must be a finite index level between 0 and 100")
    return result


def analyze_chicago(
    actual: Decimal,
    forecast: Decimal | None,
    previous: Decimal | None,
) -> PMIAnalysis:
    """Explain an activity surprise for the seven tracked instruments.

    This regional survey is an input to growth and rates expectations, not a
    measurement of FX or index prices. The previous level is context only.
    """
    actual = _decimal(actual, "actual")
    forecast = _decimal(forecast, "forecast") if forecast is not None else None
    previous = _decimal(previous, "previous") if previous is not None else None
    surprise = actual - forecast if forecast is not None else None
    previous_delta = actual - previous if previous is not None else None
    if surprise is None:
        classification = "consensus_absent"
        confidence = "faible"
        explanation = "Consensus indisponible : aucune surprise calculée ni direction déduite pour les paires ou les indices. Le précédent ne remplace pas le consensus."
        pair = chf = equity = "aucune direction déduite sans consensus"
    elif surprise > 0:
        classification = "activite_plus_forte"
        confidence = "modérée"
        explanation = "Activité régionale supérieure au consensus."
        pair = (
            "baisse possible si cette surprise relève les taux américains attendus "
            "par rapport aux taux européens et britanniques, ce qui soutiendrait le dollar."
        )
        chf = (
            "hausse possible si le différentiel de taux favorise le dollar face au franc ; "
            "un renforcement du franc lié aux flux refuges peut contrarier ce canal."
        )
        equity = (
            "lecture mixte : une activité plus forte peut soutenir les bénéfices, "
            "mais une hausse des taux attendus augmente le coût d’actualisation."
        )
    elif surprise < 0:
        classification = "activite_plus_faible"
        confidence = "modérée"
        explanation = "Activité régionale inférieure au consensus."
        pair = (
            "hausse possible si cette surprise abaisse les taux américains attendus "
            "par rapport aux taux européens et britanniques, ce qui pèserait sur le dollar."
        )
        chf = (
            "baisse possible si le différentiel de taux défavorise le dollar face au franc ; "
            "la réaction propre du franc et les flux refuges peuvent modifier ce canal."
        )
        equity = (
            "lecture mixte : une détente des taux peut soutenir les valorisations, "
            "mais une activité plus faible peut peser sur les bénéfices."
        )
    else:
        classification = "conforme"
        confidence = "faible"
        explanation = "Chiffre conforme au consensus : aucune surprise d’activité identifiée pour orienter les paires ou les indices. L’écart au précédent ne constitue pas une surprise."
        pair = chf = equity = "aucune direction déduite d’un chiffre conforme au consensus"
    mechanisms = {"EURUSD": pair, "GBPUSD": pair, "USDCHF": chf,
                  "GER30": equity, "SP500": equity, "NAS100": equity, "US30": equity}
    if surprise:
        mechanisms["GER30"] += " Pour GER30, la transmission est plus indirecte, via la demande mondiale et les taux."
    return PMIAnalysis(
        actual=actual, forecast=forecast, previous=previous,
        surprise_points=surprise, previous_delta_points=previous_delta,
        classification=classification,
        directions={asset: mechanisms[asset] for asset in TRACKED_ASSETS},
        confidence=confidence, explanation=explanation,
    )


def _number(value: Decimal, *, signed: bool = False) -> str:
    prefix = "+" if signed and value > 0 else ""
    return prefix + format(value, "f").replace(".", ",")


def _display_points(value: Decimal) -> str:
    text = _number(value)
    return text if "," in text else text + ",0"


def _format_pmi_result(
    *, title: str, period: str, source_url: str, analysis: PMIAnalysis,
    scheduled_at: datetime, observed_at: datetime, forecast_at: datetime,
    regional: bool = False, report_previous: Decimal | None = None,
    components: tuple[tuple[str, Decimal], ...] = (),
) -> str:
    """Shared mobile presentation; prices and rates remain conditional.

    The footer measures detection from the scheduled release, not the source's
    actual posting time or Telegram delivery. Exact timestamps stay in audits.
    """
    scheduled = _utc(scheduled_at, "released_at")
    observed, frozen = _utc(observed_at, "observed_at"), _utc(forecast_at, "forecast_at")
    if observed < scheduled:
        raise ValueError("Observation precedes the scheduled release")
    if frozen >= scheduled:
        raise ValueError("Consensus must be frozen before the scheduled release")
    if not isinstance(period, str) or not re.fullmatch(r"\d{4}-(?:0[1-9]|1[0-2])", period):
        raise ValueError("period must have the form YYYY-MM")
    months = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet",
              "août", "septembre", "octobre", "novembre", "décembre")
    label = f"{months[int(period[5:]) - 1]} {period[:4]}"
    subject = "Activité de Chicago" if regional else "Industrie américaine"
    conclusions = {
        "activite_plus_forte": f"{subject} plus forte qu’attendu.",
        "activite_plus_faible": f"{subject} plus faible qu’attendu.",
        "conforme": f"{subject} conforme aux attentes.",
        "consensus_absent": "Attentes indisponibles : comparaison impossible.",
    }
    lines = [f"🧪 TEST MACRO — {title} · {label}", conclusions[analysis.classification]]
    if regional:
        lines.append("Enquête régionale : portée limitée.")
    lines.extend([
        "",
        f"Publié : {_display_points(analysis.actual)} pts",
        f"Attendu : {_display_points(analysis.forecast)} pts" if analysis.forecast is not None else "Attendu : indisponible",
        f"Précédent : {_display_points(analysis.previous)} pts" if analysis.previous is not None else "Précédent : indisponible",
    ])
    if analysis.surprise_points is not None:
        surprise = _display_points(analysis.surprise_points)
        if analysis.surprise_points > 0:
            surprise = "+" + surprise
        unit = "point" if abs(analysis.surprise_points) <= 1 else "points"
        lines.append(f"Surprise : {surprise} {unit}")
    if report_previous is not None and report_previous != analysis.previous:
        lines.append(f"Précédent du rapport : {_display_points(report_previous)} pts")

    if analysis.surprise_points:
        stronger = analysis.surprise_points > 0
        pair_arrow, chf_arrow = ("↓", "↑") if stronger else ("↑", "↓")
        rate_move = "montent" if stronger else "baissent"
        lines.extend([
            "", "🎯 Scénarios possibles",
            f"Si les taux US attendus {rate_move} par rapport aux taux européens, britanniques et suisses :",
            f"• EUR/USD {pair_arrow} POSSIBLE",
            f"• GBP/USD {pair_arrow} POSSIBLE",
            f"• USD/CHF {chf_arrow} POSSIBLE",
            "Le rôle de refuge du franc peut modifier le sens de USD/CHF.",
            "",
            "SP500 / NAS100 / US30 : MIXTE",
            ("L’activité peut soutenir les bénéfices ; si les taux montent, pression possible, surtout sur NAS100."
             if stronger else
             "L’activité peut peser sur les bénéfices ; si les taux baissent, soutien possible, surtout pour NAS100."),
            "GER30 : MIXTE — effets indirects via l’activité mondiale et les taux.",
        ])
    else:
        lines.extend(["", "Marchés : aucun sens déduit de ce chiffre seul."])

    regime = "expansion" if analysis.actual > 50 else "contraction" if analysis.actual < 50 else "seuil neutre"
    lines.extend(["", f"Contexte : {regime} (seuil : 50)."])
    if components:
        lines.append(" • ".join(f"{name} : {_display_points(value)} pts" for name, value in components))
        if any(name == "Prix payés" for name, _ in components):
            lines.append("Prix payés : pas de surprise déduite sans attentes comparables.")
    paris = ZoneInfo("Europe/Paris")
    delay = f"{(observed - scheduled).total_seconds():.1f}".replace(".", ",")
    lines.extend([
        "",
        f"Prévu : {scheduled.astimezone(paris):%d/%m %H:%M} Paris • détecté : {observed.astimezone(paris):%H:%M:%S} (+{delay} s)",
        "Attentes enregistrées avant annonce." if analysis.forecast is not None else "Attentes indisponibles avant annonce.",
        f"🔗 {source_url}",
    ])
    return "\n".join(lines)


def format_chicago_test_message(
    release: PMIRelease,
    forecast: Decimal | None,
    previous: Decimal | None,
    *,
    observed_at: datetime,
    forecast_at: datetime,
) -> str:
    """Format a frozen-consensus comparison with conditional market channels.

    Detection delay is measured from the calendar's scheduled release time.
    The public summary supplies no posting timestamp, so this does not measure
    its actual publication latency or the time Telegram takes to deliver.
    """
    analysis = analyze_chicago(release.actual, forecast, previous)
    return _format_pmi_result(title="Chicago PMI", period=release.period,
                              source_url=release.source_url, analysis=analysis,
                              scheduled_at=release.released_at, observed_at=observed_at,
                              forecast_at=forecast_at, regional=True)

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import unittest

from pmi_release import (
    ReleaseNotReady, ReleaseParseError, analyze_chicago,
    format_chicago_test_message, inspect_chicago_release, parse_chicago_release,
)


SCHEDULED = datetime(2026, 10, 30, 13, 45, tzinfo=timezone.utc)


def summary(month="October", day=30, year=2026, value="54.6", change="2.3"):
    # Synthetic, deliberately not a stored copy of the copyrighted report.
    return (
        "<html><head><script>Chicago Business Barometer rose to 99.9 in December. "
        "Released December 31, 2099.</script></head><body>"
        f"<p>The Chicago Business Barometer™, rose {change} points to {value} in {month}.</p>"
        "<p>The neutral threshold is 50. New Orders moved to 61.5.</p>"
        f"<p>Released {month} {day}, {year}.</p><footer>Copyright 2099</footer></body></html>"
    )


def parse(html, **kwargs):
    return parse_chicago_release(html, expected_release_at=SCHEDULED, **kwargs)


class ChicagoParseTests(unittest.TestCase):
    def test_level_is_not_point_change_neutral_threshold_or_subindex(self):
        release = parse(summary())
        self.assertEqual(release.actual, Decimal("54.6"))
        self.assertEqual(release.period, "2026-10")
        self.assertEqual(release.publication_date, date(2026, 10, 30))
        self.assertEqual(release.released_at, SCHEDULED)
        self.assertFalse(release.publication_time_confirmed)

    def test_old_month_is_not_ready(self):
        with self.assertRaises(ReleaseNotReady):
            parse(summary(month="September"))

    def test_diagnostic_can_inspect_old_level_without_inventing_a_clock_time(self):
        html = summary(month="September", value="57.2")
        inspected = inspect_chicago_release(html)
        self.assertEqual(inspected.period, "2026-09")
        self.assertEqual(inspected.actual, Decimal("57.2"))
        self.assertEqual(inspected.publication_date, date(2026, 9, 30))
        self.assertFalse(hasattr(inspected, "released_at"))
        with self.assertRaises(ReleaseNotReady):
            parse(html)

    def test_diagnostic_preserves_the_same_ambiguity_checks(self):
        conflict = "<p>The Chicago Business Barometer fell to 53.2 in October.</p>"
        with self.assertRaises(ReleaseParseError):
            inspect_chicago_release(summary().replace("</body>", conflict + "</body>"))

    def test_old_release_day_is_not_ready(self):
        with self.assertRaises(ReleaseNotReady):
            parse(summary(day=29))

    def test_future_period_is_rejected(self):
        with self.assertRaises(ReleaseParseError) as error:
            parse(summary(month="November"))
        self.assertNotIsInstance(error.exception, ReleaseNotReady)

    def test_future_release_day_is_rejected(self):
        with self.assertRaises(ReleaseParseError):
            parse(summary(day=31))

    def test_year_comes_from_released_date_not_footer(self):
        with self.assertRaises(ReleaseNotReady):
            parse(summary(year=2025))

    def test_headline_and_release_month_must_agree(self):
        with self.assertRaises(ReleaseParseError):
            parse(summary().replace("in October.", "in September."))

    def test_explicit_headline_year_must_agree(self):
        with self.assertRaises(ReleaseParseError):
            parse(summary().replace("in October.", "in October 2025."))

    def test_release_date_is_required(self):
        with self.assertRaises(ReleaseParseError):
            parse(summary().replace("Released October 30, 2026.", "Updated today."))

    def test_release_date_must_be_valid(self):
        with self.assertRaises(ReleaseParseError):
            parse(summary(day=99))

    def test_conflicting_dates_are_rejected(self):
        with self.assertRaises(ReleaseParseError):
            parse(summary().replace("</body>", "<p>Released October 29, 2026.</p></body>"))

    def test_conflicting_levels_are_rejected(self):
        conflict = "<p>The Chicago Business Barometer fell to 53.2 in October.</p>"
        with self.assertRaises(ReleaseParseError):
            parse(summary().replace("</body>", conflict + "</body>"))

    def test_duplicate_identical_summary_is_not_ambiguous(self):
        self.assertEqual(parse(summary() + summary()).actual, Decimal("54.6"))

    def test_supported_movement_words(self):
        for movement in ("rebounded", "fell", "decreased", "declined", "edged lower"):
            with self.subTest(movement=movement):
                self.assertEqual(parse(summary().replace("rose 2.3", movement + " 2.3")).actual, Decimal("54.6"))

    def test_change_from_previous_does_not_become_level(self):
        html = summary().replace("rose 2.3 points to", "increased by 2.3 points from 52.3 to")
        self.assertEqual(parse(html).actual, Decimal("54.6"))

    def test_stood_at_format_is_supported(self):
        html = summary().replace("rose 2.3 points to", "stood at")
        self.assertEqual(parse(html).actual, Decimal("54.6"))

    def test_producer_clause_tm_suffix_and_cooling_verbs_keep_the_actual_level(self):
        for suffix, movement in (("TM", "cooled"), ("™", "tempered")):
            with self.subTest(suffix=suffix, movement=movement):
                html = summary().replace(
                    "Barometer™, rose 2.3 points to", 
                    f"Barometer{suffix}, produced with MNI, {movement} 6.0 points to",
                )
                self.assertEqual(parse(html).actual, Decimal("54.6"))
                with self.assertRaises(ReleaseParseError):
                    parse(html.replace("in October.", "in September."))

    def test_registered_level_without_change_is_supported(self):
        html = summary().replace("rose 2.3 points to", "registered")
        self.assertEqual(parse(html).actual, Decimal("54.6"))

    def test_html_inline_markup_and_nonbreaking_spaces_are_supported(self):
        html = summary().replace("Barometer™", "Barometer<sup>&trade;</sup>").replace("54.6 in", "<b>54.6</b>&nbsp;in")
        self.assertEqual(parse(html).actual, Decimal("54.6"))

    def test_invalid_currency_percent_and_out_of_range_levels_are_rejected(self):
        for value in ("$54.6", "54.6%", "-1.0", "101.0", "NaN"):
            with self.subTest(value=value):
                with self.assertRaises(ReleaseParseError):
                    parse(summary(value=value))

    def test_missing_headline_does_not_fall_back_to_other_numbers(self):
        with self.assertRaises(ReleaseParseError):
            parse(summary().replace("Chicago Business Barometer™, rose", "New Orders rose"))

    def test_expected_timestamp_must_be_aware_and_in_the_expected_month(self):
        for value in (SCHEDULED.replace(tzinfo=None), SCHEDULED - timedelta(days=40)):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_chicago_release(summary(), expected_release_at=value)


class ChicagoAnalysisTests(unittest.TestCase):
    def test_stronger_activity_is_not_an_automatic_equity_sell_signal(self):
        analysis = analyze_chicago(Decimal("54.6"), Decimal("54.5"), Decimal("52.3"))
        self.assertEqual(analysis.surprise_points, Decimal("0.1"))
        self.assertEqual(analysis.previous_delta_points, Decimal("2.3"))
        self.assertEqual(analysis.classification, "activite_plus_forte")
        self.assertIn("soutien possible", analysis.directions["USD"])
        self.assertIn("pression possible", analysis.directions["XAUUSD"])
        for asset in ("NAS100", "SPX500", "US30"):
            self.assertIn("mixte", analysis.directions[asset])

    def test_weaker_activity_keeps_equity_interpretation_mixed(self):
        analysis = analyze_chicago(Decimal("48.4"), Decimal("50.0"), Decimal("47.0"))
        self.assertEqual(analysis.classification, "activite_plus_faible")
        self.assertEqual(analysis.surprise_points, Decimal("-1.6"))
        self.assertEqual(analysis.previous_delta_points, Decimal("1.4"))
        self.assertIn("pression possible", analysis.directions["USD"])
        self.assertIn("mixte", analysis.directions["NAS100"])

    def test_on_consensus_and_missing_forecast_do_not_invent_direction(self):
        for forecast, classification in ((Decimal("54.6"), "conforme"), (None, "consensus_absent")):
            with self.subTest(forecast=forecast):
                analysis = analyze_chicago(Decimal("54.6"), forecast, Decimal("50.0"))
                self.assertEqual(analysis.classification, classification)
                self.assertNotIn("soutien possible", analysis.directions["USD"])

    def test_float_and_nonfinite_consensus_are_rejected(self):
        with self.assertRaises(TypeError):
            analyze_chicago(54.6, Decimal("54.5"), None)
        with self.assertRaises(ValueError):
            analyze_chicago(Decimal("54.6"), Decimal("NaN"), None)

    def test_message_is_a_latency_test_with_conditional_equity_reading(self):
        release = parse(summary())
        text = format_chicago_test_message(
            release, Decimal("54.5"), Decimal("52.3"),
            observed_at=SCHEDULED + timedelta(seconds=5),
            forecast_at=SCHEDULED - timedelta(hours=2),
        )
        self.assertIn("TEST MACRO", text)
        self.assertIn("+0,1 point(s)", text)
        self.assertIn("14:45:00 (Paris)", text)
        self.assertIn("+5.0 s après l’heure prévue", text)
        self.assertIn("délai inconnu", text.lower().replace(" : ", " "))
        self.assertIn("ne fournit pas l’heure effective", text)
        self.assertIn("Lecture conditionnelle", text)
        self.assertIn("NAS100 : mixte", text)
        self.assertNotIn("Heure effective :", text)

    def test_message_rejects_late_consensus_or_premature_observation(self):
        release = parse(summary())
        for observed, frozen in ((SCHEDULED - timedelta(seconds=1), SCHEDULED - timedelta(hours=1)),
                                 (SCHEDULED + timedelta(seconds=1), SCHEDULED)):
            with self.subTest(observed=observed, frozen=frozen):
                with self.assertRaises(ValueError):
                    format_chicago_test_message(release, Decimal("54.5"), None,
                                                observed_at=observed, forecast_at=frozen)


if __name__ == "__main__":
    unittest.main()

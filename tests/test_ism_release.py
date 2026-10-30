from datetime import datetime, timedelta, timezone
from decimal import Decimal
import unittest

from ism_release import (
    ReleaseNotReady, ReleaseParseError, analyze_ism, format_ism_test_message,
    inspect_ism_release, ism_source_url, parse_ism_release,
)
from portfolio import TRACKED_ASSETS


SCHEDULED = datetime(2026, 11, 2, 15, 0, tzinfo=timezone.utc)


def report(month="October", year=2026, actual="55.1", previous="54.5", table=True):
    # Small synthetic report structure; no full copyrighted release is stored.
    rows = (f"<h3>MANUFACTURING AT A GLANCE</h3><p>{month} {year}</p><table>"
            "<tr><th>Index</th><th>Series Index Oct</th><th>Series Index Sep</th></tr>"
            f"<tr><td>Manufacturing PMI<sup>®</sup></td><td>{actual}</td><td>{previous}</td></tr>"
            "<tr><td>New Orders</td><td>56.2</td><td>55.3</td></tr>"
            "<tr><td>Employment</td><td>51.8</td><td>52.7</td></tr>"
            "<tr><td>Prices</td><td>76.4</td><td>77.9</td></tr></table>") if table else ""
    return ("<html><head><title>Report September 2099</title><script>Manufacturing PMI at 99.9%</script></head><body>"
            f"<h1>Manufacturing PMI<sup>®</sup> at {actual}%</h1>"
            f"<h1>{month} {year} ISM<sup>®</sup> Manufacturing PMI<sup>®</sup> Report</h1>"
            f"<p>The Manufacturing PMI<sup>®</sup> registered {actual} percent in {month}, "
            "a change of 0.6 percentage point. New Orders registered 56.2 percent.</p>"
            + rows + "<footer>The next report will feature November 2026 data. Copyright 2099.</footer></body></html>")


def parse(html, **kwargs):
    return parse_ism_release(html, expected_period="2026-10", expected_release_at=SCHEDULED, **kwargs)


class ISMParserTests(unittest.TestCase):
    def test_heading_year_main_level_and_table_components_are_identified(self):
        result = parse(report())
        self.assertEqual(result.period, "2026-10")
        self.assertEqual(result.actual, Decimal("55.1"))
        self.assertEqual(result.previous, Decimal("54.5"))
        self.assertEqual(result.new_orders, Decimal("56.2"))
        self.assertEqual(result.prices, Decimal("76.4"))
        self.assertEqual(result.employment, Decimal("51.8"))
        self.assertEqual(result.released_at, SCHEDULED)
        self.assertFalse(result.publication_time_confirmed)
        self.assertTrue(result.source_url.endswith("/pmi/october/"))

    def test_old_month_and_same_month_old_year_are_not_ready(self):
        for html in (report(month="September"), report(year=2025)):
            with self.subTest(html=html[:40]):
                with self.assertRaises(ReleaseNotReady):
                    parse(html)

    def test_future_reference_period_is_malformed_not_ready(self):
        with self.assertRaises(ReleaseParseError) as error:
            parse(report(month="November"))
        self.assertNotIsInstance(error.exception, ReleaseNotReady)

    def test_empty_monthly_placeholder_is_not_ready(self):
        for html in ("", "<html><h1>October</h1><p>Subscribe for news.</p></html>"):
            with self.subTest(html=html):
                with self.assertRaises(ReleaseNotReady):
                    parse(html)

    def test_services_report_cannot_be_manufacturing(self):
        with self.assertRaises(ReleaseParseError) as error:
            parse(report().replace("Manufacturing", "Services"))
        self.assertNotIsInstance(error.exception, ReleaseNotReady)

    def test_report_year_is_mandatory_and_not_read_from_footer(self):
        with self.assertRaises(ReleaseParseError):
            parse(report().replace("October 2026 ISM", "October ISM"))

    def test_new_orders_and_neutral_threshold_cannot_replace_main_level(self):
        html = report(table=False).replace("Manufacturing PMI<sup>®</sup> at 55.1%", "New Orders at 56.2%")
        html = html.replace("The Manufacturing PMI<sup>®</sup> registered 55.1 percent in October", "Manufacturing expansion threshold is 50")
        with self.assertRaises(ReleaseParseError):
            parse(html)

    def test_headline_and_independent_narrative_must_agree(self):
        with self.assertRaises(ReleaseParseError):
            parse(report().replace("registered 55.1 percent in October", "registered 54.9 percent in October"))

    def test_narrative_month_and_explicit_year_must_match_heading(self):
        for replacement in ("registered 55.1 percent in September", "registered 55.1 percent in October 2025"):
            with self.subTest(replacement=replacement):
                with self.assertRaises(ReleaseParseError):
                    parse(report().replace("registered 55.1 percent in October", replacement))

    def test_conflicting_report_headings_are_rejected(self):
        extra = "<h1>September 2026 ISM Manufacturing PMI Report</h1>"
        with self.assertRaises(ReleaseParseError):
            parse(report().replace("</body>", extra + "</body>"))

    def test_main_table_cannot_disagree_or_belong_to_another_period(self):
        for html in (report().replace("<td>55.1</td>", "<td>54.0</td>"),
                     report().replace("GLANCE</h3><p>October 2026", "GLANCE</h3><p>September 2026")):
            with self.subTest(html=html[:40]):
                with self.assertRaises(ReleaseParseError):
                    parse(html)

    def test_optional_table_fields_are_absent_without_a_verified_table(self):
        result = parse(report(table=False))
        self.assertIsNone(result.previous)
        self.assertIsNone(result.prices)
        self.assertIsNone(result.new_orders)
        self.assertIsNone(result.employment)

    def test_html_registered_marks_and_entities_are_supported(self):
        html = report().replace("<sup>®</sup>", "&reg;").replace("55.1 percent", "<b>55.1</b>&nbsp;percent")
        self.assertEqual(parse(html).actual, Decimal("55.1"))

    def test_invalid_values_are_rejected(self):
        for value in ("101.0", "-1.0", "$55.1", "NaN"):
            with self.subTest(value=value):
                with self.assertRaises(ReleaseParseError):
                    parse(report(actual=value))

    def test_schedule_requires_following_month_and_timezone(self):
        for scheduled in (SCHEDULED.replace(tzinfo=None), SCHEDULED - timedelta(days=10)):
            with self.subTest(scheduled=scheduled):
                with self.assertRaises(ValueError):
                    parse_ism_release(report(), expected_period="2026-10", expected_release_at=scheduled)

    def test_december_report_rolls_to_january_and_url_is_fixed(self):
        release = parse_ism_release(report(month="December"), expected_period="2026-12",
                                    expected_release_at=datetime(2027, 1, 4, 15, 0, tzinfo=timezone.utc))
        self.assertEqual(release.period, "2026-12")
        self.assertTrue(ism_source_url("2026-12").endswith("/december/"))
        with self.assertRaises(ValueError):
            ism_source_url("https://untrusted.example")

    def test_diagnostic_reads_old_report_without_inventing_publication_time(self):
        result = inspect_ism_release(report(month="September"))
        self.assertEqual(result.period, "2026-09")
        self.assertFalse(hasattr(result, "released_at"))


class ISMMessageTests(unittest.TestCase):
    def test_growth_analysis_preserves_decimal_surprise_and_only_the_seven_assets(self):
        analysis = analyze_ism(Decimal("55.1"), Decimal("55.0"), Decimal("55.1"))
        self.assertEqual(analysis.surprise_points, Decimal("0.1"))
        self.assertEqual(analysis.previous_delta_points, Decimal("0.0"))
        self.assertEqual(tuple(analysis.directions), TRACKED_ASSETS)
        self.assertIn("baisse possible", analysis.directions["EURUSD"])
        self.assertIn("hausse possible", analysis.directions["USDCHF"])
        self.assertIn("mixte", analysis.directions["SP500"])
        self.assertNotIn("régional", analysis.explanation)

    def test_message_includes_actual_forecast_components_and_honest_schedule_delay(self):
        text = format_ism_test_message(parse(report()), Decimal("55.0"), Decimal("54.5"),
                                       observed_at=SCHEDULED + timedelta(seconds=4),
                                       forecast_at=SCHEDULED - timedelta(hours=1))
        for part in ("Publié : 55,1", "Surprise : +0,1", "Nouvelles commandes : 56,2", "Prix payés : 76,4",
                     "Heure prévue au calendrier : 02/11/2026 16:00:00", "Détecté : 16:00:04", "+4.0 s après l’heure prévue",
                     "EUR/USD ; GBP/USD : baisse possible", "USD/CHF : hausse possible", "GER30 ; SP500 ; NAS100 ; US30 : lecture mixte"):
            self.assertIn(part, text)
        for absent in ("Chicago", "régional", "XAUUSD", "SPX500", "confiance", "hausse observée", "Heure effective"):
            self.assertNotIn(absent, text)

    def test_missing_forecast_does_not_invent_surprise_from_previous_or_prices(self):
        text = format_ism_test_message(parse(report()), None, Decimal("54.5"),
                                       observed_at=SCHEDULED + timedelta(seconds=2),
                                       forecast_at=SCHEDULED - timedelta(hours=1))
        self.assertNotIn("Surprise :", text)
        self.assertNotIn("hausse possible", text)
        self.assertNotIn("baisse possible", text)
        self.assertIn("sans consensus sur cette composante", text)

    def test_late_consensus_or_observation_before_schedule_are_rejected(self):
        for observed, frozen in ((SCHEDULED, SCHEDULED), (SCHEDULED - timedelta(seconds=1), SCHEDULED - timedelta(hours=1))):
            with self.subTest(observed=observed, frozen=frozen):
                with self.assertRaises(ValueError):
                    format_ism_test_message(parse(report()), Decimal("55.0"), Decimal("54.5"),
                                            observed_at=observed, forecast_at=frozen)


if __name__ == "__main__":
    unittest.main()

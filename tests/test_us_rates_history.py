"""US rates: chronology, definitions, country, audit and snapshot safety."""

from decimal import Decimal
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import macro_us_rates as rates
from macro_catalog import TOPICS, topic_series
from macro_common import observation
from macro_render import document, load_topic, payload
from sync_macro import merge, validate


def csv(ident, lines):
    return (f"observation_date,{ident}\n" + "\n".join(lines) + "\n").encode()


class USRateParsing(unittest.TestCase):
    def test_missing_holiday_is_not_zero_and_negative_yield_survives(self):
        raw = csv("DFII10", ["2020-01-01,", "2020-01-02,-0.25", "2020-01-03,0"])
        values, detail = rates.parse_csv(raw, "DFII10", "D")
        self.assertEqual(values, {"2020-01-02": Decimal("-0.25"), "2020-01-03": Decimal(0)})
        self.assertEqual(detail["missing_observations"], 1)

    def test_identity_order_calendar_and_window_are_checked(self):
        cases = [b"observation_date,WRONG\n2020-01-01,1\n",
                 csv("DFF", ["2020-01-01,1", "2020-01-01,2"]),
                 csv("DFF", ["2020-01-01,1", "2020-01-03,2"]),
                 csv("DFF", ["2020-02-30,1"]),
                 csv("DFF", ["9999-01-01,1"]),
                 csv("DFF", ["2020-01-01,NaN"])]
        for raw in cases:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                rates.parse_csv(raw, "DFF", "D")
        with self.assertRaisesRegex(ValueError, "outside requested"):
            rates.parse_csv(csv("DFF", ["2020-01-01,1"]), "DFF", "D", "2020-01-02", "2020-01-03")

    def test_business_day_grid_differs_from_calendar_grid(self):
        lines = ["2020-01-03,1", "2020-01-06,2"]
        self.assertEqual(len(rates.parse_csv(csv("DGS2", lines), "DGS2", "D")[0]), 2)
        with self.assertRaisesRegex(ValueError, "missing source calendar"):
            rates.parse_csv(csv("DFF", lines), "DFF", "D")

    def test_monthly_dates_are_not_daily_values(self):
        values, _ = rates.parse_csv(csv("GS10", ["1953-04-01,2.83", "1953-05-01,3.05"]), "GS10", "M")
        self.assertEqual(list(values), ["1953-04", "1953-05"])
        for lines in (["1953-04-02,2"], ["1953-04-01,2", "1953-06-01,3"]):
            with self.assertRaises(ValueError):
                rates.parse_csv(csv("GS10", lines), "GS10", "M")

    def test_split_window_audit_rejects_inconsistent_history(self):
        full = {"1954-07-01": Decimal("1.13"), "2026-10-01": Decimal("3.5")}
        replies = [csv("DFF", ["1954-07-01,1.13"]), csv("DFF", ["2026-10-01,3.5"])]
        with patch.object(rates, "fetch", side_effect=replies):
            self.assertEqual(len(rates.split_audit("DFF", "D", full)), 2)
        with patch.object(rates, "fetch", side_effect=[replies[0], csv("DFF", ["2026-10-01,4.5"])]):
            with self.assertRaisesRegex(ValueError, "differs from split"):
                rates.split_audit("DFF", "D", full)

    def test_known_spread_exceptions_are_exact_and_later_reference_is_not_input(self):
        computed = {"1990-11-21": Decimal("0.72"), "2020-01-01": Decimal("-0.5")}
        reference = {"1990-11-21": Decimal("0.74"), "2020-01-01": Decimal("-0.5"), "2020-01-02": Decimal("-0.4")}
        audit = rates.audit_spread(computed, reference, "T10Y2Y")
        self.assertEqual(audit["audited_common_dates"], 2)
        self.assertEqual(audit["reference_only_dates"], 1)
        self.assertEqual(len(audit["reference_differences"]), 1)
        self.assertNotIn("2020-01-02", computed)
        for stamp in computed:
            changed = dict(computed, **{stamp: Decimal("0.71")})
            with self.assertRaisesRegex(ValueError, "unexplained spread"):
                rates.audit_spread(changed, reference, "T10Y2Y")

    def test_country_validation_and_withdrawal_protection(self):
        row = observation("us_effr", "1954-07-01", "1.13", "https://fred.stlouisfed.org/series/DFF")
        self.assertEqual(row["country"], "USA")
        self.assertEqual(observation("cpi_yoy", "2020-01", "2", "https://example.org")["country"], "CHN")
        validate([row], {"us_effr"})
        with self.assertRaises(ValueError):
            validate([dict(row, country="CHN")], {"us_effr"})
        with self.assertRaisesRegex(ValueError, "withdrew known"):
            merge([row], [], {"us_effr"}, {"us_effr": [{"start": "1954-07-01", "end": "2026-10-03"}]})


class USRateSnapshot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, cls.meta = load_topic("us-rates")
        cls.values = {}
        for row in cls.rows:
            cls.values.setdefault(row["series_id"], {})[row["period"]] = Decimal(row["value"])

    def test_complete_verified_starts_and_series_metadata(self):
        validate(self.rows, topic_series(TOPICS["us-rates"]))
        self.assertEqual(len(self.values), 11)
        self.assertTrue(all(r["country"] == "USA" and not r["published_at"] for r in self.rows))
        for key, (_, earliest, _) in rates.SOURCES.items():
            self.assertLessEqual(min(self.values[key]), earliest)
            self.assertTrue(self.meta["history"][key]["full_equals_split"])
        self.assertEqual(max(self.values["us_target"]), "2008-12-15")
        self.assertEqual(min(self.values["us_target_lower"]), "2008-12-16")
        self.assertEqual(self.values["us_target_lower"].keys(), self.values["us_target_upper"].keys())
        self.assertTrue(all(v <= self.values["us_target_upper"][p] for p, v in self.values["us_target_lower"].items()))

    def test_spreads_only_use_common_observation_dates(self):
        for key, (left, right, _) in rates.DERIVED.items():
            expected = {p: self.values[left][p] - self.values[right][p]
                        for p in self.values[left].keys() & self.values[right].keys()}
            self.assertEqual(self.values[key], expected)

    def test_payload_contains_earliest_dates_and_preserves_nulls(self):
        charts = {c["id"]: c for c in payload("us-rates", self.rows, self.meta)["charts"]}
        self.assertEqual(charts["us-policy-rates"]["periods"][0], "1954-07-01")
        self.assertEqual(charts["us-treasury-monthly"]["periods"][0], "1953-04")
        self.assertNotIn("1953-04", charts["us-treasury-monthly"]["values"]["us_treasury_2y_monthly"])
        self.assertTrue(any(v < 0 for v in charts["us-term-spread"]["values"]["us_term_spread"].values()))

    def test_compact_page_keeps_full_payload_without_massive_initial_table(self):
        page = document("us-rates", self.rows, self.meta)
        self.assertEqual(page.count('<tr id="macro-'), 6 * 60)
        self.assertIn("完整CSV", page)
        for key in rates.DERIVED:
            row = next(r for r in self.rows if r["series_id"] == key)
            self.assertIn("DGS10%2C", row["source_url"])
            self.assertNotIn(rates.DERIVED[key][2], row["source_url"])


if __name__ == "__main__":
    unittest.main()

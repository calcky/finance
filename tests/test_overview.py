"""Overview arithmetic, source clocks and publication integrity."""

from decimal import Decimal
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import macro_overview as overview


def row(period, value, country="CHN", key="cpi_yoy"):
    return dict(series_id=key, country=country, period=period, value=value,
                source_url="https://example.org/official", published_at="")


class SummaryArithmetic(unittest.TestCase):
    def test_country_missing_values_and_previous_observation(self):
        rows = [row("2026-04", ""), row("2026-03", "0"), row("2026-01", "-1.2"),
                row("2026-04", "10", "USA")]
        s = overview.summarize(rows, "cpi_yoy")
        self.assertEqual(s["latest"]["period"], "2026-03")
        self.assertEqual(s["previous"]["period"], "2026-01")
        self.assertEqual(s["delta"], Decimal("1.2"))
        self.assertEqual(s["available_end"], "2026-04")
        self.assertEqual(s["count"], 2)

    def test_window_is_five_calendar_years_not_five_rows(self):
        rows = [row("2021-12", "-100"), row("2022-01", "-2"),
                row("2025-01", "4"), row("2026-08", "1")]
        s = overview.summarize(rows, "cpi_yoy")
        self.assertEqual((s["window_first"], s["window_count"]), ("2022-01", 3))
        self.assertEqual((s["low"], s["high"], s["position"]), (Decimal(-2), Decimal(4), Decimal(50)))
        self.assertEqual((s["first"], s["count"]), ("2021-12", 4))

    def test_constant_and_single_point_have_no_invented_rank(self):
        for rows in ([row("2026-01", "1.4")], [row("2026-01", "1.4"), row("2026-02", "1.40")]):
            self.assertIsNone(overview.summarize(rows, "cpi_yoy")["position"])
        self.assertIsNone(overview.summarize(rows[:1], "cpi_yoy")["previous"])

    def test_duplicate_missing_and_nonfinite_series_fail(self):
        for rows in ([], [row("2026-01", "")], [row("2026-01", "NaN")],
                     [row("2026-01", "1"), row("2026-01", "2")]):
            with self.assertRaises(ValueError):
                overview.summarize(rows, "cpi_yoy")

    def test_percentage_point_change_is_not_percent_growth(self):
        text = overview.card("prices", "cpi_yoy", "", [row("2026-01", "2"), row("2026-02", "3")],
                             dict(retrieved_at="2026-03-09T00:00:00+00:00"))
        self.assertIn("+1 个百分点", text)
        self.assertNotIn("50 %", text)
        self.assertIn("来源发布日期：未提供逐条日期", text)
        self.assertIn("2026-03-09T00:00:00+00:00", text)

    def test_latest_empty_period_remains_visible(self):
        text = overview.card("prices", "cpi_yoy", "", [row("2026-01", "0"), row("2026-02", "")],
                             dict(retrieved_at="2026-03-09T00:00:00+00:00"))
        self.assertIn("末期为空缺", text)
        self.assertIn("**0 %**", text)
        self.assertIn("尚无前次有效观测", text)


class SnapshotIntegration(unittest.TestCase):
    def test_generated_overview_matches_saved_snapshots(self):
        text = overview.document(overview.load_snapshots(overview.ROOT))
        self.assertEqual(text, (overview.ROOT / overview.OUTPUT).read_text())
        self.assertEqual(text.count(":class: overview-card"), 12)
        self.assertEqual(text.count("::::{container} overview-grid"), 6)
        self.assertEqual(text.count('<details class="overview-scenario">'), 3)

    def test_regeneration_is_noop_and_failed_generation_preserves_page(self):
        snapshots = overview.load_snapshots(overview.ROOT)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / overview.OUTPUT
            target.parent.mkdir(parents=True)
            with patch.object(overview, "ROOT", root), patch.object(overview, "load_snapshots", return_value=snapshots):
                overview.main()
                before = (target.read_bytes(), target.stat().st_mtime_ns)
                overview.main()
                self.assertEqual(before, (target.read_bytes(), target.stat().st_mtime_ns))
                with patch.object(overview, "document", side_effect=ValueError("missing series")):
                    with self.assertRaises(ValueError):
                        overview.main()
                self.assertEqual(before, (target.read_bytes(), target.stat().st_mtime_ns))


if __name__ == "__main__":
    unittest.main()

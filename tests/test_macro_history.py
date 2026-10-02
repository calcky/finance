"""Historical backfill integrity and safe routine updates."""

from pathlib import Path
import csv
from datetime import datetime, timezone
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from macro_common import observation
from macro_income_history import parse_release
from macro_render import load_topic, periods_between, document
from sync_macro import combine, merge, needs_history
import sync_macro
from macro_catalog import SERIES

URL = "https://www.stats.gov.cn/example"


class HistoryUpdates(unittest.TestCase):
    def test_recent_history_audit_avoids_repeated_backfills_of_quarterly_series(self):
        now = datetime(2026, 10, 2, tzinfo=timezone.utc)
        meta = dict(history={"income_ytd": {}}, retrieved_at="2026-07-15T00:00:00+00:00")
        self.assertTrue(needs_history(meta, now))
        meta["history_checked_at"] = "2026-10-01T00:00:00+00:00"
        self.assertFalse(needs_history(meta, now))
        self.assertTrue(needs_history({}, now))

    def test_declared_window_detects_missing_endpoints(self):
        old = [observation("cpi_yoy", f"2020-{m:02d}", 1, URL) for m in (1, 2, 3)]
        spans = {"cpi_yoy": [{"start": "2020-01", "end": "2020-12"}]}
        for fresh in (old[1:], old[:-1], []):
            with self.assertRaisesRegex(ValueError, "withdrew"):
                merge(old, fresh, ["cpi_yoy"], spans)

    def test_daily_refresh_preserves_closed_history_and_revisions(self):
        old = [observation("repo_7d", "2012-05-03", 3.53, URL),
               observation("repo_7d", "2026-09-23", 1.4, URL)]
        new = [observation("repo_7d", "2026-09-23", 1.3, URL)]
        ranges = {"repo_7d": [{"start": "2026-08-01", "end": "2026-10-02"}]}
        updated = merge(old, new, ["repo_7d"], ranges)
        self.assertEqual([(r["period"], r["value"]) for r in updated],
                         [("2012-05-03", "3.53"), ("2026-09-23", "1.3")])
        self.assertEqual(updated, merge(updated, new, ["repo_7d"], ranges))

    def test_backfill_can_introduce_separate_old_definition(self):
        current = [observation("m1", "2025-01", 100, URL)]
        history = current + [observation("m1_old", "2024-01", 60, URL)]
        self.assertEqual(len(merge(current, history, ["m1", "m1_old"], {})), 2)

    def test_conflicting_sources_and_partial_archives_fail_closed(self):
        old = observation("m2", "2001-09", "14.62485", URL)
        revised = observation("m2", "2001-09", "15.18226", URL)
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            combine([([old], {}), ([revised], {})])
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            combine([([], {"repo_7d": {"requested_window_complete": False}})])

    def test_income_release_disambiguates_real_growth(self):
        html = '<div class="txt-content">2013年全国居民人均可支配收入18311元，比上年名义增长10.9%，扣除价格因素，实际增长8.1%。</div>'
        item = dict(title="2013年国民经济稳中向好", published="2014-01-20", url=URL)
        rows = parse_release(html, item)
        self.assertEqual({r["series_id"]: r["value"] for r in rows},
                         {"income_ytd": "18311", "income_nominal_ytd_yoy": "10.9", "income_real_ytd_yoy": "8.1"})
        self.assertEqual({r["period"] for r in rows}, {"2013-Q4"})
        item.update(title="上半年国民经济运行缓中趋稳", published="2014-07-16")
        rows = parse_release(html.replace("2013年", "2014年上半年"), item)
        self.assertEqual({r["period"] for r in rows}, {"2014-Q2"})


class StagedPublication(unittest.TestCase):
    def run_case(self, revise=False, fail_render=False):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            directory = root / "data/macro"
            directory.mkdir(parents=True)
            topics = {k: dict(title=k, charts=[dict(series=[k])]) for k in ("cpi_yoy", "ppi_yoy")}
            rows, details = [], {}
            for key in topics:
                row = observation(key, "2026-01", 1, URL)
                with (directory / f"{key}.csv").open("w", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=sync_macro.FIELDS, lineterminator="\n")
                    writer.writeheader()
                    writer.writerow(row)
                meta = dict(schema_version=2, title=key, series={key: SERIES[key]},
                            retrieved_at="2026-01-20T00:00:00+00:00", history={key: {"archive": URL}},
                            coverage={key: dict(first="2026-01", last="2026-01", count=1)})
                (directory / f"{key}.metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
                rows.append(dict(row, value="2") if revise else row)
                details[key] = {"refresh_ranges": [{"start": "2026-01", "end": "2026-10"}]}
            source = root / "source.json"
            source.write_text(json.dumps(dict(rows=rows, meta=details)))
            before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in directory.iterdir()}
            # Rendering the second topic fails after the first is already
            # staged. Neither the first nor second snapshot may be replaced.
            effects = [None, RuntimeError("render failed")] if fail_render else [None, None]
            with patch.object(sync_macro, "ROOT", root), patch.object(sync_macro, "TOPICS", topics), \
                 patch.object(sync_macro, "SERIES", {k: SERIES[k] for k in topics}), \
                 patch.object(sync_macro, "render", side_effect=effects), \
                 patch.object(sys, "argv", ["sync_macro", "--source-snapshots", str(source)]):
                if fail_render:
                    with self.assertRaisesRegex(RuntimeError, "render failed"):
                        sync_macro.main()
                else:
                    sync_macro.main()
            after = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in directory.iterdir()}
            self.assertEqual(before, after)

    def test_later_render_failure_keeps_all_original_snapshots(self):
        self.run_case(revise=True, fail_render=True)

    def test_unchanged_daily_data_does_not_rewrite_metadata_or_timestamps(self):
        self.run_case()


class HistoricalSnapshots(unittest.TestCase):
    def setUp(self):
        self.topics = {slug: load_topic(slug) for slug in (
            "prices", "money-credit", "rates", "activity", "employment-income", "trade-fx")}
        self.rows = [row for rows, _ in self.topics.values() for row in rows]

    def selected(self, key):
        return sorted((r for r in self.rows if r["series_id"] == key), key=lambda r: r["period"])

    def test_coverage_cannot_silently_shrink_to_recent_window(self):
        starts = dict(cpi_yoy="1998-01", ppi_yoy="1993-01", m2="1999-12",
                      m1_old="1999-12", m1="2024-01", tsf_flow="2002-01",
                      lpr_1y_pre2019="2013-10", lpr_1y="2019-08",
                      repo_7d="2012-05-03",
                      usdcny_mid="2006-01-04", yield_10y="2006-03-01",
                      income_ytd="2013-Q1", income_real_ytd_yoy="2013-Q4",
                      income_nominal_ytd_yoy="2013-Q4", exports="1995-01")
        for key, latest_allowed_start in starts.items():
            with self.subTest(key=key):
                self.assertLessEqual(self.selected(key)[0]["period"], latest_allowed_start)

    def test_continuity_only_where_source_is_continuous(self):
        for key, frequency in [("m2", "M"), ("m1_old", "M"), ("m1", "M"),
                               ("tsf_flow", "M"), ("income_nominal_ytd_yoy", "Q")]:
            periods = [r["period"] for r in self.selected(key)]
            self.assertEqual(periods, periods_between(periods[0], periods[-1], frequency))
        stock = {r["period"] for r in self.selected("tsf_stock") if r["period"] < "2016-01"}
        self.assertEqual(stock, {"2014-12", "2015-03", "2015-06", "2015-09", "2015-12"})
        self.assertEqual(self.selected("tsf_flow")[0]["value"], "-472")

    def test_no_mixing_definition_or_combined_months(self):
        self.assertEqual(self.selected("m1_old")[-1]["period"], "2024-12")
        self.assertEqual(self.selected("lpr_1y_pre2019")[-1]["period"], "2019-07")
        self.assertTrue(all(r["period"] < "2011-01" for r in self.selected("investment_legacy_ytd_yoy")))
        self.assertTrue(all(r["period"] >= "2011-01" for r in self.selected("investment_ytd_yoy")))
        self.assertTrue(all(r["period"].endswith("-02") for r in self.selected("industry_janfeb_yoy")))
        self.assertFalse(any(r["period"] >= "2013-01" and r["period"][-2:] in ("01", "02") for r in self.selected("industry_yoy")))

    def test_coverage_metadata_and_extra_tables_include_history(self):
        for slug, (rows, meta) in self.topics.items():
            for key, coverage in meta["coverage"].items():
                selected = self.selected(key)
                self.assertEqual(coverage, dict(first=selected[0]["period"], last=selected[-1]["period"], count=len(selected)))
            if slug == "employment-income":
                self.assertIn("<tr><td>2013-Q1</td>", document(slug, rows, meta))


if __name__ == "__main__":
    unittest.main()

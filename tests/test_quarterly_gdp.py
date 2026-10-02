"""Quarterly GDP definitions, history coverage and scoped publication safety."""

import copy
from decimal import Decimal
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from macro_catalog import topic_series, TOPICS
from macro_quarterly_gdp import GROUPS, parse, verify_metadata
from macro_render import load_topic, periods_between
import macro_overview
import sync_macro


def fixture(group):
    _, unit, basis, start, _, members = group
    definitions = [dict(_id=i, i_showname=n, du_name=unit, dp_name=c, i_annotation=basis)
                   for _, i, n, c in members]
    cells = [dict(_id=i, i_showname=n, du_name=unit, da="000000000000", value="105.2")
             for _, i, n, _ in members]
    return (dict(success=True, data=dict(total=len(definitions), list=definitions)),
            dict(success=True, data=[dict(code=start[:4]+"01SS", values=cells)]))


class DefinitionContracts(unittest.TestCase):
    def test_index_conversion_never_applies_to_qoq_or_nominal(self):
        for group, expected in zip(GROUPS, ["105.2", "5.2", "105.2"]):
            metadata, payload = fixture(group)
            verify_metadata(metadata, group)
            self.assertEqual({r["value"] for r in parse(payload, group)}, {expected})
        _, payload = fixture(GROUPS[2])
        payload["data"][0]["values"][0]["value"] = "-10.1"
        self.assertEqual(parse(payload, GROUPS[2])[0]["value"], "-10.1")

    def test_nominal_real_seasonal_comparison_and_metadata_completeness(self):
        for group in GROUPS:
            metadata, _ = fixture(group)
            for field, bad in [("i_annotation", "未知"), ("du_name", "美元"),
                               ("dp_name", "同比错误"), ("i_showname", "另一指标")]:
                invalid = copy.deepcopy(metadata)
                invalid["data"]["list"][0][field] = bad
                with self.assertRaises(ValueError):
                    verify_metadata(invalid, group)
            metadata["data"]["total"] += 1
            with self.assertRaises(ValueError):
                verify_metadata(metadata, group)

    def test_geography_duplicate_wrong_quarter_missing_and_truncated_history(self):
        group = GROUPS[0]
        _, valid = fixture(group)
        cases = []
        wrong = copy.deepcopy(valid)
        wrong["data"][0]["values"][0]["da"] = "foreign"
        cases.append(wrong)
        wrong = copy.deepcopy(valid)
        wrong["data"] *= 2
        cases.append(wrong)
        wrong = copy.deepcopy(valid)
        wrong["data"][0]["code"] = "199206SS"
        cases.append(wrong)
        wrong = copy.deepcopy(valid)
        wrong["data"][0]["values"][0]["value"] = ""
        cases.append(wrong)
        wrong = copy.deepcopy(valid)
        wrong["data"][0]["code"] = "202601SS"
        cases.append(wrong)
        wrong = copy.deepcopy(valid)
        extra = copy.deepcopy(wrong["data"][0])
        extra["code"] = "199203SS"
        wrong["data"].append(extra)
        cases.append(wrong)
        for payload in cases:
            with self.assertRaises(ValueError):
                parse(payload, group)

    def test_single_quarter_and_ytd_cannot_swap_names(self):
        _, payload = fixture(GROUPS[1])
        payload["data"][0]["values"][0]["i_showname"] = GROUPS[1][-1][1][2]
        with self.assertRaises(ValueError):
            parse(payload, GROUPS[1])


class SnapshotIntegrity(unittest.TestCase):
    def setUp(self):
        self.rows, self.meta = load_topic("quarterly-gdp")

    def test_full_continuous_history_and_provenance(self):
        self.assertEqual({r["series_id"] for r in self.rows}, set(topic_series(TOPICS["quarterly-gdp"])))
        for group in GROUPS:
            for key, _, _, _ in group[-1]:
                selected = sorted((r for r in self.rows if r["series_id"] == key), key=lambda r: r["period"])
                periods = [r["period"] for r in selected]
                self.assertLessEqual(periods[0], group[3])
                self.assertGreaterEqual(periods[-1], "2026-Q2")
                self.assertEqual(periods, periods_between(periods[0], periods[-1], "Q"))
                self.assertTrue(all(not r["published_at"] for r in selected))
                self.assertEqual(self.meta["coverage"][key], dict(first=periods[0], last=periods[-1], count=len(periods)))
                self.assertIn("annotation", self.meta["acquisition"][key])

    def test_overview_distinguishes_quarterly_and_cumulative(self):
        text = macro_overview.card("quarterly-gdp", "gdp_q_yoy", "", self.rows, self.meta)
        self.assertIn("独立单季", text)
        self.assertNotIn("年内累计", text)
        self.assertIn("national/quarterData", text)
        rows, meta = load_topic("employment-income")
        text = macro_overview.card("employment-income", "income_real_ytd_yoy", "", rows, meta)
        self.assertIn("年内累计", text)
        self.assertIn("national/quarterData", text)

    def test_source_rounding_not_exact_additivity(self):
        values = {(r["series_id"], r["period"]): Decimal(r["value"]) for r in self.rows}
        for key, period in values:
            if key != "gdp_q_nominal":
                continue
            sectors = sum(values[f"gdp_{s}_q_nominal", period] for s in ("primary", "secondary", "tertiary"))
            # Four values rounded to 0.1 in source units (100 million yuan).
            self.assertLessEqual(abs(values[key, period]-sectors), Decimal("0.2"))
            quarter = int(period[-1])
            ytd = sum(values[key, f"{period[:4]}-Q{q}"] for q in range(1, quarter+1))
            self.assertLessEqual(abs(values["gdp_ytd_nominal", period]-ytd), Decimal("0.05")*(quarter+1))

    def test_scoped_first_sync_noop_revision_and_withdrawal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sentinel = root / "unrelated.txt"
            sentinel.write_text("preserve")
            acquisition = self.meta["acquisition"]
            with patch.object(sync_macro, "ROOT", root), patch.object(sync_macro, "render"), \
                 patch("macro_quarterly_gdp.collect", return_value=(self.rows, acquisition)) as collector:
                def run(*args):
                    with patch.object(sys, "argv", ["sync_macro", "--topics", "quarterly-gdp", *args]):
                        sync_macro.main()
                run("--backfill")  # No reverse-repo archive required.
                files = list((root / "data/macro").iterdir())
                self.assertEqual(len(files), 2)
                before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in files}
                run()
                self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in files})
                revised = copy.deepcopy(self.rows)
                revised[0]["value"] = str(Decimal(revised[0]["value"])+Decimal("0.1"))
                collector.return_value = revised, acquisition
                run()
                self.assertIn(revised[0], load_topic("quarterly-gdp", root)[0])
                before = {p: p.read_bytes() for p in files}
                collector.return_value = revised[1:], acquisition
                with self.assertRaisesRegex(ValueError, "withdrew"):
                    run()
                self.assertEqual(before, {p: p.read_bytes() for p in files})
                self.assertEqual(sentinel.read_text(), "preserve")

    def test_collector_scoping(self):
        self.assertEqual([f.__module__ for f in sync_macro.collectors_for({"quarterly-gdp"})], ["macro_quarterly_gdp"])
        self.assertEqual({f.__module__ for f in sync_macro.collectors_for({"employment-income"})},
                         {"macro_income_history", "macro_nbs_history"})


if __name__ == "__main__":
    unittest.main()

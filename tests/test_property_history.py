"""Property units, YTD periods, sales regimes and safe full-history refresh."""

import copy
import json
from decimal import Decimal
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from macro_catalog import TOPICS, topic_series
from macro_property import GROUPS, members, parse, verify_metadata, verify_quote, supplement
from macro_render import load_topic, payload
import sync_macro


def fixture(group, periods=("202602MM",)):
    expected = members(group)
    definitions = [dict(_id=i, i_showname=name, du_name=unit, dp_name=comparison,
                        i_annotation="2005年8月份以前为实际销售；以后包括期房和现房。")
                   for i, (_, name, unit, comparison) in expected.items()]
    cells = [dict(_id=i, i_showname=name, du_name=unit, da="000000000000", value="-12.1" if unit == "%" else "100")
             for i, (_, name, unit, _) in expected.items()]
    return expected, dict(success=True, data=dict(total=len(definitions), list=definitions)), dict(
        success=True, data=[dict(code=p, values=copy.deepcopy(cells)) for p in periods])


class Definitions(unittest.TestCase):
    def test_early_quotes_values_and_conversion_are_checked(self):
        path = Path(__file__).resolve().parents[1] / "data/reference/property-early-releases.json"
        records = json.loads(path.read_text())
        identities = {(r["series_id"], r["period"]) for r in records}
        self.assertEqual(len(records), len(identities))
        for record in records:
            body = "<div class='TRS_Editor'>"+record["source_text"]+"</div>"
            verify_quote(body, record)
            with self.assertRaisesRegex(ValueError, "quotation changed"):
                verify_quote("<p>Publication withdrawn</p>", record)
            wrong = dict(record, value="99999")
            with self.assertRaises(ValueError):
                verify_quote(body, wrong)

    def test_revised_database_wins_over_older_supplement(self):
        path = Path(__file__).resolve().parents[1] / "data/reference/property-early-releases.json"
        records = json.loads(path.read_text())
        rows = [dict(series_id=r["series_id"], period=r["period"], value="123") for r in records]
        with patch("macro_property.fetch", side_effect=AssertionError("No old release needed")):
            result, _ = supplement(rows, {})
        self.assertTrue(all(r["value"] == "123" for r in result))

    def test_exact_identity_units_and_ytd_dimension(self):
        for group in GROUPS:
            expected, metadata, data = fixture(group)
            verify_metadata(metadata, expected)
            rows = parse(data, expected)
            self.assertEqual({r["period"] for r in rows}, {"2026-02"})
            self.assertEqual({r["value"] for r in rows}, {"-12.1", "100"})
            for field, wrong in [("i_showname", "另一个指标"), ("du_name", "平方米"), ("dp_name", "同比增减%")]:
                bad = copy.deepcopy(metadata)
                bad["data"]["list"][0][field] = wrong
                with self.assertRaises(ValueError):
                    verify_metadata(bad, expected)
            metadata["data"]["total"] += 1
            with self.assertRaises(ValueError):
                verify_metadata(metadata, expected)

    def test_sales_transition_preserves_every_value_without_splicing(self):
        expected, metadata, data = fixture(GROUPS[3], ("200402MM", "200507MM", "200508MM", "200509MM", "200602MM"))
        rows = parse(data, expected)
        self.assertEqual(len(rows), 10)
        for row in rows:
            suffix = "_legacy" if row["period"][:4] == "2004" else "_transition" if row["period"][:4] == "2005" else ""
            self.assertEqual(row["series_id"], "property_sales_area_"+("ytd_yoy" if row["unit"] == "%" else "ytd")+suffix)
        metadata["data"]["list"][0]["i_annotation"] = "范围已改变"
        with self.assertRaisesRegex(ValueError, "scope"):
            verify_metadata(metadata, expected)

    def test_zero_and_negative_growth_not_missing_and_amounts_never_imply_growth(self):
        expected, _, data = fixture(GROUPS[0])
        data["data"][0]["values"][0]["value"] = "0"
        rows = parse(data, expected)
        self.assertEqual(rows[0]["value"], "0")
        self.assertIn("-12.1", [r["value"] for r in rows])
        data["data"][0]["values"][1]["value"] = ""
        with self.assertRaisesRegex(ValueError, "omitted"):
            parse(data, expected)

    def test_january_duplicate_geography_schema_and_negative_amount_fail(self):
        expected, _, valid = fixture(GROUPS[0])
        cases = []
        wrong = copy.deepcopy(valid)
        wrong["data"][0]["code"] = "202601MM"
        cases.append(wrong)
        wrong = copy.deepcopy(valid)
        wrong["data"] *= 2
        cases.append(wrong)
        for field, value in [("da", "foreign"), ("du_name", "美元"), ("i_showname", "当月投资"), ("value", "-1")]:
            wrong = copy.deepcopy(valid)
            wrong["data"][0]["values"][0][field] = value
            cases.append(wrong)
        for data in cases:
            with self.assertRaises(ValueError):
                parse(data, expected)


class PublishedHistory(unittest.TestCase):
    def setUp(self):
        self.rows, self.meta = load_topic("property")

    def test_all_history_and_separate_regimes_have_provenance(self):
        self.assertEqual({r["series_id"] for r in self.rows}, set(topic_series(TOPICS["property"])))
        self.assertGreaterEqual(len(self.rows), 5744)
        self.assertFalse(any(r["period"].endswith("-01") for r in self.rows))
        for key in self.meta["coverage"]:
            rows = [r for r in self.rows if r["series_id"] == key]
            periods = sorted(r["period"] for r in rows)
            self.assertEqual(self.meta["coverage"][key], dict(first=periods[0], last=periods[-1], count=len(periods)))
            self.assertTrue(all(r["source_url"].startswith("https://") for r in rows))
            self.assertIn("request", self.meta["history"][key])
            if key.endswith("_legacy"):
                self.assertTrue(all(p < "2005-01" for p in periods))
            elif key.endswith("_transition"):
                self.assertTrue(all(p.startswith("2005-") for p in periods))
            else:
                self.assertGreaterEqual(periods[-1], "2026-08")
                if "_sales_" in key:
                    self.assertEqual(periods[0], "2006-02")
        charts = payload("property", self.rows, self.meta)["charts"]
        self.assertEqual(len(charts), 6)
        self.assertIn("2026-01", charts[0]["periods"])
        self.assertNotIn("2026-01", charts[0]["values"][charts[0]["series"][0]])

    def test_scoped_noop_revision_and_source_withdrawal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(sync_macro, "ROOT", root), patch.object(sync_macro, "render"), \
                 patch("macro_property.collect", return_value=(self.rows, self.meta["history"])) as collector:
                def run(*args):
                    with patch.object(sys, "argv", ["sync_macro", "--topics", "property", *args]):
                        sync_macro.main()
                run("--backfill")
                files = list((root / "data/macro").iterdir())
                self.assertEqual(len(files), 2)
                before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in files}
                run()
                self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in files})
                revised = copy.deepcopy(self.rows)
                revised[0]["value"] = str(Decimal(revised[0]["value"])+Decimal("0.1"))
                collector.return_value = revised, self.meta["history"]
                run()
                self.assertIn(revised[0], load_topic("property", root)[0])
                before = {p: p.read_bytes() for p in files}
                collector.return_value = revised[1:], self.meta["history"]
                with self.assertRaisesRegex(ValueError, "withdrew"):
                    run()
                self.assertEqual(before, {p: p.read_bytes() for p in files})


if __name__ == "__main__":
    unittest.main()

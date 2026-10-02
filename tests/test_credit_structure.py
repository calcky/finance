"""AFRE scope, negative composition and borrower/maturity stock contracts."""

from decimal import Decimal
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from macro_tsf_components import parse_components, grouped
from macro_loan_history import parse_loans
from macro_render import load_topic, payload, periods_between
import sync_macro

URL = "https://www.pbc.gov.cn/official-test.htm"


def table(rows):
    return ("<table>" + "".join("<tr>" + "".join(f"<td>{v}</td>" for v in row) + "</tr>" for row in rows) + "</table>").encode()


HEADER = ["月份", "社会融资规模增量", "人民币贷款", "外币贷款（折合人民币）", "委托贷款", "信托贷款",
          "未贴现的银行承兑汇票", "企业债券", "政府债券", "非金融企业境内股票融资", "存款类金融机构资产支持证券", "贷款核销"]


class SourceContracts(unittest.TestCase):
    def test_backcast_split_header_overwrites_all_components_not_percentages(self):
        rows = [["社会融资规模增量统计表"], ["单位：亿元人民币"], HEADER,
                ["2017.01", 36000, 23000, 100, 3100, 3200, 6100, -500, 600, 1200, -100, 200],
                ["单位：亿元人民币"], ["月份", "社会融资规模当月增量"], ["", ""]+HEADER[2:],
                ["2017.01", 37720, 23133, 126, 3142, 3128, 6130, -510, 665, 1225, -129, 253],
                ["单位：%"], HEADER, ["2017.01"]+[1]*11]
        values = grouped(parse_components(table(rows), 2019, URL))
        expected = dict(total=37720, tsf_rmb_flow=23133, tsf_direct_flow=715,
                        tsf_offbalance_flow=12400, tsf_remaining_flow=807)
        for key, value in expected.items():
            self.assertEqual(values[key, "2017-01"], value)

    def test_legacy_missing_is_not_zero_and_cannot_build_complete_group(self):
        header = HEADER[:8]+[HEADER[9]]
        values = parse_components(table([["社会融资规模"], ["单位：亿元人民币"], header,
                                         ["2002.01", -472, 240, -11, -12, "——", -755, 0, 40]]), 2012, URL)
        self.assertNotIn(("tsf_trust_flow", "2002-01"), values)
        self.assertEqual(values["tsf_corporate_bonds_flow", "2002-01"], 0)
        self.assertNotIn(("tsf_offbalance_flow", "2002-01"), grouped(values))
        self.assertNotIn(("tsf_remaining_flow", "2002-01"), grouped(values))

    def test_month_ten_and_missing_component_rejected(self):
        rows = [["社会融资规模"], ["单位：亿元人民币"], HEADER, [2019.1]+list(range(11))]
        values = parse_components(table(rows), 2019, URL)
        self.assertEqual({p for _, p in values}, {"2019-10"})
        rows[-1][-1] = ""
        with self.assertRaisesRegex(ValueError, "component missing"):
            parse_components(table(rows), 2019, URL)

    def test_transposed_history_and_currency_validation(self):
        labels = HEADER[1:8]+[HEADER[9]]
        rows = [["社会融资规模"], ["单位：亿元人民币"], ["项目"]+[f"2012.{m:02d}" for m in range(1,13)]]
        rows += [[label]+list(range(12)) for label in labels]
        result = parse_components(table(rows), 2012, URL)
        self.assertEqual(len(result), 96)
        self.assertEqual(result["tsf_rmb_flow", "2012-10"], 9)
        with self.assertRaisesRegex(ValueError, "unit"):
            parse_components(table(rows).replace("亿元".encode(), "美元".encode()), 2012, URL)

    def loans(self, year=2025, old=False):
        rows = [["金融机构人民币信贷收支表"], ["单位：亿元人民币"],
                ["项目"]+[f"{year}.{m:02d}" for m in range(1,13)]]
        def add(label, value):
            rows.append([label]+[value]*12)
        add("住户贷款", 100)
        if old:
            for name, value in [("短期消费性贷款", 10), ("短期经营性贷款", 20),
                                ("中长期消费性贷款", 30), ("中长期经营性贷款", 40)]:
                add(name, value)
        else:
            add("短期贷款", 30)
            add("中长期贷款", 70)
        add("非金融性公司及其他部门贷款" if old else "企（事）业单位贷款", 200)
        add("短期贷款及票据融资", 90)
        add("短期贷款", 80.123456)
        add("中长期贷款", 90)
        add("票据融资", 10)
        return rows

    def test_borrower_blocks_subtotals_precision_and_legacy_scope(self):
        rows = parse_loans(table(self.loans()), 2025, URL)
        v = {r["series_id"]: r["value"] for r in rows}
        self.assertEqual(v["loan_household_short"], "0.003")
        self.assertEqual(v["loan_business_short"], "0.008012")
        self.assertEqual(v["loan_business_bills"], "0.001")
        old = parse_loans(table(self.loans(2007, True)), 2007, URL)
        v = {r["series_id"]: r["value"] for r in old}
        self.assertEqual(v["loan_household_short"], "0.003")
        self.assertEqual(v["loan_household_long"], "0.007")
        self.assertIn("loan_business_legacy_total", v)
        self.assertNotIn("loan_business_total", v)

    def test_loans_missing_periods_or_wrong_currency_fail(self):
        rows = self.loans()
        rows[4][2] = ""
        with self.assertRaisesRegex(ValueError, "missing months"):
            parse_loans(table(rows), 2025, URL)
        data = table(self.loans()).replace("人民币".encode(), "美元".encode())
        with self.assertRaisesRegex(ValueError, "currency"):
            parse_loans(data, 2025, URL)


class PublishedHistory(unittest.TestCase):
    def setUp(self):
        self.rows, self.meta = load_topic("credit-structure")
        self.v = {(r["series_id"], r["period"]): Decimal(r["value"]) for r in self.rows}

    def test_history_and_real_gaps_remain(self):
        expected = dict(tsf_rmb_flow="2002-01", tsf_trust_flow="2006-01", tsf_government_flow="2017-01",
                        loan_household_total="2007-01", loan_business_total="2010-01", loan_business_legacy_total="2007-01")
        for key, start in expected.items():
            periods = sorted(p for k, p in self.v if k == key)
            self.assertLessEqual(periods[0], start)
        self.assertFalse(any(k == "loan_business_legacy_total" and p > "2009-12" for k,p in self.v))
        for key in ("tsf_rmb_flow", "tsf_trust_flow", "tsf_government_flow", "loan_household_total", "loan_business_total"):
            periods = sorted(p for k,p in self.v if k == key)
            self.assertEqual(periods, periods_between(periods[0], periods[-1], "M"))
        for key in self.meta["coverage"]:
            periods = sorted(p for k, p in self.v if k == key)
            self.assertEqual(self.meta["coverage"][key], dict(first=periods[0], last=periods[-1], count=len(periods)))
            self.assertIn("attachments", self.meta["history"][key])

    def test_grouped_net_matches_official_total_and_household_identity(self):
        totals, _ = load_topic("money-credit")
        for row in totals:
            p = row["period"]
            if row["series_id"] != "tsf_flow" or ("tsf_remaining_flow", p) not in self.v:
                continue
            net = sum(self.v[k,p] for k in TOP_FIVE)
            self.assertEqual(net, Decimal(row["value"]), p)
        for (key,p), v in self.v.items():
            if key == "loan_household_total":
                self.assertLessEqual(abs(v-self.v["loan_household_short",p]-self.v["loan_household_long",p]), Decimal(".000002"))

    def test_stack_common_history_and_net_not_positive_top(self):
        charts = payload("credit-structure", self.rows, self.meta)["charts"]
        stack = charts[0]
        self.assertEqual(stack["periods"][0], "2017-01")
        self.assertEqual(charts[1]["periods"][0], "2002-01")
        for p in stack["periods"]:
            self.assertAlmostEqual(stack["totals"][p], sum(stack["values"][k][p] for k in stack["series"]))
        self.assertTrue(any(sum(max(0, stack["values"][k][p]) for k in stack["series"]) > stack["totals"][p] for p in stack["periods"]))

    def test_missing_component_never_produces_partial_net(self):
        rows = [r for r in self.rows if (r["series_id"], r["period"]) != ("tsf_government_flow", "2026-08")]
        chart = payload("credit-structure", rows, self.meta)["charts"][0]
        self.assertNotIn("2026-08", chart["totals"])
        self.assertIn("2026-08", chart["periods"])

    def test_scoped_daily_noop_and_withdrawal_preserve_all_history(self):
        full = [(self.rows, self.meta["history"])]
        recent = [r for r in self.rows if r["period"] >= "2025-01"]
        detail = {r["series_id"]: {"refresh_ranges": [{"start": "2025-01", "end": "2026-12"}]} for r in recent}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(sync_macro, "ROOT", root), patch.object(sync_macro, "render"), \
                 patch.object(sync_macro, "collectors_for") as discovery:
                collector = unittest.mock.Mock(return_value=full[0])
                discovery.return_value = [collector]
                def run(*args):
                    with patch.object(sys, "argv", ["sync_macro", "--topics", "credit-structure", *args]):
                        sync_macro.main()
                run("--backfill")
                files = list((root / "data/macro").iterdir())
                self.assertEqual(len(files), 2)
                before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in files}
                collector.return_value = recent, detail
                run()
                self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in files})
                collector.return_value = recent[1:], detail
                with self.assertRaisesRegex(ValueError, "withdrew"):
                    run()
                self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in files})
                collector.side_effect = OSError("Source unavailable")
                with self.assertRaisesRegex(OSError, "Source unavailable"):
                    run()
                self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in files})


TOP_FIVE = ["tsf_rmb_flow", "tsf_government_flow", "tsf_direct_flow", "tsf_offbalance_flow", "tsf_remaining_flow"]

if __name__ == "__main__":
    unittest.main()

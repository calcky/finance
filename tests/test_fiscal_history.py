"""Fiscal period, scope, source-priority and full-history regressions."""

import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from macro_catalog import SERIES, TOPICS, topic_series
from macro_common import observation
from macro_fiscal import merge_budget, budget_supplements
from macro_fiscal_nbs import GROUPS, parse, verify_metadata
from macro_fiscal_mof import archive, parse_budget, html_for, collect_budget
from macro_fiscal_debt import parse_debt
from macro_fiscal_annual import parse_fund, parse_local
from macro_render import load_topic, periods_between, payload
from sync_macro import merge, validate

URL = "https://example.org/official.htm"


class FiscalParsing(unittest.TestCase):
    def test_timeout_reports_source_and_never_substitutes_data(self):
        with patch("macro_fiscal_mof.fetch", side_effect=TimeoutError("read timed out")) as request:
            with self.assertRaisesRegex(RuntimeError, URL) as context:
                html_for(URL)
        self.assertIsInstance(context.exception.__cause__, TimeoutError)
        self.assertEqual(request.call_count, 1)

    def test_fiscal_wrapper_does_not_retry_access_refusals(self):
        with patch("macro_fiscal_mof.fetch", side_effect=HTTPError(URL, 403, "Forbidden", {}, None)) as request:
            with self.assertRaises(RuntimeError):
                html_for(URL)
            self.assertEqual(request.call_count, 1)

    def test_annual_identity_dimension_and_future_year(self):
        members = GROUPS[0][2]
        definitions = [dict(_id=i, i_showname=n, du_name=u,
                            dp_name="累计同比增减%" if u == "%" else "本期累计") for i, (_, n, u) in members.items()]
        meta = dict(success=True, data=dict(total=len(definitions), list=definitions))
        verify_metadata(meta, members)
        bad = copy.deepcopy(meta)
        bad["data"]["list"][0]["dp_name"] = "本期"
        with self.assertRaisesRegex(ValueError, "comparison"):
            verify_metadata(bad, members)
        cells = [dict(d, da="000000000000", value="100") for d in definitions]
        data = dict(success=True, data=[dict(code="1950YY", values=cells)])
        self.assertEqual(parse(data, members, "A")[0]["period"], "1950")
        with self.assertRaisesRegex(ValueError, "frequency"):
            parse(data, members, "M")
        data["data"][0]["values"].append(cells[0])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            parse(data, members, "A")
        with self.assertRaisesRegex(ValueError, "Future"):
            observation("fiscal_revenue_annual", "2999", 1, URL)
        self.assertEqual(periods_between("1999", "2002", "A"), ["1999", "2000", "2001", "2002"])

    def test_monthly_first_is_not_cumulative(self):
        # 2008-11 official report puts both contexts in the SAME paragraph.
        text = ["11月份，全国财政收入3792.4亿元，比去年同月下降3.1%。1-11月累计，全国财政收入58068.21亿元，比去年同期增长20.5%。",
                "1-11月累计，全国财政支出45825.34亿元。"]
        rows = parse_budget("2008年11月份财政收支情况", text, URL, "2008-12-11")
        self.assertEqual({r["series_id"]: r["value"] for r in rows}, {
            "fiscal_revenue_ytd": "58068.21", "fiscal_expenditure_ytd": "45825.34"})
        with self.assertRaisesRegex(ValueError, "cumulative"):
            parse_budget("2008年11月份财政收支情况", text[:1][0].split("1-11月")[:1], URL, "")

    def test_missing_land_is_not_backsolved_from_growth(self):
        p = ["1-3月，全国一般公共预算收入100亿元。其中，税收收入80亿元；非税收入20亿元。",
             "二、全国政府性基金预算收支情况", "1-3月，全国政府性基金预算收入50亿元，其中，国有土地使用权出让收入同比下降20%。",
             "1-3月，全国政府性基金预算支出60亿元。"]
        rows = parse_budget("2019年1-3月财政收支情况", p, URL, "")
        self.assertNotIn("fiscal_land_ytd", {r["series_id"] for r in rows})
        self.assertEqual(next(r["value"] for r in rows if r["series_id"] == "fiscal_fund_revenue_ytd"), "50")

    def test_stale_archive_count_and_duplicate_pages(self):
        first = "<!--createPageHTML(3,0)-->var countPage=1<div class='liBox'><a href='a.htm'>2025年财政收支情况</a></div>"
        page = lambda name: BeautifulSoup(f"<div class='liBox'><a href='{name}.htm'>2024年财政收支情况</a></div>", "html.parser")
        with patch("macro_fiscal_mof.fetch", return_value=first.encode()), patch("macro_fiscal_mof.soup_for", side_effect=[page('b'), page('c')]):
            entries, pages = archive("https://example.org/", "财政收支", True)
        self.assertEqual((len(entries), len(pages)), (3, 3))
        with patch("macro_fiscal_mof.fetch", return_value=first.encode()), patch("macro_fiscal_mof.soup_for", return_value=page('a')):
            with self.assertRaisesRegex(ValueError, "repeated"):
                archive("https://example.org/", "财政收支", True)

    def test_debt_current_month_stock_and_legacy_combined(self):
        text = """一、全国地方政府债券发行情况2018年12月份，全国发行地方政府债券638亿元。其中，发行新增债券475亿元，发行置换债券和再融资债券（用于偿还部分到期本金）163亿元。
        2018年，全国发行地方政府债券41652亿元。二、全国地方政府债务余额情况截至2018年末，全国地方政府债务余额183862亿元。其中，一般债务109939亿元，专项债务73923亿元。"""
        rows = parse_debt("2018年地方政府债券发行和债务余额情况", text, URL, "2019-01-23")
        values = {r["series_id"]: r["value"] for r in rows}
        self.assertEqual(values["fiscal_issuance_gross"], "638")
        self.assertEqual(values["fiscal_issuance_swap_refinancing"], "163")
        self.assertNotIn("fiscal_issuance_refinancing", values)
        self.assertEqual(values["fiscal_local_total_stock"], "183862")
        with self.assertRaisesRegex(ValueError, "period mismatch"):
            parse_debt("2018年地方政府债券发行和债务余额情况", text.replace("截至2018年末", "截至2017年末"), URL, "")
        with self.assertRaisesRegex(ValueError, "components"):
            parse_debt("2018年地方政府债券发行和债务余额情况", text.replace("163亿元", "170亿元"), URL, "")

    def test_explicit_all_is_not_a_missing_zero(self):
        t = "一、全国地方政府债券发行情况2018年3月份，全国发行地方政府债券1910亿元；全部是置换债券。二、全国地方政府债务余额情况截至2018年3月末，全国地方政府债务余额166101亿元，其中一般债务104355亿元，专项债务61746亿元。"
        rows = parse_debt("2018年3月地方政府债券发行和债务余额情况", t, URL, "")
        values = {r["series_id"]: r["value"] for r in rows}
        self.assertEqual(values["fiscal_issuance_swap"], "1910")
        self.assertNotIn("fiscal_issuance_new", values)

    def test_final_accounts_select_final_not_budget_and_preserve_narrow_land(self):
        soup = BeautifulSoup("""<p>单位：亿元</p><table><tr><td>项目</td><td>预算数</td><td>决算数</td></tr>
          <tr><td>全国政府性基金收入</td><td>18704.49</td><td>36785.02</td></tr>
          <tr><td>卅二、国有土地使用权出让金收入</td><td>12447.00</td><td>28197.70</td></tr></table>""", "html.parser")
        rows = parse_fund("2010年全国政府性基金收入决算表", soup, URL, "2011-07-20")
        values = {r["series_id"]: r["value"] for r in rows}
        self.assertEqual(values["fiscal_fund_revenue_annual"], "36785.02")
        self.assertEqual(values["fiscal_land_fee_annual"], "28197.70")
        with self.assertRaisesRegex(ValueError, "national"):
            parse_fund("2010年中央政府性基金收入决算表", soup, URL, "")
        soup.find(string="决算数").replace_with("执行数")
        with self.assertRaisesRegex(ValueError, "headers"):
            parse_fund("2010年全国政府性基金收入决算表", soup, URL, "")

    def test_local_debt_actual_rows_not_ceiling_and_later_vintage(self):
        soup = BeautifulSoup("""<p>单位：亿元</p><table>
        <tr><td>一、2015年末地方政府一般债务余额实际数</td><td></td><td>92619.04</td></tr>
        <tr><td>二、2016年地方政府一般债务限额</td><td>999999</td></tr>
        <tr><td>七、2016年末地方政府一般债务余额实际数</td><td></td><td>97867.78</td></tr></table>""", "html.parser")
        rows, year = parse_local("2016年地方政府一般债务余额决算表", soup, URL, "2017-07-13")
        self.assertEqual(year, 2016)
        self.assertEqual({r["period"]:r["value"] for r in rows}, {"2015":"92619.04", "2016":"97867.78"})

    def test_source_priority_keeps_annual_separate_and_does_not_mutate(self):
        nbs = [observation("fiscal_revenue_ytd", "2024-12", 219702, URL),
               observation("fiscal_revenue_annual", "2024", "219734.30", URL)]
        mof = [observation("fiscal_revenue_ytd", "2024-12", 219700, URL),
               observation("fiscal_revenue_ytd", "2025-02", 100, URL)]
        saved = copy.deepcopy(nbs)
        result, differences = merge_budget(nbs, mof)
        self.assertEqual(nbs, saved)
        self.assertEqual(len(result), 3)
        self.assertEqual(differences[0]["selected_nbs_value"], "219702")

    def test_daily_refresh_rechecks_release_only_gaps_inside_database_window(self):
        source = "https://gks.mof.gov.cn/tongjishuju/200902/t20090201_110982.htm"
        old = [observation("fiscal_revenue_ytd", "2008-12", "61330.35", source),
               observation("fiscal_tax_ytd", "2009-01", "5293", source)]
        self.assertEqual(budget_supplements([], old), [source])
        revised = [observation("fiscal_revenue_ytd", "2008-12", "61330.36", "https://data.stats.gov.cn/api")]
        self.assertEqual(budget_supplements(revised, old), [])
        fresh, _ = merge_budget(revised, old)
        self.assertEqual(next(r["value"] for r in fresh if r["series_id"] == "fiscal_revenue_ytd"), "61330.36")

    def test_old_headline_supplement_does_not_widen_other_refresh_windows(self):
        old_url = "https://gks.mof.gov.cn/tongjishuju/201701/t20170123_2526014.htm"
        current = dict(url=URL, title="2026年1-8月财政收支情况")
        old_soup = BeautifulSoup("<h2 class='title_con'>2016年财政收支情况</h2>", "html.parser")
        current_p = ["1-8月，全国一般公共预算收入100亿元。二、全国政府性基金预算收支情况", "1-8月，全国政府性基金预算收入60亿元。"]
        old_p = ["全年，全国一般公共预算收入200亿元。二、全国政府性基金预算收支情况", "全年，全国政府性基金预算收入120亿元。"]
        with patch("macro_fiscal_mof.archive", return_value=([current], [URL])), patch("macro_fiscal_mof.article", side_effect=[(None,current_p,""),(old_soup,old_p,"")]):
            rows, _ = collect_budget(False, [old_url])
        identities = {(r["series_id"],r["period"]) for r in rows}
        self.assertIn(("fiscal_revenue_ytd", "2016-12"), identities)
        self.assertNotIn(("fiscal_fund_revenue_ytd", "2016-12"), identities)
        self.assertIn(("fiscal_fund_revenue_ytd", "2026-08"), identities)


class FiscalSnapshot(unittest.TestCase):
    def test_full_snapshot_and_interactive_gaps(self):
        rows, meta = load_topic("fiscal")
        validate(rows, topic_series(TOPICS["fiscal"]))
        values = {(r["series_id"],r["period"]): r["value"] for r in rows}
        self.assertEqual(values["fiscal_revenue_annual", "1950"], "62.17")
        self.assertEqual(values["fiscal_fund_revenue_annual", "2010"], "36785.02")
        self.assertEqual(values["fiscal_local_general_annual", "2015"], "92619.04")
        self.assertEqual(values["fiscal_local_total_stock", "2026-08"], "598955")
        self.assertEqual(values["fiscal_local_total_stock", "2017-11"], "165944")
        self.assertEqual(sum(r["series_id"] == "fiscal_issuance_gross" for r in rows), 104)
        self.assertEqual(values["fiscal_land_ytd", "2026-08"], "13753")
        self.assertNotIn(("fiscal_land_ytd", "2019-03"), values)
        self.assertNotIn(("fiscal_fund_revenue_ytd", "2013-04"), values)
        charts = payload("fiscal", rows, meta)["charts"]
        self.assertEqual(len(charts), 10)
        self.assertEqual(charts[0]["frequency"], "A")
        self.assertIn("2013-04", next(c for c in charts if c["id"] == "fiscal-funds")["periods"])
        for c in charts:
            self.assertEqual(len({SERIES[k]["frequency"] for k in c["series"]}), 1)

    def test_withdrawal_fails_and_retains_saved_snapshot(self):
        rows, _ = load_topic("fiscal")
        saved = copy.deepcopy(rows)
        key = "fiscal_revenue_annual"
        with self.assertRaisesRegex(ValueError, "withdrew"):
            merge(rows, [r for r in rows if not (r["series_id"] == key and r["period"] == "1950")],
                  topic_series(TOPICS["fiscal"]), {key: [{"start":"1949", "end":"2026"}]})
        self.assertEqual(rows, saved)


if __name__ == "__main__":
    unittest.main()

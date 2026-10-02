"""Historical NBS contracts: revisions must not erase valid older definitions."""

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from macro_nbs_history import parse_monthly, refresh_range, collect
from macro_nbs_cpi_releases import parse_release, parse_economy_release

URL = "https://www.stats.gov.cn/sj/zxfb/example.html"


def payload(code, value, name):
    return {"data": [{"code": code, "values": [{"_id": "id", "da": "000000000000",
        "value": value, "i_showname": name, "du_name": "%"}]}]}


class HistoryContracts(unittest.TestCase):
    def parse(self, key, code, value, name, transform="identity"):
        members = {"id": (key, name, "%", transform, "")}
        return parse_monthly(payload(code, value, name), members, {"cid": "source"})

    def test_old_m1_and_investment_remain_separate(self):
        rows = self.parse("m1_yoy", "202412MM", "-1.4", "货币(M1)供应量同比增长")
        self.assertEqual(rows[0]["series_id"], "m1_old_yoy")
        rows = self.parse("m1_yoy", "202501MM", "0.4", "货币(M1)供应量同比增长")
        self.assertEqual(rows[0]["series_id"], "m1_yoy")
        rows = self.parse("investment_ytd_yoy", "201012MM", "24.5", "固定资产投资额累计增长")
        self.assertEqual(rows[0]["series_id"], "investment_legacy_ytd_yoy")

    def test_missing_indicator_does_not_pass_on_other_valid_series(self):
        members = {"id": ("m2_yoy", "M2", "%", "identity", ""),
                   "missing": ("m1_yoy", "M1", "%", "identity", "")}
        with self.assertRaises(ValueError):
            parse_monthly(payload("202501MM", "7.0", "M2"), members, {"cid": "source"})

    def test_whole_legacy_segment_cannot_disappear_silently(self):
        with patch.multiple("macro_nbs_history", CONFIG={
                "m1_yoy": ("money", "id", "M1", "%", "identity", "202501")},
                PRICE_HISTORY=[], COMBINED=[]), patch("macro_nbs_history._payload",
                return_value=payload("202501MM", "0.4", "M1")):
            with self.assertRaisesRegex(ValueError, "definition segment missing"):
                collect(backfill=True)

    def test_refresh_uses_catalog_boundaries_not_returned_observations(self):
        request = {"dts": ["194901MM-202610MM"]}
        self.assertEqual(refresh_range("ppi_yoy", "ppi", request), {"start": "1949-01", "end": "2026-10"})
        self.assertEqual(refresh_range("m1_old_yoy", "money", request)["end"], "2024-12")
        self.assertEqual(refresh_range("core_cpi_yoy", "809d2522b0fe4be89142650341b19083", request),
                         {"start": "2021-01", "end": "2025-12"})

    def test_monthly_february_is_not_cumulative(self):
        monthly = self.parse("retail_yoy", "200002MM", "10.5", "社会消费品零售总额同比增长")
        cumulative = self.parse("retail_janfeb_yoy", "200002MM", "10.9", "社会消费品零售总额累计增长")
        self.assertEqual(monthly[0]["value"], "10.5")
        self.assertEqual(cumulative[0]["value"], "10.9")
        self.assertEqual(self.parse("retail_janfeb_yoy", "200003MM", "10.4", "社会消费品零售总额累计增长"), [])
        self.assertTrue(self.parse("industry_yoy", "201202MM", "11.4", "工业增加值同比增长"))
        with self.assertRaises(ValueError):
            self.parse("industry_yoy", "201302MM", "9.9", "工业增加值同比增长")

    def test_historical_food_definition_and_missing(self):
        name = "食品类居民消费价格指数(上年同月=100)"
        rows = self.parse("food_cpi_yoy", "200012MM", "99.9", name, "index100")
        self.assertEqual((rows[0]["series_id"], rows[0]["value"]), ("food_cpi_legacy_yoy", "-0.1"))
        with self.assertRaises(ValueError):
            self.parse("food_cpi_yoy", "199001MM", "", name, "index100")
        mixed = payload("200101MM", "99.6", name)
        mixed["data"].extend(payload("199001MM", "", name)["data"])
        parsed = parse_monthly(mixed, {"id": ("food_cpi_yoy", name, "%", "index100", "")}, {"cid": "source"})
        self.assertEqual(len(parsed), 1)

    def test_release_columns_and_year_rollover(self):
        html = '''<div class="txt-content"><table>
            <tr><td rowspan="2"></td><td colspan="2">12月</td><td rowspan="2">累计同比涨跌幅</td></tr>
            <tr><td>环比涨跌幅（%）</td><td>同比涨跌幅（%）</td></tr>
            <tr><td>非食品</td><td>0.1</td><td>1.1</td><td>1.0</td></tr>
            <tr><td>服务</td><td>0.0</td><td>2.1</td><td>2.0</td></tr>
            <tr><td>其中：不包括食品和能源</td><td>0.1</td><td>1.6</td><td>1.5</td></tr>
            </table></div>'''
        rows = parse_release(html, URL, "12月份居民消费价格月度报告", "2017-01-16")
        self.assertEqual({r["period"] for r in rows}, {"2016-12"})
        self.assertEqual({r["series_id"]: r["value"] for r in rows},
            dict(nonfood_cpi_yoy="1.1", services_cpi_yoy="2.1", core_cpi_yoy="1.6"))

    def test_old_prose_yoy_does_not_take_food_mom(self):
        html = '''<div class="txt-content">2001年12月份，全国居民消费价格总水平比上年同月下降0.3%。
            食品类价格比上月上涨0.3%。服务项目价格比上年同月上涨3.8%。</div>'''
        rows = parse_release(html, URL, "2001年12月份居民消费价格月度报告", "2002-01-16")
        self.assertEqual([(r["series_id"], r["value"]) for r in rows], [("services_cpi_yoy", "3.8")])

    def test_service_subcategory_is_not_all_services(self):
        html = '''<div class="txt-content">10月份，全国居民消费价格同比上涨0.2%。
            家庭设备用品及服务价格同比下降2.4%。10月份，服务项目价格同比上涨4.2%。</div>'''
        rows = parse_release(html, URL, "2001年10月份居民消费价格月度报告", "2001-11-13")
        self.assertEqual([(r["series_id"], r["value"]) for r in rows], [("services_cpi_yoy", "4.2")])

    def test_comparison_month_is_not_observation_month(self):
        html = '''<div class="txt-content">1月份，居民消费价格同比上涨1.5%。
            非食品价格上涨0.5%；服务项目价格上涨0.2%。从月环比看，比2009年12月份上涨0.6%。</div>'''
        rows = parse_release(html, URL, "1月份居民消费价格同比上涨1.5%", "2010-02-11")
        self.assertEqual({r["period"] for r in rows}, {"2010-01"})

    def test_monthly_cpi_inside_janfeb_economy_report(self):
        html = '''<div class="txt-content"><p>1-2月份，规模以上工业增加值同比增长20.7%。</p>
            <p>2月份，居民消费价格同比上涨2.7%，涨幅比上月扩大1.2个百分点。
            非食品价格上涨1.0%；服务项目价格上涨1.7%。1-2月份，居民消费价格同比上涨2.1%。</p></div>'''
        rows = parse_economy_release(html, URL, "1-2月份国民经济主要指标数据", "2010-03-11")
        self.assertEqual({r["period"] for r in rows}, {"2010-02"})
        self.assertEqual({r["series_id"]: r["value"] for r in rows},
                         {"nonfood_cpi_yoy": "1.0", "services_cpi_yoy": "1.7"})

    def test_quarterly_economy_appendix_keeps_monthly_column(self):
        html = '''<div class="txt-content"><p>一季度居民消费价格同比上涨2.2%。</p><table>
            <tr><td rowspan="2">指标</td><td colspan="2">3月</td><td colspan="2">1-3月</td></tr>
            <tr><td>绝对量</td><td>同比增长（%）</td><td>绝对量</td><td>同比增长（%）</td></tr>
            <tr><td>六、居民消费价格</td><td>…</td><td>2.4</td><td>…</td><td>2.2</td></tr>
            <tr><td>非食品</td><td>…</td><td>1.0</td><td>…</td><td>0.8</td></tr>
            <tr><td>服务项目</td><td>…</td><td>1.3</td><td>…</td><td>1.1</td></tr>
            </table></div>'''
        rows = parse_economy_release(html, URL, "一季度国民经济情况", "2010-04-15")
        self.assertEqual({r["period"] for r in rows}, {"2010-03"})
        self.assertEqual({r["series_id"]: r["value"] for r in rows},
                         {"nonfood_cpi_yoy": "1.0", "services_cpi_yoy": "1.3"})

    def test_economy_combined_months_are_not_single_month(self):
        for separator in ("-", "—", "－", "–", "至", "～", "、"):
            html = f'''<div class="txt-content"><p>1{separator}2月份，居民消费价格同比上涨2.1%。
                非食品价格上涨0.7%；服务项目价格上涨1.0%。</p></div>'''
            self.assertEqual(parse_economy_release(html, URL, "国民经济报告", "2010-03-11"), [])

    def test_economy_price_index_matches_monthly_prose(self):
        html = '''<div class="txt-content"><p>7月份，居民消费价格同比下降1.8%。
            非食品价格下降2.1%；服务项目价格下降1.4%。1-7月份，居民消费价格同比下降1.2%。</p>
            <table><tr><td rowspan="2">指标</td><td colspan="2">7月</td><td colspan="2">1-7月</td></tr>
            <tr><td>绝对量</td><td>同比增长（%）</td><td>绝对量</td><td>同比增长（%）</td></tr>
            <tr><td>四、居民消费价格指数</td><td>…</td><td>98.2</td><td>…</td><td>98.8</td></tr>
            <tr><td>非食品</td><td>…</td><td>97.9</td><td>…</td><td>98.5</td></tr>
            <tr><td>服务项目</td><td>…</td><td>98.6</td><td>…</td><td>98.7</td></tr>
            </table></div>'''
        for label in ("居民消费价格指数", "居民消费价格(上年同期=100)"):
            rows = parse_economy_release(html.replace("居民消费价格指数", label), URL,
                                         "7月份国民经济主要指标数据", "2009-08-11")
            self.assertEqual({r["series_id"]: r["value"] for r in rows},
                             {"nonfood_cpi_yoy": "-2.1", "services_cpi_yoy": "-1.4"})


if __name__ == "__main__":
    unittest.main()

"""Historical market data must keep definitions and reject incomplete imports."""

from datetime import date
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import macro_market_history as market
import macro_repo_history as repo

URL = "https://www.pbc.gov.cn/announcement"
STAMP = "2020-01-02"


def document(body):
    # The real PBC page has a layout table outside the article's data tables.
    return f'<html><table><tr><td><span>{STAMP}</span><div id="zoom">{body}</div></td></tr></table></html>'


def table(tenor="7天", rate="2.50%", header="操作利率", amount="100亿元"):
    return (f'<table><tr><th>期限</th><th>{header}</th><th>操作量</th></tr>'
            f'<tr><td>{tenor}</td><td>{rate}</td><td>{amount}</td></tr></table>')


class RepoHistoryContract(unittest.TestCase):
    def parse(self, body):
        return repo.parse_announcement(document(body), URL, STAMP)

    def test_reverse_seven_day_only(self):
        rows, _ = self.parse("逆回购操作" + table("14天", "2.75%") + table())
        self.assertEqual([(r["period"], r["value"]) for r in rows], [(STAMP, "2.50")])
        self.assertEqual(self.parse("正回购操作" + table()), ([], "no_reverse"))
        self.assertEqual(self.parse("逆回购操作" + table("14天")), ([], "no_7day"))
        self.assertEqual(self.parse("今日无逆回购操作。MLF操作情况" + table("1年", "3.30%"))[0], [])
        self.assertEqual(self.parse("今日不开展逆回购操作。SLO操作情况" + table())[0], [])

    def test_mixed_operation_document_uses_section_heading(self):
        body = "<p>今日开展正回购和逆回购</p><p>正回购交易情况</p>" + table(rate="3.0%")
        body += "<p>逆回购交易情况</p>" + table(rate="2.5%")
        rows, _ = self.parse(body)
        self.assertEqual([r["value"] for r in rows], ["2.5"])

    def test_zero_operation_and_missing_rate_are_not_zero_interest(self):
        for body in ("逆回购操作" + table(amount="0亿元"),
                     "逆回购操作" + table(amount="0.00").replace("操作量", "操作量（亿元）"),
                     "逆回购操作" + table(rate="—"),
                     "7天逆回购操作量为零，没有公布操作利率"):
            with self.subTest(body=body):
                self.assertEqual(self.parse(body)[0], [])
        self.assertEqual(self.parse("逆回购操作" + table(rate="0%"))[0][0]["value"], "0")

    def test_percent_unit_can_be_in_header_or_rate_cell(self):
        for rate, header in [("2.5", "中标加权平均利率（%）"), ("2. 50 ％", "操作利率"),
                             ("2.5%", "招标利率"), ("2.5%", "回购利率")]:
            with self.subTest(rate=rate):
                self.assertEqual(float(self.parse("逆回购" + table(rate=rate, header=header))[0][0]["value"]), 2.5)
        with self.assertRaisesRegex(ValueError, "percent unit"):
            self.parse("逆回购" + table(rate="2.5"))

    def test_images_and_conflicting_rates_fail(self):
        with self.assertRaisesRegex(ValueError, "Image-bearing"):
            self.parse('<img src="unreadable-table.png">')
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            self.parse("逆回购" + table() + table(rate="3.0%"))
        with self.assertRaisesRegex(ValueError, "Unrecognized.*header"):
            self.parse("逆回购" + table(header="未知报价利率"))

    def test_failed_window_cannot_be_published(self):
        record = {"url": URL, "date": STAMP, "title": "公告"}
        progress = []
        with patch.object(repo, "archive_page", return_value=([record], 1, 1)), \
             patch.object(repo.common, "fetch", return_value=b"missing article body"):
            with self.assertRaisesRegex(ValueError, "requested window incomplete"):
                repo.collect(True, progress=lambda rows, meta: progress.append(meta))
        self.assertFalse(progress[-1]["repo_7d"]["requested_window_complete"])
        self.assertEqual(len(progress[-1]["repo_7d"]["failed_urls"]), 1)

    def test_access_rejection_stops_instead_of_skipping(self):
        record = {"url": URL, "date": STAMP, "title": "公告"}
        with patch.object(repo, "archive_page", return_value=([record], 1, 1)), \
             patch.object(repo.common, "fetch", side_effect=HTTPError(URL, 403, "Forbidden", {}, None)) as fetch:
            with self.assertRaises(HTTPError):
                repo.collect(True)
            self.assertEqual(fetch.call_count, 1)

    def test_same_day_equal_rate_formats_deduplicate(self):
        records = [{"url": URL + str(i), "date": STAMP, "title": "公告"} for i in range(2)]
        html = [document("逆回购" + table(rate=value)) for value in ("2.5%", "2.50%")]
        with patch.object(repo, "archive_page", return_value=(records, 2, 1)), \
             patch.object(repo.common, "fetch", side_effect=html):
            rows, meta = repo.collect(True)
        self.assertEqual(len(rows), 1)
        self.assertTrue(meta["repo_7d"]["requested_window_complete"])
        self.assertEqual(meta["repo_7d"]["counts"]["observed_duplicate_same_rate"], 1)


class StableMarketProvenance(unittest.TestCase):
    def test_fx_same_observation_does_not_change_with_query_window(self):
        def payload(end):
            return {"data": {"startDate": "2020-01-01", "endDate": end, "searchlist": ["USD/CNY"]},
                    "records": [{"date": STAMP, "values": ["6.9"]}]}
        a = market.parse_fx_history(payload("2020-01-15"), "https://example.org/query15", date(2020, 1, 1), date(2020, 1, 15))
        b = market.parse_fx_history(payload("2020-01-31"), "https://example.org/query31", date(2020, 1, 1), date(2020, 1, 31))
        self.assertEqual(a, b)
        self.assertEqual(a[0]["source_url"], market.FX_SOURCE)

    def test_yield_observation_stable_across_daily_query_end_dates(self):
        html = ('<table><tr><th>曲线</th><th>日期</th><th>1年</th><th>10年</th></tr>'
                '<tr><td>中债国债收益率曲线</td><td>2026-09-01</td><td>1.2</td><td>1.7</td></tr></table>')
        outputs = []
        for day in (2, 3):
            class Today(date):
                @classmethod
                def today(cls):
                    return date(2026, 10, day)
            with patch.object(market, "date", Today), patch.object(market, "fetch", return_value=html):
                outputs.append(market.collect_yield_history(False))
        self.assertEqual(outputs[0][0], outputs[1][0])
        self.assertNotEqual(outputs[0][1]["yield_1y"]["query_urls"], outputs[1][1]["yield_1y"]["query_urls"])
        self.assertEqual(outputs[0][0][0]["source_url"], market.yield_source_url("2026-09-01"))

    def test_empty_yield_response_does_not_erase_recent_completed_months(self):
        with patch.object(market, "fetch", return_value="<html>error</html>"):
            with self.assertRaisesRegex(ValueError, "Empty completed ChinaBond window"):
                market.collect_yield_history(False)


if __name__ == "__main__":
    unittest.main()

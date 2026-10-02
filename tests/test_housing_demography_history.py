"""Housing/population source contracts and historical versus projected data."""

import copy
import csv
from decimal import Decimal
import gzip
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from macro_catalog import SERIES, TOPICS, topic_series
from macro_common import observation
from macro_nbs_annual import definitions, parse as parse_annual
from macro_population import GROUPS, HOUSEHOLDS, parse_fertility, parse_household_evidence
from macro_shanghai import discover_pages, discover_reports, parse_fertility as parse_shanghai
from macro_housing import CITY, parse_bis, parse_city, parse_yearbook, sales_segment
from macro_housing_wealth import EXPECTED, parse as parse_wealth, parse_metadata
from macro_render import load_topic, payload, periods_between
import sync_macro

URL = "https://example.org/data"


def encoded_csv(rows, delimiter=","):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter=delimiter)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


class AnnualSources(unittest.TestCase):
    def test_annual_identity_scope_units_and_empty_years(self):
        members = GROUPS[0][1]
        identifier, (key, name, unit) = next(iter(members.items()))
        cell = dict(_id=identifier, i_showname=name, du_name=unit, da="000000000000", value="54167")
        data = dict(success=True, data=[dict(code="1949YY", values=[cell]), dict(code="2026YY", values=[dict(cell, value="")])])
        self.assertEqual([r["period"] for r in parse_annual(data, members)], ["1949"])
        for field, wrong in [("da", "310000000000"), ("du_name", "人"), ("i_showname", "人口抽样调查样本数"), ("value", "-1")]:
            bad = copy.deepcopy(data)
            bad["data"][0]["values"][0][field] = wrong
            with self.assertRaises(ValueError):
                parse_annual(bad, members)
        with self.assertRaises(ValueError):
            parse_annual(dict(success=True, data=data["data"]*2), members)
        info = dict(cell, dp_name="本期")
        meta = dict(success=True, data=dict(total=1, list=[info]))
        definitions(meta, members)
        info["dp_name"] = "同比增减%"
        with self.assertRaises(ValueError):
            definitions(meta, members)

    def test_un_medium_variant_contains_projections_that_must_be_excluded(self):
        raw = [dict(ISO3_code="CHN", LocID="156", Location="China", Variant="Medium", Time=str(y), TFR="1.2") for y in range(1950, 2101)]
        rows = parse_fertility(gzip.compress(encoded_csv(raw)))
        self.assertEqual(len(rows), 74)
        self.assertEqual(max(r["period"] for r in rows), "2023")
        with self.assertRaises(ValueError):
            parse_fertility(gzip.compress(encoded_csv(raw[1:])))
        raw[0]["LocID"] = "344"
        with self.assertRaises(ValueError):
            parse_fertility(gzip.compress(encoded_csv(raw)))

    def test_household_sample_is_not_national_total_and_conversion_is_checked(self):
        records = json.loads(HOUSEHOLDS.read_text())
        for record in records:
            html = "<p>"+record["quotation"].replace(".", "．")+"</p>"
            rows = parse_household_evidence(html, record)
            if record["kind"] == "survey_sample":
                self.assertEqual(rows, [])
            else:
                self.assertEqual(Decimal(rows[0]["value"]), Decimal(record["count_wanhu"]))
                with self.assertRaises(ValueError):
                    parse_household_evidence(html, dict(record, count_wanhu="1"))
            with self.assertRaisesRegex(ValueError, "quotation"):
                parse_household_evidence("<p>Withdrawn</p>", record)


class ShanghaiSources(unittest.TestCase):
    def test_archive_pagination_and_report_discovery(self):
        html = 'totalPage: 4 <a href="/tjsj2/20260304/a.html" title="2025年人口监测统计资料汇编">report</a>'
        self.assertEqual(len(discover_pages(html)), 4)
        self.assertEqual(len(discover_reports(html)), 1)
        for title in ("2016年上海市卫生计生数据", "2020上海市计划生育统计资料汇编"):
            self.assertEqual(len(discover_reports(f'<a href="/tjsj2/report.html" title="{title}">report</a>')), 1)
        with self.assertRaises(ValueError):
            discover_pages("totalPage: 0")
        with self.assertRaises(ValueError):
            discover_reports("<p>error page</p>")

    def test_fertility_selects_correct_table_and_registered_scope(self):
        other = '<table><tr><td>全市</td><td>2485</td></tr></table>'
        fertility = '<h3>户籍人口生育率</h3><table><tr><td>地区</td><td>总和<br>生育率</td></tr><tr><td>全市</td><td><span>0.</span>66</td></tr></table>'
        row = parse_shanghai(other+fertility, URL, "2025年上海市人口监测统计资料汇编")
        self.assertEqual(row["value"], "0.66")
        self.assertIn("户籍", row["note"])
        with self.assertRaises(ValueError):
            parse_shanghai(fertility.replace("户籍", "常住"), URL, "2025年报告")
        with self.assertRaises(ValueError):
            parse_shanghai(fertility+fertility.replace("66", "70"), URL, "2025年报告")
        with self.assertRaises(ValueError):
            parse_shanghai("<p>户籍人口总和生育率</p>", URL, "2025年报告")


class HousingSources(unittest.TestCase):
    def test_sales_scope_transition(self):
        self.assertEqual([sales_segment(y) for y in ["1991", "2004", "2005", "2006"]], ["legacy", "legacy", "transition", "current"])

    def test_yearbook_only_fills_pre_database_history(self):
        html = '<p>平均销售价格 元/平方米</p><table>'+''.join(f'<tr><td>{y}</td><td>1000</td><td>900</td></tr>' for y in range(1991, 2005))+'</table>'
        rows = parse_yearbook(html.encode("gb18030"))
        self.assertEqual(len(rows), 18)
        self.assertEqual(max(r["period"] for r in rows), "1999")
        with self.assertRaises(ValueError):
            parse_yearbook(html.replace("平方米", "套").encode("gb18030"))

    def city_fixture(self):
        return dict(success=True, data=[dict(code=p.replace("-", "")+"MM", values=[
            dict(_id=i, i_showname=name, du_name="无", da="310000000000", value="99.5") for i, (_, name) in CITY.items()
        ]) for p in periods_between("2006-01", "2011-02", "M")])

    def test_city_index100_is_change_not_price_and_2011_is_split(self):
        data = self.city_fixture()
        rows = parse_city(data)
        self.assertEqual({r["value"] for r in rows}, {"-0.5"})
        self.assertTrue(all(r["series_id"].endswith("_legacy") == (r["period"] < "2011-01") for r in rows))
        data["data"][0]["values"][0]["da"] = "000000000000"
        with self.assertRaises(ValueError):
            parse_city(data)
        data = self.city_fixture()
        data["data"][0]["values"][0]["i_showname"] = "新建商品住宅销售价格指数(2010年=100)"
        with self.assertRaises(ValueError):
            parse_city(data)

    def test_bis_scope_break_and_source_status(self):
        raw = [dict(FREQ="Q", REF_AREA="CN", VALUE="N", UNIT_MEASURE="628", UNIT_MULT="0", TIME_PERIOD=p,
                    OBS_VALUE="100", OBS_STATUS="A", OBS_CONF="F") for p in periods_between("2005-Q2", "2016-Q2", "Q")]
        rows = parse_bis(encoded_csv(raw), "N", URL)
        self.assertEqual({r["series_id"] for r in rows}, {"housing_bis_nominal_legacy", "housing_bis_nominal_current"})
        self.assertTrue(all(r["series_id"].endswith("_legacy") == (r["period"] < "2016-Q1") for r in rows))
        raw[-1]["OBS_STATUS"] = "F"
        with self.assertRaises(ValueError):
            parse_bis(encoded_csv(raw), "N", URL)

    def wealth_fixture(self):
        rows = []
        for year in range(1979, 2026):
            for key, value in [("mnwhoui999", "1000000000000"), ("mgdproi999", "500000000000"), ("ynwhoui999", "2"), ("inyixxi999", "1" if year == 2025 else "0.5")]:
                rows.append(dict(country="CN", variable=key, percentile="p0p100", year=str(year), value=value, age="999", pop="i", data_quality="5"))
        return rows

    def test_wealth_reverses_constant_price_deflation_and_scales_ratio(self):
        raw = self.wealth_fixture()
        rows, base, _ = parse_wealth(encoded_csv(raw, ";"))
        self.assertEqual(base, "2025")
        values = {(r["series_id"], r["period"]): Decimal(r["value"]) for r in rows}
        self.assertEqual(values["housing_wealth_history", "1979"], Decimal("0.5"))
        self.assertEqual(values["housing_wealth_extension", "2025"], Decimal("1"))
        self.assertEqual(values["housing_wealth_gdp_extension", "2025"], Decimal("200"))
        self.assertNotIn(("housing_wealth_history", "2021"), values)
        with self.assertRaises(ValueError):
            parse_wealth(encoded_csv(raw[1:], ";"))
        raw[-2]["value"] = "0.02"
        with self.assertRaisesRegex(ValueError, "ratio"):
            parse_wealth(encoded_csv(raw, ";"))

    def test_wealth_metadata_is_aggregate_housing_not_net_wealth(self):
        raw = [dict(country="CN", variable=k, shortname=name, unit=unit, simpledes="Housing market value") for k, (name, unit) in EXPECTED.items()]
        parse_metadata(encoded_csv(raw, ";"))
        raw[0]["shortname"] = "Net personal wealth"
        with self.assertRaises(ValueError):
            parse_metadata(encoded_csv(raw, ";"))


class PublishedHistory(unittest.TestCase):
    def test_every_new_topic_has_full_scoped_provenance_and_real_gaps(self):
        for slug in ["population", "shanghai-population", "housing-prices", "housing-wealth"]:
            rows, meta = load_topic(slug)
            self.assertEqual({r["series_id"] for r in rows}, set(topic_series(TOPICS[slug])))
            sync_macro.validate(rows, meta["series"])
            for key in meta["coverage"]:
                periods = sorted(r["period"] for r in rows if r["series_id"] == key)
                self.assertEqual(meta["coverage"][key], dict(first=periods[0], last=periods[-1], count=len(periods)))
        rows, meta = load_topic("population")
        self.assertEqual(min(r["period"] for r in rows if r["series_id"] == "population_china"), "1949")
        self.assertEqual(max(r["period"] for r in rows if r["series_id"] == "fertility_china_un"), "2023")
        households = next(c for c in payload("population", rows, meta)["charts"] if c["id"] == "population-households")
        self.assertIn("2021", households["periods"])
        self.assertTrue(all("2021" not in v for v in households["values"].values()))

    def test_scoped_revision_noop_and_withdrawal_keep_previous_snapshot(self):
        rows, meta = load_topic("housing-wealth")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(sync_macro, "ROOT", root), patch.object(sync_macro, "render"), \
                 patch("macro_housing_wealth.collect", return_value=(rows, meta["history"])) as collector:
                def run(*args):
                    with patch.object(sys, "argv", ["sync_macro", "--topics", "housing-wealth", *args]):
                        sync_macro.main()
                run("--backfill")
                paths = list((root / "data/macro").iterdir())
                before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in paths}
                run()
                self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in paths})
                revised = copy.deepcopy(rows)
                revised[0]["value"] = str(Decimal(revised[0]["value"])+Decimal("0.01"))
                collector.return_value = revised, meta["history"]
                run()
                self.assertIn(revised[0], load_topic("housing-wealth", root)[0])
                before = {p: p.read_bytes() for p in paths}
                collector.return_value = revised[1:], meta["history"]
                with self.assertRaisesRegex(ValueError, "withdrew"):
                    run()
                self.assertEqual(before, {p: p.read_bytes() for p in paths})


if __name__ == "__main__":
    unittest.main()

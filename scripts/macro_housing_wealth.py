"""WID housing wealth estimates, separating historical reconstruction and extension."""

import csv
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import io

from macro_common import add, fetch, number
from macro_render import periods_between

DATA = "https://wid.world/bulk_download/WID_data_CN.csv"
META = "https://wid.world/bulk_download/WID_metadata_CN.csv"
DICTIONARY = "https://wid.world/codes-dictionary/"
METHOD = "https://wid.world/document/estimation-of-global-wealth-aggregates-in-wid-tn-2026-03/"
EXPECTED = {
    "mnwhoui999": ("National housing assets", "CNY"),
    "ynwhoui999": ("National housing assets", "% of GDP"),
    "mgdproi999": ("Gross domestic product", "CNY"),
    "inyixxi999": ("National income price index", ""),
}


def parse_metadata(data):
    rows = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig")), delimiter=";"))
    info = {}
    for raw in rows:
        key = raw["variable"]
        if key not in EXPECTED:
            continue
        name, unit = EXPECTED[key]
        if (key in info or raw["country"] != "CN" or raw["shortname"].strip() != name or raw["unit"] != unit):
            raise ValueError("WID metadata identity/unit changed")
        info[key] = raw
    if set(info) != set(EXPECTED) or "market value" not in info["mnwhoui999"]["simpledes"]:
        raise ValueError("WID housing definition missing/changed")
    return info


def parse(data):
    values, flags = {}, {}
    for raw in csv.DictReader(io.StringIO(data.decode("utf-8-sig")), delimiter=";"):
        key, year = raw["variable"], raw["year"]
        if key not in EXPECTED:
            continue
        if raw["country"] != "CN" or raw["percentile"] != "p0p100" or raw["age"] != "999" or raw["pop"] != "i":
            raise ValueError("WID aggregate/geography changed")
        if (key, year) in values or len(year) != 4 or not year.isascii() or not year.isdigit():
            raise ValueError("WID duplicate/invalid year")
        value = number(raw["value"])
        if value is None or value <= 0:
            raise ValueError("WID required component missing/nonpositive")
        values[key, year] = value
        flags[key, year] = raw.get("data_quality", "")
    years = sorted(y for k, y in values if k == "mnwhoui999")
    if not years or years[0] != "1979" or years != periods_between(years[0], years[-1], "A"):
        raise ValueError("WID national housing history incomplete")
    bases = sorted(y for (k, y), v in values.items() if k == "inyixxi999" and v == 1)
    if not bases or bases[-1] != years[-1]:
        raise ValueError("WID price reference year could not be verified")
    rows, audit = [], []
    for year in years:
        if any((k, year) not in values for k in EXPECTED):
            raise ValueError("WID housing conversion component missing")
        amount, deflator = values["mnwhoui999", year], values["inyixxi999", year]
        ratio, gdp = values["ynwhoui999", year], values["mgdproi999", year]
        if abs(amount/gdp-ratio) > Decimal("0.000051"):
            raise ValueError("WID GDP ratio does not reconcile at source precision")
        segment = "history" if year <= "2020" else "extension"
        nominal = (amount*deflator/Decimal(10)**12).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        note = (f"WID研究估算；含住宅及住宅土地，未扣负债，非全部房地产；源{bases[-1]}年不变价乘同年价格指数，除1e12，四舍五入到0.01万亿元；" +
                ("2021年起模型延伸，不能视为直接市场观测" if segment == "extension" else "历史重建估算，也不是官方市场普查"))
        add(rows, f"housing_wealth_{segment}", year, nominal, DATA, note=note)
        add(rows, f"housing_wealth_gdp_{segment}", year, ratio*100, DATA,
            note="同版WID住宅资产存量/年度GDP比率，原始fraction乘100；不是房地产GDP贡献占比；"+note)
        audit.append(dict(year=year, constant_price_cny=str(amount), deflator=str(deflator),
                          gdp_constant_price_cny=str(gdp), raw_gdp_ratio=str(ratio),
                          raw_quality_flag=flags["mnwhoui999", year], nominal_trillion_cny=str(nominal)))
    return rows, bases[-1], audit


def collect(backfill=False):
    info = parse_metadata(fetch(META))
    rows, base_year, audit = parse(fetch(DATA))
    metadata = {}
    for key in {r["series_id"] for r in rows}:
        extension = key.endswith("_extension")
        metadata[key] = dict(source_url=DATA, metadata_url=META, dictionary_url=DICTIONARY,
            methodology_url=METHOD, price_base_year=base_year, source_definitions=info,
            conversion="nominal trillion CNY = round(mnwhoui999 * inyixxi999 / 1e12, 2); GDP percent = ynwhoui999 * 100",
            conversion_audit=[r for r in audit if (r["year"] > "2020") == extension],
            coverage="WID中国住宅及对应土地资产总值1979年起，非全部房地产总市值；未扣房贷；原不变价按同版平减指数还原当年价",
            definition_notes=["基础研究覆盖1979—2020；2021年起为外推/模型延伸，虚线单列，不据其波动断言真实市场涨跌",
                              "历史重建也含估算，公共/企业住宅资产可能以比例补足；原data_quality标记不解释为直接观测",
                              "WID新版可能修订全历史及价格基年；每次重取完整数据与同版平减指数，不混用旧版"],
            requested_window_complete=True,
            refresh_ranges=[dict(start="2021" if extension else "1979", end=str(date.today().year) if extension else "2020")])
    print("Housing wealth:", len(rows), "observations; price base", base_year, flush=True)
    return rows, metadata

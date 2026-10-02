"""Housing prices: transaction averages, city changes and BIS scope breaks."""

import csv
from datetime import date
import io
import json
import re

from bs4 import BeautifulSoup

from macro_common import add, fetch, number
from macro_nbs_annual import collect_group, normalized
from macro_nbs_history import API, BASE, _payload
from macro_render import periods_between

AVERAGES = {
    "67851f1515504d5992b1a9d0c023f0bb": ("housing_average_all_current", "新建商品房平均销售价格(元/平方米)", "元/平方米"),
    "222b8f1e22804abaaa3b58b227f8103d": ("housing_average_residential_current", "住宅商品房平均销售价格(元/平方米)", "元/平方米"),
}
YEARBOOK = "https://www.stats.gov.cn/sj/ndsj/2005/html/F0638C.HTM"
CITY_CID = "3eb43764c74741469b745c396cf002d1"
CITY_ROOT = "327ecbb2e6b14c669da1e99e39faa24c"
CITY = {
    "732f9cca00c84facb9bb8dd8365bc0e7": ("housing_shanghai_new_mom", "新建商品住宅销售价格指数(上月=100)"),
    "fb43046325f64e3896a96b70b071d52b": ("housing_shanghai_new_yoy", "新建商品住宅销售价格指数(上年同月=100)"),
    "05dd255eb4d54986a567d523b4403676": ("housing_shanghai_used_mom", "二手住宅销售价格指数(上月=100)"),
    "11ad09962ea7497eb2ccdf2be5719a20": ("housing_shanghai_used_yoy", "二手住宅销售价格指数(上年同月=100)"),
}
BIS_METHOD = "https://www.bis.org/statistics/pp_selected_documentation.pdf"


def sales_segment(year):
    return "legacy" if year < "2005" else "transition" if year == "2005" else "current"


def parse_yearbook(data):
    soup = BeautifulSoup(data.decode("gb18030"), "html.parser")
    text = normalized(soup.get_text())
    if "平均销售价格" not in text or "元/平方米" not in text:
        raise ValueError("Historical sales-average table identity/unit changed")
    rows, seen = [], set()
    for tr in soup.find_all("tr"):
        cells = [normalized(td.get_text()) for td in tr.find_all(["td", "th"])]
        if not cells or not re.fullmatch(r"199\d", cells[0]):
            continue
        year = cells[0]
        if year in seen or len(cells) < 3:
            raise ValueError("Duplicate/incomplete historical average-price row")
        seen.add(year)
        for category, cell in zip(("all", "residential"), cells[1:3]):
            value = number(cell)
            if value is None or value <= 0:
                raise ValueError("Historical housing price missing/invalid")
            add(rows, f"housing_average_{category}_legacy", year, value, YEARBOOK,
                note="2005年鉴表6-38原值；仅补1991—1999；成交均价非同质房价；不覆盖2000年起数据库修订")
    if sorted(seen) != periods_between("1991", "1999", "A"):
        raise ValueError("Historical sales averages truncated")
    return rows


def parse_city(data):
    rows, seen = [], set()
    for item in data["data"]:
        if not re.fullmatch(r"\d{4}(0[1-9]|1[0-2])MM", item["code"]):
            raise ValueError("City house-price month invalid")
        period = item["code"][:4]+"-"+item["code"][4:6]
        for raw in item["values"]:
            identifier = raw["_id"]
            if identifier not in CITY or raw["da"] != "310000000000" or (identifier, period) in seen:
                raise ValueError("City house-price identity/geography/uniqueness changed")
            seen.add((identifier, period))
            key, name = CITY[identifier]
            if normalized(raw["i_showname"]) != name or raw["du_name"] != "无":
                raise ValueError("City price comparison/unit changed")
            value = number(raw["value"])
            if value is None:
                continue
            if not 0 < value < 1000:
                raise ValueError("City comparison index out of bounds")
            if period < "2011-01":
                key += "_legacy"
            add(rows, key, period, value-100, API,
                note=f"上海；原指标 {raw['i_showname'].strip()}；原值 {value} 减100得到涨跌幅；2011年前调查方法单列")
    for stem, _ in CITY.values():
        years = sorted(r["period"] for r in rows if r["series_id"] in (stem, stem+"_legacy"))
        if not years or years[0] != "2006-01" or years != periods_between(years[0], years[-1], "M"):
            raise ValueError("Shanghai house-price history incomplete")
    return rows


def parse_bis(data, kind, url):
    rows, seen = [], set()
    label = "nominal" if kind == "N" else "real"
    for raw in csv.DictReader(io.StringIO(data.decode("utf-8-sig"))):
        if any(raw.get(k) != v for k, v in dict(FREQ="Q", REF_AREA="CN", VALUE=kind, UNIT_MEASURE="628", UNIT_MULT="0").items()):
            raise ValueError("BIS selected series identity/unit changed")
        period = raw["TIME_PERIOD"]
        if period in seen or not re.fullmatch(r"\d{4}-Q[1-4]", period):
            raise ValueError("BIS duplicate/invalid quarter")
        seen.add(period)
        value = number(raw["OBS_VALUE"])
        if value is None:
            continue
        if value <= 0 or raw["OBS_STATUS"] != "A":
            raise ValueError("BIS missing/nonstandard observation status")
        segment = "legacy" if period < "2016-Q1" else "current"
        add(rows, f"housing_bis_{label}_{segment}", period, value, url,
            note="BIS70城代表指数，2010年=100；2016年前新建住宅，之后二手住宅；"+
                 ("按CPI平减" if kind == "R" else "名义价格指数")+f"；源状态{raw['OBS_STATUS']}，保密标记{raw['OBS_CONF']}")
    periods = sorted(r["period"] for r in rows)
    if not periods or periods[0] != "2005-Q2" or periods != periods_between(periods[0], periods[-1], "Q"):
        raise ValueError("BIS China housing history truncated")
    return rows


def collect(backfill=False):
    rows, metadata = [], {}
    batch, details = collect_group("302cec9f9b354cb3a82670d8747bea2f", AVERAGES)
    for row in batch:
        row["series_id"] = row["series_id"].removesuffix("_current")+"_"+sales_segment(row["period"])
    rows.extend(batch)
    rows.extend(parse_yearbook(fetch(YEARBOOK)))
    for original, detail in details.items():
        for segment, start, end in [("legacy", "1949", "2004"), ("transition", "2005", "2005"), ("current", "2006", str(date.today().year))]:
            key = original.removesuffix("_current")+"_"+segment
            metadata[key] = dict(detail, yearbook_url=YEARBOOK, refresh_ranges=[dict(start=start, end=end)],
                coverage="年度均价1991年起，非恒定质量房价；1991—1999取旧年鉴，2000年起数据库优先；2004年数据库修订不同于旧年鉴初值，不覆盖修订",
                definition_notes=["销售统计2005年范围变化，2004年及以前、2005转换期、2006年起分段；均价受成交结构影响"])
    meta_url = BASE+"new/queryIndicatorsByCid?cid="+CITY_CID
    info = json.loads(fetch(meta_url))
    if info.get("success") is not True:
        raise ValueError("City housing metadata unavailable")
    records = {r["_id"]: r for r in info["data"]["list"]}
    if len(records) != info["data"]["total"]:
        raise ValueError("City housing metadata incomplete")
    for identifier, (key, name) in CITY.items():
        if normalized(records[identifier]["i_showname"]) != name or records[identifier]["du_name"] != "无":
            raise ValueError("City housing metadata identity/unit changed")
    now = date.today()
    request = dict(cid=CITY_CID, rootId=CITY_ROOT, indicatorIds=list(CITY), daCatalogId="",
        das=[dict(text="上海", value="310000000000")], dts=[f"194901MM-{now:%Y%m}MM"], showType="1")
    rows.extend(parse_city(_payload(request)))
    for identifier, (key, _) in CITY.items():
        for suffix, start, end in [("_legacy", "1949-01", "2010-12"), ("", "2011-01", f"{now:%Y-%m}")]:
            metadata[key+suffix] = dict(api_url=API, request=request, metadata_url=meta_url,
                annotation=records[identifier].get("i_annotation"), indicator_id=identifier, geography="310000000000",
                conversion="comparison index - 100", requested_window_complete=True,
                refresh_ranges=[dict(start=start, end=end)],
                coverage="上海2006年起月度；2011调查方法改革前后单列保留；普通五年换基不删除同比环比历史")
    for kind in ("N", "R"):
        url = f"https://stats.bis.org/api/v1/data/WS_SPP/Q.CN.{kind}.628?format=csv"
        batch = parse_bis(fetch(url), kind, url)
        rows.extend(batch)
        for key in {r["series_id"] for r in batch}:
            legacy = key.endswith("_legacy")
            metadata[key] = dict(source_url=url, methodology_url=BIS_METHOD, base="2010 average = 100",
                coverage="BIS代表性70城住宅指数2005Q2起；2016Q1由新建改为二手住宅，分段保留；非全国所有住房统计",
                requested_window_complete=True, refresh_ranges=[dict(start="2005-Q2" if legacy else "2016-Q1", end="2015-Q4" if legacy else f"{now.year}-Q{(now.month-1)//3+1}")])
    print("Housing prices:", len(rows), "observations", flush=True)
    return rows, metadata

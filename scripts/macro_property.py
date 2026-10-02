"""NBS developer statistics: cumulative periods and sales scope breaks."""

import json
import re
from html import unescape
from pathlib import Path

from bs4 import BeautifulSoup

from macro_common import add, fetch, number
from macro_catalog import SERIES
from macro_nbs_history import API, BASE, _cells, _payload, request_for

# Source names, units and comparison dimensions are checked before publishing.
# key stem, source stem, amount unit, amount ID, official-growth ID
GROUPS = [
    ("9206137ccf03460daa74b7799e0f3c31", [
        ("investment", "房地产投资_", "亿元", "bfb626c0dfa04afab67937c452ca9f50", "205e08cba8c2409980db58c98da91b6f"),
        ("residential_investment", "房地产住宅投资_", "亿元", "f6c2584119124db1bd7672ae7147b9e8", "21743217a484413fb02c09259cdf6bc0"),
    ]),
    ("4c5a2c305155451f99abf94e42305ba2", [
        ("funds", "房地产投资本年资金来源小计", "亿元", "d43adb048a744b60bdc1621c967a5331", "e3c3d04b40fc41348a82eb8b6fdcb28b"),
        ("domestic_loans", "房地产投资国内贷款", "亿元", "491731775fdc444393c3bc4fbe18f053", "4d609e39f8404f01aa1f7203caa32020"),
        ("self_funding", "房地产投资自筹资金", "亿元", "38e2f5a7c44043a2bb30c8a0552c9edc", "db918b1f89a2441dbee1d2cce8e76853"),
    ]),
    ("cac0766314e045ea82f69886aabd31b0", [
        ("construction", "房地产施工面积", "万平方米", "9ed8eb38cd5a4dbc8bc340883fb8754d", "ef1eeecd33c64b9ab5f6f180b3bb65d9"),
        ("starts", "房地产新开工施工面积", "万平方米", "17660a75e3494e389bad3658ff124995", "d0bfd7e4b56a4bb98cea7cfd141475d9"),
        ("completions", "房地产竣工面积", "万平方米", "a0def4ba92f94107b884c46b70adc08b", "526de94de84b4b08a898d94a212d18b8"),
    ]),
    ("0ae633cdb85f4a8397650831b2b27e50", [
        ("sales_area", "新建商品房销售面积", "万平方米", "d353226cf0434c929b6299f8d4987754", "50a37fbef1d04be68f15d82b711783bf"),
    ]),
    ("5530aa75038249fab2e5e10a9997c18b", [
        ("sales_value", "新建商品房销售额", "亿元", "090ed0c087024014a7fe903e409958df", "4617f4bb61234af9ab075b3695a1f0bf"),
    ]),
]


def normalized(value):
    return re.sub(r"\s+", "", value).replace("（", "(").replace("）", ")")


def members(group):
    result = {}
    for key, label, unit, amount_id, growth_id in group[1]:
        result[amount_id] = (f"property_{key}_ytd", f"{label}累计值({unit})", unit, "本期累计")
        result[growth_id] = (f"property_{key}_ytd_yoy", f"{label}累计增长(%)", "%", "累计同比增减%")
    return result


def verify_metadata(data, expected):
    if data.get("success") is not True:
        raise ValueError("Property metadata request failed")
    items = data["data"]["list"]
    lookup = {item["_id"]: item for item in items}
    if len(items) != data["data"]["total"] or len(lookup) != len(items):
        raise ValueError("Property metadata incomplete/duplicate")
    for identifier, (key, name, unit, comparison) in expected.items():
        item = lookup.get(identifier, {})
        if (normalized(item.get("i_showname", "")) != name or item.get("du_name") != unit
                or item.get("dp_name") != comparison):
            raise ValueError(f"Property identity/unit/comparison changed: {key}")
        if "_sales_" in key:
            note = item.get("i_annotation") or ""
            if "2005年8月" not in note or "包括期房和现房" not in note:
                raise ValueError("Property sales scope annotation changed")
    return lookup


def parse(data, expected):
    rows, observed = [], set()
    for identifier, period, value, raw in _cells(data, expected):
        key, name, unit, _ = expected[identifier]
        if normalized(raw["i_showname"]) != name or raw["du_name"] != unit:
            raise ValueError(f"Property observation identity/unit changed: {key}")
        if period.endswith("-01"):
            raise ValueError("Unexpected separate January property observation")
        if unit != "%" and value < 0:
            raise ValueError("Negative cumulative property amount/area")
        observed.add(identifier)
        note = f"来源指标：{raw['i_showname'].strip()}；年内累计，2月表示1—2月；不是单月"
        if unit == "%":
            note += "；官方可比口径增速，不从历史金额反算"
        if "_sales_" in key:
            if period < "2005-01":
                key += "_legacy"
                note += "；2004年及以前实际销售口径，独立保留"
            elif period < "2006-01":
                key += "_transition"
                note += "；2005年8月附近调整范围，整年作为转换期独立保留，不猜测边界月份"
        add(rows, key, period, value, API, note=note)
    if observed != set(expected):
        raise ValueError("Property source omitted entire indicator")
    return rows


def verify_quote(data, record):
    """Fail closed if an audited old release changes; never guess new values."""
    soup = BeautifulSoup(data, "html.parser")
    body = soup.select_one(".TRS_Editor") or soup.select_one(".txt-content") or soup
    text = BeautifulSoup(unescape(body.get_text()), "html.parser").get_text()
    if re.sub(r"\s+", "", record["source_text"]) not in re.sub(r"\s+", "", text):
        raise ValueError(f"Property historical quotation changed: {record['period']}/{record['series_id']}")
    value = number(record["value"])
    if SERIES[record["series_id"]]["unit"] == "%":
        values = {number(v) for v in re.findall(r"([+-]?\d+(?:\.\d+)?)\s*%", record["source_text"])}
        if value not in values:
            raise ValueError("Supplement growth not present in audited quotation")
    elif (record.get("original_unit") != "亿平方米" or record.get("unit") != "万平方米"
          or number(record.get("original_value")) * 10000 != value
          or record["original_value"]+record["original_unit"] not in record["source_text"]):
        raise ValueError("Supplement amount conversion/precision changed")


def supplement(rows, metadata):
    # Small, explicitly audited missing-only records; the revised database wins
    # if it subsequently supplies one of these observations.
    manifest = Path(__file__).resolve().parents[1] / "data/reference/property-early-releases.json"
    records = json.loads(manifest.read_text(encoding="utf-8"))
    observed = {(r["series_id"], r["period"]) for r in rows}
    documents = {}
    for record in records:
        key, period, url = record["series_id"], record["period"], record["source_url"]
        if (key, period) in observed:
            continue
        if url not in documents:
            documents[url] = fetch(url)
        verify_quote(documents[url], record)
        add(rows, key, period, record["value"], url,
            note="国家统计局原始公告补充数据库缺口；年内累计/全年，不是单月；保留当时公布口径和精度；" +
                 record.get("note", "直接采用官方累计同比，不从金额推算"))
        observed.add((key, period))
        metadata[key].setdefault("supplemental_releases", []).append(record)
    for key in metadata:
        metadata[key]["coverage_note"] = "现有月度目录主体自2000年起；另核验12篇早期原始公告补入29个缺失观测。新开工2000年4—11月及部分2000—2002年到位资金增速仍缺失；非1月缺口不插值。"
    return rows, metadata


def collect(backfill=False):
    rows, metadata = [], {}
    for group in GROUPS:
        cid, _ = group
        expected = members(group)
        url = BASE + "new/queryIndicatorsByCid?cid=" + cid
        definitions = verify_metadata(json.loads(fetch(url)), expected)
        request = request_for(cid, list(expected))
        batch = parse(_payload(request), expected)
        rows.extend(batch)
        for key in {r["series_id"] for r in batch}:
            original = key.removesuffix("_legacy").removesuffix("_transition")
            identifier = next(i for i, member in expected.items() if member[0] == original)
            start, end = "1949-01", request["dts"][0].split("-")[1][:6]
            end = end[:4]+"-"+end[4:6]
            if "_sales_" in key:
                if key.endswith("_legacy"):
                    end = "2004-12"
                elif key.endswith("_transition"):
                    start, end = "2005-01", "2005-12"
                else:
                    start = "2006-01"
            metadata[key] = dict(api_url=API, metadata_url=url, request=request, indicator_id=identifier,
                annotation=definitions[identifier].get("i_annotation"), comparison=expected[identifier][3],
                requested_window_complete=True, refresh_ranges=[dict(start=start, end=end)],
                coverage="查询1949年至当前月全部非缺失值；1949是查询边界，不是统计起点；1月不发布、2月为1—2月累计",
                definition_notes=["2005年销售范围变化：2004年及以前、2005转换期、2006年起分别保留，旧数据不删除",
                    "累计同比为官方可比口径：调查范围、退房和统计执法等调整后，不能由旧发布金额直接计算",
                    "施工面积是本年施工过的范围，不是新增面积或期末未完工库存；销售范围包含住宅和非住宅，不含二手房"])
        print("Property history:", cid, len(batch), flush=True)
    return supplement(rows, metadata)

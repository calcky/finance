"""NBS quarterly GDP: audited full histories, refreshed even on daily runs."""

import json
import re

from macro_common import add, fetch
from macro_nbs_history import API, BASE, _cells, _payload, request_for
from macro_render import periods_between

# key, indicator ID, exact source name, comparison period
GROUPS = [
    ("28d936104e304aa191e338eb82b6dc09", "亿元", "按当年价格计算", "1992-Q1", 0, [
        ("gdp_q_nominal", "d22612f09aeb4241bc557ef0ac61b3ba", "国内生产总值当季值(亿元)", "本期"),
        ("gdp_ytd_nominal", "8c5fab362d124fa7b91af833b3bd7397", "国内生产总值累计值(亿元)", "本期累计"),
        ("gdp_primary_q_nominal", "a26bbeef7cac49ef9162c2411e0b211e", "第一产业增加值当季值(亿元)", "本期"),
        ("gdp_secondary_q_nominal", "4c9eec4f1cdd4c138ed3a25c9cb9cbaf", "第二产业增加值当季值(亿元)", "本期"),
        ("gdp_tertiary_q_nominal", "5f9d870499024341862a97826d66ec3d", "第三产业增加值当季值(亿元)", "本期"),
    ]),
    ("f9b694c9b79e4ce5958bc88c6410fa67", "无", "按不变价格计算", "1993-Q1", 100, [
        ("gdp_q_yoy", "170e7f00f8c24ede863c0526b42ae81f", "国内生产总值指数(上年同期=100)当季值", "本期"),
        ("gdp_ytd_yoy", "f5b82b2b6ad345a29a337d256a9d5ded", "国内生产总值指数(上年同期=100)累计值", "本期累计"),
        ("gdp_primary_q_yoy", "6be0a577e9ca470c9b5bb2a20805dd97", "第一产业增加值指数(上年同期=100)当季值", "本期"),
        ("gdp_secondary_q_yoy", "db8aa034185e4b09a345bf4bb36be0eb", "第二产业增加值指数(上年同期=100)当季值", "本期"),
        ("gdp_tertiary_q_yoy", "bb45bc3960bd443caa67eb3b0118f123", "第三产业增加值指数(上年同期=100)当季值", "本期"),
    ]),
    ("2b0aa179980e41b8b636037ebae01d91", "%", "经季节调整后与上一季度", "2011-Q1", 0, [
        ("gdp_qoq_sa", "88bcaf76058e49b08a45b14a204b2d3d", "国内生产总值环比增长速度(%)", "环比增减%"),
    ]),
]


def normalized(name):
    return re.sub(r"\s+", "", name).replace("（", "(").replace("）", ")")


def verify_metadata(payload, group):
    _, unit, basis, _, _, members = group
    if payload.get("success") is not True:
        raise ValueError("GDP metadata request failed")
    items = payload["data"]["list"]
    by_id = {item["_id"]: item for item in items}
    if len(items) != payload["data"]["total"] or len(by_id) != len(items):
        raise ValueError("Incomplete/duplicate GDP metadata")
    for key, identifier, name, comparison in members:
        item = by_id.get(identifier, {})
        if (normalized(item.get("i_showname", "")) != name or item.get("du_name") != unit
                or item.get("dp_name") != comparison or basis not in item.get("i_annotation", "")):
            raise ValueError(f"GDP identity/unit/comparison/basis changed: {key}")
    return by_id


def parse(payload, group):
    _, unit, _, start, subtract, members = group
    by_id = {identifier: (key, name) for key, identifier, name, _ in members}
    rows = []
    for identifier, period, value, raw in _cells(payload, by_id, quarterly=True):
        key, name = by_id[identifier]
        if normalized(raw["i_showname"]) != name or raw["du_name"] != unit:
            raise ValueError(f"GDP observation identity/unit changed: {key}")
        if unit == "亿元" and value <= 0:
            raise ValueError("Nonpositive GDP value added")
        add(rows, key, period, value-subtract, API,
            note=f"来源指标：{raw['i_showname'].strip()}；原始值 {value}；" +
                 ("不变价同比指数减100得到增长率" if subtract else "直接采用官方值"))
    for key, _, _, _ in members:
        periods = sorted(r["period"] for r in rows if r["series_id"] == key)
        if not periods or periods[0] > start:
            raise ValueError(f"GDP history truncated: {key}")
        if periods != periods_between(periods[0], periods[-1], "Q"):
            raise ValueError(f"GDP history contains a gap: {key}")
    return rows


def collect(backfill=False):
    # Three compact histories: always reread all to catch annual/SA revisions.
    rows, metadata = [], {}
    for group in GROUPS:
        cid, unit, basis, _, subtract, members = group
        url = BASE + "new/queryIndicatorsByCid?cid=" + cid
        definitions = verify_metadata(json.loads(fetch(url)), group)
        request = request_for(cid, [m[1] for m in members], quarterly=True)
        batch = parse(_payload(request), group)
        rows.extend(batch)
        end = request["dts"][0].split("-")[1]
        for key, identifier, _, comparison in members:
            metadata[key] = dict(api=API, metadata_url=url, request=request,
                indicator_id=identifier, raw_unit=unit, comparison=comparison,
                annotation=definitions[identifier]["i_annotation"],
                conversion="index - 100" if subtract else "identity",
                coverage="官方修订后季度历史；每日全量复核；空白不补值；不混入旧公告初值",
                requested_window_complete=True,
                refresh_ranges=[dict(start="1949-Q1", end=f"{end[:4]}-Q{int(end[4:6])}")])
    return rows, metadata

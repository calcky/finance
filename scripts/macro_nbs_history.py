"""Full available NBS monthly histories, retaining statistical scope breaks.

The public API accepts a broad date range and returns empty cells before a
series exists. 1949 is a query boundary, never a claim about series inception.
"""

from datetime import date
from decimal import Decimal
import json
import re
import time

from macro_common import add, fetch, number
from macro_nbs import API, CONFIG, ROOT

QUARTER_ROOT = "a94b8b7365a94874968cabbe392cf679"
BASE = "https://data.stats.gov.cn/dg/website/publicrelease/web/external/"
# Additional CPI classifications hold comparable monthly changes, not index
# levels requiring chain linking. Their original catalogue is retained per row.
PRICE_HISTORY = [
    ("cpi_yoy", "954cfd7597e34b919ec71caf6aeead51", "4c1065dd4e984b25a21190c843551697", "1998–2015"),
    ("cpi_yoy", "9d4eec43537742a7ab5d63db97fa2f51", "e5c318ffdbbc4d38898e52b52267eb25", "2016–2020"),
    ("cpi_yoy", "809d2522b0fe4be89142650341b19083", "4ae9047687934a6390984c21d6ddab96", "2021–2025"),
    ("core_cpi_yoy", "809d2522b0fe4be89142650341b19083", "c2050e97c49a4763a6d0f0f38bf0b4ed", "2021–2025"),
    ("nonfood_cpi_yoy", "809d2522b0fe4be89142650341b19083", "728da4f1859140139194110824b700e1", "2021–2025"),
    ("services_cpi_yoy", "809d2522b0fe4be89142650341b19083", "e330ad10ab224cfda1f25db93bf04d01", "2021–2025"),
    ("cpi_mom", "bc985d1741a94451880c606022a8fe00", "384ddbda2edc47969caa98263f16231b", "2000–2015"),
    ("cpi_mom", "42132fae9f2244818f0480b4c422615c", "0dc091b5194c46afaf10369d5c55676a", "2016–2020"),
    ("cpi_mom", "e6664817f0cd427783cd397770695634", "e437d965279d41ceb9ace591b62f6ffc", "2021–2025"),
]
COMBINED = [
    ("industry_janfeb_yoy", "3f2e14f0542348ed9fe02476eca3450b", "21e7072e9f384209aedb56e69a18216e", "工业增加值累计增长"),
    ("retail_janfeb_yoy", "d0cb882c7f27443ab6b3ef9421901961", "e3ca151b53d347b78d1e179e5ebf1d33", "社会消费品零售总额累计增长"),
]


def request_for(cid, identifiers, quarterly=False):
    today = date.today()
    suffix = "SS" if quarterly else "MM"
    end = f"{today.year}{((today.month - 1) // 3 + 1) if quarterly else today.month:02d}{suffix}"
    return dict(cid=cid, indicatorIds=identifiers, daCatalogId="",
                das=[dict(text="全国", value="000000000000")],
                dts=[f"194901{suffix}-{end}"], showType="1",
                rootId=QUARTER_ROOT if quarterly else ROOT)


def _payload(request):
    time.sleep(2)
    result = json.loads(fetch(API, request))
    if result.get("success") is not True or not isinstance(result.get("data"), list):
        raise ValueError("NBS historical response failed")
    return result


def _cells(payload, expected, quarterly=False):
    seen = set()
    pattern = r"\d{4}0[1-4]SS" if quarterly else r"\d{4}(0[1-9]|1[0-2])MM"
    for item in payload["data"]:
        code = item["code"]
        if not re.fullmatch(pattern, code):
            raise ValueError(f"Unexpected NBS history period: {code}")
        period = f"{code[:4]}-Q{int(code[4:6])}" if quarterly else f"{code[:4]}-{code[4:6]}"
        for raw in item["values"]:
            identifier = raw["_id"]
            if identifier not in expected or raw["da"] != "000000000000":
                raise ValueError("NBS historical indicator/geography changed")
            if (identifier, period) in seen:
                raise ValueError("NBS historical duplicate observation")
            seen.add((identifier, period))
            value = number(raw["value"])
            if value is not None:
                yield identifier, period, value, raw


def parse_monthly(payload, members, request):
    """members maps indicator ID to (series, expected name, unit, transform, segment)."""
    rows, observed = [], set()
    for identifier, period, value, raw in _cells(payload, members):
        observed.add(identifier)
        key, expected, unit, transform, segment = members[identifier]
        name = re.sub(r"\s+", "", raw["i_showname"]).replace("（", "(").replace("）", ")")
        if expected not in name or (unit is not None and raw["du_name"] != unit):
            raise ValueError(f"NBS history identity/unit mismatch: {key}: {name}")
        note = f"来源指标：{raw['i_showname'].strip()}；原始值 {value}；目录 {request['cid']}"
        if segment:
            note += f"；分类版本 {segment}"
        if transform == "index100":
            basis = "上月=100" if key == "cpi_mom" else "上年同月=100"
            if basis not in name or not 0 < value < 1000:
                raise ValueError("Wrong historical price comparison basis")
            value -= 100
            note += "；比较指数减100得到涨跌幅，保留官方各期权重/分类"
        elif transform == "usd100m":
            value /= Decimal(100000)
            note += "；千美元除以100000得到亿美元"
        if key == "m1_yoy" and period < "2025-01":
            key = "m1_old_yoy"
            note += "；2025年前旧M1定义，与新定义单独保存"
        if key == "investment_ytd_yoy" and period < "2011-01":
            key = "investment_legacy_ytd_yoy"
            note += "；2011年前旧范围/起报点，与现行口径分列"
        if key == "food_cpi_yoy" and period < "2001-01":
            key = "food_cpi_legacy_yoy"
            note += "；2000年及以前食品中含烟酒，与后期食品范围分列"
        if key in ("industry_janfeb_yoy", "retail_janfeb_yoy"):
            if not period.endswith("-02"):
                continue
            note += "；YYYY-02表示当年1—2月累计同比，不是2月单月"
        elif key == "industry_yoy":
            # The source monthly series has actual February values before2013;
            # after2013 those cells are empty. Never remove valid early data.
            if period >= "2013-01" and period[-2:] in ("01", "02"):
                raise ValueError("Unexpected separate Jan/Feb industrial observation after2013")
            note += "；2011年规上起点从500万元提高至2000万元；2013年起1—2月合并调查"
        add(rows, key, period, value, API, note=note)
    if observed != set(members):
        raise ValueError(f"NBS historical catalogue omitted indicators: {set(members) - observed}")
    return rows


def refresh_range(key, cid, request):
    start_code, end_code = request["dts"][0].split("-")
    start, end = start_code[:4] + "-" + start_code[4:6], end_code[:4] + "-" + end_code[4:6]
    classifications = {
        "954cfd7597e34b919ec71caf6aeead51": ("1949-01", "2015-12"),
        "bc985d1741a94451880c606022a8fe00": ("1949-01", "2015-12"),
        "9d4eec43537742a7ab5d63db97fa2f51": ("2016-01", "2020-12"),
        "42132fae9f2244818f0480b4c422615c": ("2016-01", "2020-12"),
        "809d2522b0fe4be89142650341b19083": ("2021-01", "2025-12"),
        "e6664817f0cd427783cd397770695634": ("2021-01", "2025-12"),
    }
    if cid in classifications:
        start, end = classifications[cid]
    elif cid in ("5c7452825c7c4dcba391db5ca7f335c5", "b4fad2cf9e0e4af7815b7e9e2e95c5c7"):
        start = "2026-01"
    if key == "m1_old_yoy":
        end = "2024-12"
    elif key == "m1_yoy":
        start = "2025-01"
    elif key == "investment_legacy_ytd_yoy":
        end = "2010-12"
    elif key == "investment_ytd_yoy":
        start = "2011-01"
    elif key == "food_cpi_legacy_yoy":
        end = "2000-12"
    elif key == "food_cpi_yoy":
        start = "2001-01"
    return {"start": start, "end": end}


def collect(backfill=False):
    """Refresh complete source ranges; small monthly histories need no truncation."""
    groups = {}
    for key, (cid, identifier, expected, unit, transform, _) in CONFIG.items():
        groups.setdefault(cid, {})[identifier] = (key, expected, unit, transform, "2026–" if key in {
            "cpi_yoy", "core_cpi_yoy", "nonfood_cpi_yoy", "services_cpi_yoy", "cpi_mom"} else "")
    for key, cid, identifier, segment in PRICE_HISTORY:
        expected, unit, transform = CONFIG[key][2:5]
        groups.setdefault(cid, {})[identifier] = (key, expected, unit, transform, segment)
    for key, cid, identifier, expected in COMBINED:
        groups.setdefault(cid, {})[identifier] = (key, expected, "%", "identity", "")
    rows, details = [], {}
    for cid, members in groups.items():
        request = request_for(cid, list(members))
        batch = parse_monthly(_payload(request), members, request)
        if not batch:
            raise ValueError(f"NBS empty historical catalogue: {cid}")
        expected_keys = {member[0] for member in members.values()}
        for current, legacy in [("m1_yoy", "m1_old_yoy"),
                                ("investment_ytd_yoy", "investment_legacy_ytd_yoy"),
                                ("food_cpi_yoy", "food_cpi_legacy_yoy")]:
            if current in expected_keys:
                expected_keys.add(legacy)
        missing_keys = expected_keys - {r["series_id"] for r in batch}
        if missing_keys:
            raise ValueError(f"NBS historical definition segment missing: {missing_keys}")
        rows.extend(batch)
        for key in {r["series_id"] for r in batch}:
            detail = details.setdefault(key, dict(api_url=API, requests=[], refresh_ranges=[],
                coverage_note="查询1949年至当前期间的全部可用非缺失值；最早观测不等于官方统计创始日期；缺失不填零。"))
            detail["requests"].append(request)
            # Use source-classification bounds, not observed bounds, so a
            # withdrawn boundary observation is refreshed too.
            detail["refresh_ranges"].append(refresh_range(key, cid, request))
        print("NBS history:", cid, len(batch), "observations", flush=True)
    for key in ("core_cpi_yoy", "nonfood_cpi_yoy", "services_cpi_yoy"):
        details[key]["coverage_note"] += "此JSON目录提供2021年起数据；独立历史公告采集器补充2021年前可核验的月度记录，未找到的早期分项保留缺口，不宣称2021为官方首次发布。"
    details["industry_yoy"]["structural_breaks"] = [
        {"period": "2011-01", "note": "规模以上企业起点由年主营业务收入500万元提高至2000万元"},
        {"period": "2013-01", "note": "1—2月一起调查和发布，不再公布2月单月"}]
    keys = [(r["series_id"], r["period"]) for r in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("Overlapping NBS historical classifications")
    return sorted(rows, key=lambda r: (r["series_id"], r["period"])), details


def collect_income_api():
    """Source amount since2013Q1 and explicitly real growth since2014Q1.

    2013Q4 returns10.9 despite the catalogue real-growth annotation. Exclude
    that ambiguous cell; the wrapper uses the verified original release.
    """
    cid = "ec2d57ed282f456e8d025aff035b4fad"
    identifiers = {"bb5699c5ad534b568cca7c946227225a": "income_ytd",
                   "7abcbb6f7c844b669d43da985d3f6ff2": "income_real_ytd_yoy"}
    metadata_url = BASE + "new/queryIndicatorsByCid?cid=" + cid
    time.sleep(2)
    metadata = json.loads(fetch(metadata_url))
    records = {v["_id"]: v for v in metadata["data"]["list"]}
    if "实际增速" not in records["7abcbb6f7c844b669d43da985d3f6ff2"].get("i_annotation", ""):
        raise ValueError("Income growth no longer documented as real")
    request = request_for(cid, list(identifiers), quarterly=True)
    rows = []
    for identifier, period, value, raw in _cells(_payload(request), identifiers, quarterly=True):
        key = identifiers[identifier]
        if "居民人均可支配收入累计" not in re.sub(r"\s+", "", raw["i_showname"]):
            raise ValueError("NBS income identity changed")
        if raw["du_name"] != ("元" if key == "income_ytd" else "%"):
            raise ValueError("NBS income units changed")
        if key == "income_real_ytd_yoy" and period < "2014-Q1":
            continue
        add(rows, key, period, value, API, note="季度末年内累计；实际增速由目录注释明确，不从金额机械推算")
    details = {key: dict(api_url=API, request=request, metadata_url=metadata_url,
        coverage_note="金额2013Q1起；本API实际增速2014Q1起；2013Q4 API值10.9与实际增速注释不一致，排除该API值并由原始官方公告补齐，不冒充实际增速。",
        refresh_ranges=[{"start": "2013-Q1" if key == "income_ytd" else "2014-Q1",
                         "end": f"{date.today().year}-Q{(date.today().month - 1) // 3 + 1}"}])
        for key in identifiers.values()}
    return rows, details


def collect_money_level_fallback():
    """Optional NBS copy of PBC levels where direct PBC files are unavailable."""
    cid = "82130c6621a745cda3d64b090e733383"
    identifiers = {"f3c0ae453a54424489af41de315ec592": "m2", "add08d4a1ca049158166f126e169edde": "m1"}
    request = request_for(cid, list(identifiers))
    rows = []
    for identifier, period, value, raw in _cells(_payload(request), identifiers):
        if raw["du_name"] != "亿元":
            raise ValueError("NBS money level units changed")
        key = identifiers[identifier]
        if key == "m1" and period < "2025-01":
            key = "m1_old"
        add(rows, key, period, value / 10000, API,
            note="中国人民银行数据经国家统计局发布；亿元除以10000得到万亿元；M1按2025年定义变化分列")
    return rows, {key: dict(api_url=API, request=request,
        coverage_note="NBS转发央行历史金额，补充直接央行文件缺口；不替换较新央行修订。") for key in ("m2", "m1", "m1_old")}

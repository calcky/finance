"""Full official fiscal histories; annual sources never fill December cells."""

from datetime import date
import json
import re
import unicodedata

from macro_common import add, fetch, number
from macro_nbs_history import API, BASE, request_for, _payload

ANNUAL_ROOT = "884c062607104a91967b22742537f44f"
# identifier: (series suffix, exact normalized source name, unit)
GROUPS = [
    ("9ab4eeaba2264792b296b6658b6472dc", "A", {
        "47768ef2d84343468356fcaf26fef62f": ("revenue_annual", "一般公共预算收入(亿元)", "亿元"),
        "bd7a970226ff40a8b030c6b9a912560b": ("expenditure_annual", "一般公共预算支出(亿元)", "亿元"),
        "1778836232b74f12986c4edba9065981": ("revenue_annual_yoy", "一般公共预算收入增长速度(%)", "%"),
        "878e412131ce40d89636b0eea8e834d9": ("expenditure_annual_yoy", "一般公共预算支出增长速度(%)", "%"),
    }),
    ("f478a1d7c27a4015b6f9af06ce6f617c", "A", {
        "dd298501e2ff4e6f9d05a27a185dc8e8": ("tax_annual", "国家税收收入(亿元)", "亿元"),
        "04e1ba1dede544698f7da5673c2d04a0": ("nontax_annual", "国家非税收入(亿元)", "亿元"),
    }),
    ("3d6a3cc9a0404bdeb78abee3891efc9e", "A", {
        "5ec0835196cf4a6baca6dc8b609cc004": ("central_debt_annual", "中央财政债务余额(亿元)", "亿元"),
    }),
    ("0083b57bb6b44d4d964b87a89192344e", "M", {
        "d615e8de42114feb9169f027e6c2dcc6": ("revenue_ytd", "国家财政收入累计值(亿元)", "亿元"),
        "03e60611a6be446099bef411599bceb0": ("revenue_ytd_yoy", "国家财政收入累计增长(%)", "%"),
    }),
    ("37564a0046c14c059382e3ad26a0d94f", "M", {
        "cbb9b066b0e84cad93d249388b258a81": ("expenditure_ytd", "国家财政支出(不含债务还本)累计值(亿元)", "亿元"),
        "8dc84fd764df46a294e54a7662b1a38a": ("expenditure_ytd_yoy", "国家财政支出(不含债务还本)累计增长(%)", "%"),
    }),
]


def compact(text):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))


def verify_metadata(data, members):
    if data.get("success") is not True:
        raise ValueError("Fiscal NBS metadata failed")
    items = data["data"]["list"]
    lookup = {v["_id"]: v for v in items}
    if len(items) != data["data"]["total"] or len(lookup) != len(items):
        raise ValueError("Fiscal NBS metadata incomplete/duplicate")
    for identifier, (key, name, unit) in members.items():
        item = lookup.get(identifier, {})
        comparison = "累计同比增减%" if unit == "%" else "本期累计"
        if (compact(item.get("i_showname", "")) != name or item.get("du_name") != unit
                or item.get("dp_name") != comparison):
            raise ValueError(f"Fiscal NBS identity/unit/comparison changed: {key}")
    return lookup


def parse(data, members, frequency):
    if data.get("success") is not True or not isinstance(data.get("data"), list):
        raise ValueError("Fiscal NBS response failed")
    rows, seen = [], set()
    for item in data["data"]:
        code = item["code"]
        pattern = r"\d{4}YY" if frequency == "A" else r"\d{4}(0[1-9]|1[0-2])MM"
        if not re.fullmatch(pattern, code):
            raise ValueError("Fiscal NBS wrong period frequency")
        period = code[:4] if frequency == "A" else code[:4]+"-"+code[4:6]
        for cell in item["values"]:
            identifier = cell["_id"]
            if identifier not in members or cell["da"] != "000000000000" or (identifier, period) in seen:
                raise ValueError("Fiscal NBS unknown geography/indicator or duplicate")
            seen.add((identifier, period))
            key, name, unit = members[identifier]
            if compact(cell["i_showname"]) != name or cell["du_name"] != unit:
                raise ValueError("Fiscal NBS cell identity/unit changed")
            value = number(cell["value"])
            if value is None:
                continue
            if unit != "%" and value < 0:
                raise ValueError("Negative fiscal amount")
            note = "来源指标："+name+"；"+("年度来源，与12月累计独立" if frequency == "A" else "年内累计；早年真实1月值保留；不是单月")
            if unit == "%":
                note += "；官方增速，不从金额重算"
            add(rows, "fiscal_"+key, period, value, API, note=note)
    return rows


def collect(backfill=False):
    rows, meta = [], {}
    for cid, frequency, members in GROUPS:
        url = BASE+"new/queryIndicatorsByCid?cid="+cid
        definitions = verify_metadata(json.loads(fetch(url)), members)
        request = request_for(cid, list(members))
        if frequency == "A":
            request.update(rootId=ANNUAL_ROOT, dts=[f"1949YY-{date.today().year}YY"])
        batch = parse(_payload(request), members, frequency)
        if {r["series_id"] for r in batch} != {"fiscal_"+m[0] for m in members.values()}:
            raise ValueError("Fiscal NBS omitted entire indicator")
        audit = None
        if backfill:
            suffix = "YY" if frequency == "A" else "MM"
            first = "1949" if frequency == "A" else "194901"
            middle_end = "1999" if frequency == "A" else "199912"
            middle_start = "2000" if frequency == "A" else "200001"
            last = request["dts"][0].split("-")[1]
            windows = [first+suffix+"-"+middle_end+suffix, middle_start+suffix+"-"+last]
            split = [row for window in windows for row in parse(_payload(dict(request, dts=[window])), members, frequency)]
            identity = lambda values: {(r["series_id"], r["period"]): r["value"] for r in values}
            if identity(batch) != identity(split) or len(split) != len(batch):
                raise ValueError("Fiscal broad/split history mismatch")
            audit = dict(windows=windows, broad_equals_split=True)
        rows.extend(batch)
        for identifier, (key, _, _) in members.items():
            selected = [r["period"] for r in batch if r["series_id"] == "fiscal_"+key]
            meta["fiscal_"+key] = dict(api_url=API, metadata_url=url, request=request,
                indicator_id=identifier, annotation=definitions[identifier].get("i_annotation"),
                requested_window_complete=True, split_validation=audit,
                refresh_ranges=[dict(start=min(selected), end=max(selected))],
                coverage_note="查询1949年至当前全部非缺失观测；查询边界不是起点。年度财政主体1950年起、非税2007年起、中央债务2005年起；月度主体1998年起，保留真实缺口。",
                definition_notes=["年度来源不一概标为决算；与财政部月报12月累计分别保存；不同期、版不能强求分项精确加总。",
                                  "2011预算外收入纳入；2015部分基金转入一般公共预算；2022留抵退税影响同比；长历史不等于口径恒定。"])
        print("Fiscal NBS:", cid, len(batch), flush=True)
    return rows, meta

"""Strict annual NBS catalogue reader shared by population and housing."""

from datetime import date
import json
import re

from macro_common import add, fetch, number
from macro_nbs_history import API, BASE, _payload

ROOT = "884c062607104a91967b22742537f44f"
PROVINCE_ROOT = "c4d82af16c3d4f0cb4f09d4af7d5888e"


def normalized(text):
    return re.sub(r"\s+", "", text).replace("（", "(").replace("）", ")")


def definitions(data, members):
    if data.get("success") is not True:
        raise ValueError("Annual NBS metadata request failed")
    items = data["data"]["list"]
    found = {i["_id"]: i for i in items}
    if len(items) != data["data"]["total"] or len(found) != len(items):
        raise ValueError("Annual NBS metadata incomplete/duplicate")
    for identifier, (key, name, unit) in members.items():
        item = found.get(identifier, {})
        if (normalized(item.get("i_showname", "")) != name or item.get("du_name") != unit
                or item.get("dp_name") != "本期"):
            raise ValueError(f"Annual identity/unit/comparison changed: {key}")
    return found


def parse(data, members, geography="000000000000"):
    if data.get("success") is not True or not isinstance(data.get("data"), list):
        raise ValueError("Annual NBS data request failed")
    rows, seen, observed = [], set(), set()
    for item in data["data"]:
        if not re.fullmatch(r"[1-9]\d{3}YY", item["code"]):
            raise ValueError("Unexpected annual NBS period")
        year = item["code"][:4]
        for cell in item["values"]:
            identifier = cell["_id"]
            if identifier not in members or cell["da"] != geography or (identifier, year) in seen:
                raise ValueError("Annual indicator/geography/uniqueness changed")
            seen.add((identifier, year))
            key, name, unit = members[identifier]
            if normalized(cell["i_showname"]) != name or cell["du_name"] != unit:
                raise ValueError("Annual observation identity/unit changed")
            value = number(cell["value"])
            if value is None:
                continue
            if unit != "‰" and value <= 0:
                raise ValueError("Nonpositive annual population/price/household size")
            add(rows, key, year, value, API,
                note=f"原指标：{cell['i_showname'].strip()}；地区代码 {geography}；保留官方历史修订与显示精度")
            observed.add(identifier)
    if observed != set(members):
        raise ValueError("Annual NBS source omitted an entire series")
    return rows


def collect_group(cid, members, *, geography="000000000000", place="全国", root=ROOT):
    url = BASE + "new/queryIndicatorsByCid?cid=" + cid
    info = definitions(json.loads(fetch(url)), members)
    request = dict(cid=cid, indicatorIds=list(members), daCatalogId="",
                   das=[dict(text=place, value=geography)], dts=[f"1949YY-{date.today().year}YY"],
                   showType="1", rootId=root)
    rows = parse(_payload(request), members, geography)
    metadata = {key: dict(api_url=API, metadata_url=url, request=request, indicator_id=identifier,
                         geography=geography, place=place, annotation=info[identifier].get("i_annotation"),
                         definition=info[identifier].get("i_mark"), raw_unit=unit,
                         requested_window_complete=True,
                         refresh_ranges=[dict(start="1949", end=str(date.today().year))])
                for identifier, (key, _, unit) in members.items()}
    print("Annual history:", place, cid, len(rows), flush=True)
    return rows, metadata

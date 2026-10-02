"""National Bureau of Statistics public JSON data and quarterly income releases."""

from datetime import date
from decimal import Decimal
import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from macro_common import add, fetch, number
from macro_catalog import SERIES

API = "https://data.stats.gov.cn/dg/website/publicrelease/web/external/stream/esData"
ROOT = "fc982599aa684be7969d7b90b1bd0e84"
# catalogue, indicator, expected identifying text, raw unit, transformation, start
CONFIG = {
    "cpi_yoy": ("5c7452825c7c4dcba391db5ca7f335c5", "53180dfb9c14411ba4b762307c85920c", "居民消费价格指数", None, "index100", "202601"),
    "core_cpi_yoy": ("5c7452825c7c4dcba391db5ca7f335c5", "71be3d43d2fb44188199840272463ae0", "不包括食品和能源", None, "index100", "202601"),
    "nonfood_cpi_yoy": ("5c7452825c7c4dcba391db5ca7f335c5", "f91a869a255949ccba0cd73cfa871340", "非食品", None, "index100", "202601"),
    "services_cpi_yoy": ("5c7452825c7c4dcba391db5ca7f335c5", "c87191b714554e9eba8c2c062abfabb4", "服务", None, "index100", "202601"),
    "cpi_mom": ("b4fad2cf9e0e4af7815b7e9e2e95c5c7", "f3904a1f5a384d54a3944ec6e2df3d1c", "居民消费价格指数", None, "index100", "202601"),
    "food_cpi_yoy": ("deccae3d6ecb4967809ab21a3c679c7f", "09373c3f8fdd428fa1b289925da6d590", "食品类居民消费价格指数", None, "index100", "202601"),
    "ppi_yoy": ("60e8b361f11c4a878c652a6487a25561", "150633e52b9a470a9a9fd1b296dd6c5b", "工业生产者出厂价格指数", None, "index100", "202601"),
    "pmi_manufacturing": ("93ffbb1aa85740d3aa2618371508b606", "a09aa989bdcf4cffa2021795722eb916", "制造业采购经理指数", "%", "identity", "202401"),
    "pmi_nonmanufacturing": ("7a64a6e25aec4a8e9dde044ecd9e2cce", "88a150208f6e4a1db8babe41ae700f66", "非制造业商务活动指数", "%", "identity", "202401"),
    "industry_yoy": ("3f2e14f0542348ed9fe02476eca3450b", "ef1b1765960d45a29b4d7c4ca91be916", "工业增加值同比增长", "%", "identity", "202401"),
    "retail_yoy": ("d0cb882c7f27443ab6b3ef9421901961", "aaac57d54d2e465d91bc9f3ea1a8618e", "社会消费品零售总额同比增长", "%", "identity", "202401"),
    "investment_ytd_yoy": ("5129067b149d4ddfbec1ffc478d35bfb", "7e570cf8071c4734a7d78d9f0a70fbe1", "固定资产投资额累计增长", "%", "identity", "202401"),
    "unemployment": ("ee3b7046b390415b9b7745e3d16f6052", "3888eac6062945a79c8a27e5f13d4953", "全国城镇调查失业率", "%", "identity", "202401"),
    "m1_yoy": ("82130c6621a745cda3d64b090e733383", "640401d3351b4b868dea28f89f410a54", "(M1)", "%", "identity", "202501"),
    "m2_yoy": ("82130c6621a745cda3d64b090e733383", "e03f2232631f41cd9d754a7d7feb4a81", "(M2)", "%", "identity", "202501"),
    "exports": ("7e11b47c828d4e4e925f1c5a98305558", "9e38b39f55a7461ea195508c1bb7dbdc", "出口总值当期值", "千美元", "usd100m", "202401"),
    "imports": ("7e11b47c828d4e4e925f1c5a98305558", "86a340fee806409ebdf4d0069bd23f29", "进口总值当期值", "千美元", "usd100m", "202401"),
    "trade_balance": ("7e11b47c828d4e4e925f1c5a98305558", "0123bdd4e85348f28efc74685a4a40e5", "进出口差额当期值", "千美元", "usd100m", "202401"),
}


def parse_json(payload, members, request):
    if payload.get("success") is not True or not isinstance(payload.get("data"), list):
        raise ValueError("NBS did not return a successful data response")
    by_id = {CONFIG[k][1]: k for k in members}
    rows, seen = [], set()
    for item in payload["data"]:
        if not re.fullmatch(r"\d{6}MM", item["code"]):
            raise ValueError("NBS unexpected period encoding")
        period = item["code"][:4] + "-" + item["code"][4:6]
        for raw in item["values"]:
            if raw["_id"] not in by_id or raw["da"] != "000000000000":
                raise ValueError("NBS changed requested indicator or geography")
            key = by_id[raw["_id"]]
            _, _, expected, unit, transform, _ = CONFIG[key]
            name = re.sub(r"\s+", "", raw["i_showname"]).replace("（", "(").replace("）", ")")
            if expected not in name or (unit is not None and raw["du_name"] != unit):
                raise ValueError(f"NBS definition/unit mismatch for {key}: {name}/{raw['du_name']}")
            if (key, period) in seen:
                raise ValueError("NBS duplicate observation")
            seen.add((key, period))
            value = number(raw["value"])
            if value is None:
                continue
            # The joint Jan-Feb production/retail value is not a February value.
            if key in ("industry_yoy", "retail_yoy") and period[-2:] in ("01", "02"):
                continue
            note = f"来源指标：{raw['i_showname'].strip()}；原始值 {value}"
            if transform == "index100":
                expected_base = "上月=100" if key == "cpi_mom" else "上年同月=100"
                if expected_base not in name or not 0 < value < 1000:
                    raise ValueError("Wrong price index base")
                value -= 100
                note += "；转换：原始比较指数减 100 得涨跌幅"
            elif transform == "usd100m":
                value /= Decimal(100000)
                note += "；转换：千美元除以 100000 得亿美元"
            add(rows, key, period, value, API, note=note)
    for key in members:
        if not any(r["series_id"] == key for r in rows):
            raise ValueError(f"NBS missing series: {key}")
    return rows


def collect_json():
    today = date.today()
    end_year, end_month = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    end = f"{end_year}{end_month:02d}"
    groups = {}
    for key, (cid, _, _, _, _, start) in CONFIG.items():
        groups.setdefault((cid, start), []).append(key)
    rows, details = [], {}
    for (cid, start), members in groups.items():
        request = dict(cid=cid, indicatorIds=[CONFIG[k][1] for k in members], daCatalogId="",
                       das=[dict(text="全国", value="000000000000")], dts=[f"{start}MM-{end}MM"], showType="1", rootId=ROOT)
        batch = parse_json(json.loads(fetch(API, request)), members, request)
        rows.extend(batch)
        for key in members:
            details[key] = {"api_url": API, "request": request, "indicator_id": CONFIG[key][1],
                            "conversion": CONFIG[key][4], "published_at": "接口未提供逐条发布日期"}
        print("NBS:", ", ".join(members), len(batch), "observations", flush=True)
    return rows, details


def parse_income(html, url, title):
    soup = BeautifulSoup(html, "html.parser")
    body = soup.select_one(".txt-content")
    if body is None:
        raise ValueError("NBS income article layout changed")
    year = re.search(r"(20\d{2})年", title)
    if not year:
        raise ValueError("Income report year missing")
    if "一季度" in title:
        quarter = 1
    elif "上半年" in title:
        quarter = 2
    elif "前三季度" in title:
        quarter = 3
    elif re.match(r"20\d{2}年(?:全年)?居民收入", title):
        quarter = 4
    else:
        raise ValueError(f"Unrecognized income reporting period: {title}")
    period = f"{year[1]}-Q{quarter}"
    publication = soup.find("meta", attrs={"name": "PubDate"})
    published = publication["content"][:10].replace("/", "-") if publication else ""
    table = body.find("table")
    if table is None or "实际" not in table.get_text():
        raise ValueError("Income table has no real-growth definition")
    for tr in table.find_all("tr"):
        cells = [re.sub(r"\s+", "", x.get_text()) for x in tr.find_all(["td", "th"], recursive=False)]
        if len(cells) >= 3 and "全国居民人均可支配收入" in cells[0] and "中位数" not in cells[0]:
            growth = re.fullmatch(r"([+-]?[\d.]+)[（(]([+-]?[\d.]+)[）)]", cells[2])
            if not growth:
                raise ValueError(f"Income nominal/real growth not recognized: {cells[2]}")
            rows = []
            for key, value in [("income_ytd", cells[1]), ("income_nominal_ytd_yoy", growth[1]), ("income_real_ytd_yoy", growth[2])]:
                add(rows, key, period, value, url, published, "季度末年内累计口径，非独立单季")
            return rows
    raise ValueError("Missing national income row")


def collect_income():
    base = "https://www.stats.gov.cn/sj/zxfb/"
    links = {}
    # A bounded crawl of the official release archive; stop after reaching 2024.
    for page in range(60):
        url = base + (f"index_{page}.html" if page else "")
        soup = BeautifulSoup(fetch(url), "html.parser")
        dates = []
        for a in soup.select("a[title][href]"):
            title = a.get("title", "")
            if "居民收入和消费支出" not in title:
                continue
            year = re.search(r"(20\d{2})年", title)
            if year:
                dates.append(int(year[1]))
                if int(year[1]) >= 2024:
                    links[urljoin(url, a["href"])] = title
        if dates and min(dates) < 2024:
            break
    if not links:
        raise ValueError("No official quarterly income releases")
    rows = []
    for url, title in sorted(links.items()):
        rows.extend(parse_income(fetch(url), url, title))
    print("NBS income:", len(rows), "observations", flush=True)
    return rows, {key: {"archive": base, "parser": "官方季度报告：全国居民人均可支配收入表，括号内为实际增速"}
                  for key in ("income_ytd", "income_nominal_ytd_yoy", "income_real_ytd_yoy")}

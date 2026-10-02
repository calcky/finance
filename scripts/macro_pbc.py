"""Official PBC, ChinaMoney and ChinaBond data; explicit, checked source schemas."""

import calendar
import csv
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO, StringIO
import json
import re
from urllib.parse import urljoin, urlencode
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup
from openpyxl import load_workbook
from macro_common import add, fetch, number


def soup_at(url):
    return BeautifulSoup(fetch(url), "html.parser")


def norm(value):
    return re.sub(r"\s+", "", str(value))


def unique_link(soup, base, label):
    links = {urljoin(base, a["href"]) for a in soup.select("a[href]") if label in a.get_text()}
    if len(links) != 1:
        raise ValueError(f"Expected one link for {label}: {links}")
    return links.pop()


def parse_workbook(data, kind, year, url):
    sheet = load_workbook(BytesIO(data), read_only=True, data_only=True).active
    cells = list(sheet.values)
    def cell(r, c):
        return cells[r-1][c-1]
    text = norm(" ".join(str(v) for row in cells for v in row if v is not None))
    rows = []
    if kind == "money":
        if "亿元" not in text or "M2" not in norm(cell(8, 1)) + norm(cell(8, 2)) + norm(cell(8, 3)):
            raise ValueError("Money supply workbook schema changed")
        if "M1" not in norm(cell(10, 1)) + norm(cell(10, 2)) + norm(cell(10, 3)):
            raise ValueError("M1 row changed")
        if year < 2025:
            raise ValueError("Old M1 definition not allowed")
    elif kind == "flow":
        if "亿元" not in text or "增量" not in text or "社会融资规模" not in text:
            raise ValueError("TSF flow workbook schema changed")
    elif kind == "stock":
        if "万亿元" not in text or "存量" not in norm(cell(6, 2)) or "增速" not in norm(cell(6, 3)):
            raise ValueError("TSF stock workbook schema changed")
    else:
        raise ValueError("Unknown workbook type")
    for month in range(1, 13):
        period = f"{year}-{month:02d}"
        # Excel numeric 2026.1 at October must not be interpreted as January.
        header = cell(6, month+3) if kind == "money" else cell(month+11, 1) if kind == "flow" else cell(5, 2*month)
        expected = Decimal(f"{year}.{month}") if kind == "stock" else Decimal(f"{year}.{month:02d}")
        if number(header) != expected:
            raise ValueError(f"Unexpected month header {header} at {period}")
        if kind == "money":
            values = [("m2", cell(8, month+3)), ("m1", cell(10, month+3))]
        elif kind == "flow":
            values = [("tsf_flow", cell(month+11, 2))]
        else:
            values = [("tsf_stock", cell(8, 2*month)), ("tsf_stock_yoy", cell(8, 2*month+1))]
        for key, raw in values:
            value = number(raw)
            if value is None:
                continue
            if kind == "money":
                value /= 10000
            add(rows, key, period, value, url, note=f"{year} 年官方统计表；" + ("亿元÷10000=万亿元" if kind == "money" else "单月增量" if kind == "flow" else "月末存量/官方同比"))
    if not rows:
        raise ValueError(f"Empty {kind} workbook")
    return rows


def collect_workbooks():
    base = "https://www.pbc.gov.cn/diaochatongjisi/116219/116319/index.html"
    root = soup_at(base)
    rows, details = [], {}
    # January may precede creation of the new year's statistics directory.
    years = {}
    for a in root.select("a[href]"):
        match = re.fullmatch(r"(20\d{2})年统计数据", a.get_text(strip=True))
        if match and 2024 <= int(match[1]) <= date.today().year:
            years[int(match[1])] = urljoin(base, a["href"])
    if not years or max(years) < date.today().year - 1:
        raise ValueError("PBC annual directory missing/restructured")
    for year, annual in sorted(years.items()):
        annual_soup = soup_at(annual)
        for category, kinds in [("货币统计概览", [("money", "货币供应量")]),
                                ("社会融资规模", [("flow", "增量"), ("stock", "存量")])]:
            if year < 2025 and category == "货币统计概览":
                continue
            category_url = unique_link(annual_soup, annual, category)
            category_soup = soup_at(category_url)
            for kind, title in kinds:
                links = set()
                for a in category_soup.select("a[href]"):
                    tr = a.find_parent("tr")
                    if a["href"].lower().endswith(".xlsx") and tr and title in tr.get_text():
                        links.add(urljoin(category_url, a["href"]))
                if len(links) != 1:
                    raise ValueError(f"PBC {year} {kind}: ambiguous attachment {links}")
                url = links.pop()
                batch = parse_workbook(fetch(url), kind, year, url)
                rows.extend(batch)
                for key in {r["series_id"] for r in batch}:
                    details.setdefault(key, {"annual_directory": base, "attachments": []})["attachments"].append(url)
                print("PBC workbook:", year, kind, len(batch), flush=True)
    return rows, details


def parse_lpr(payload, url):
    data = payload["data"]
    if data["columns"] != ["date", "open", "high", "low", "close", "volume", "1Y", "5Y"]:
        raise ValueError("LPR CSV schema changed")
    rows = []
    for row in csv.reader(StringIO(data["csv"].replace("\\r\\n", "\n"))):
        if not row:
            continue
        if len(row) != 8:
            raise ValueError("LPR row width changed")
        observed = date.fromisoformat(row[0])
        if observed.year < 2024:
            continue
        for key, col in [("lpr_1y", 6), ("lpr_5y", 7)]:
            add(rows, key, row[0][:7], row[col], url, note=f"月内观察日 {row[0]}，不是报价发布日期")
    if not rows:
        raise ValueError("Empty LPR history")
    return rows


def parse_repo(html, url):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    # The publication stamp is part of the document, not inferred from URL.
    stamp = re.search(r"(20\d{2})-(\d{2})-(\d{2})", text)
    if not stamp:
        raise ValueError("Repo publication date missing")
    rows = []
    for table in soup.find_all("table"):
        if "操作利率" not in table.get_text():
            continue
        trs = [[norm(x.get_text()) for x in tr.find_all(["td", "th"], recursive=False)] for tr in table.find_all("tr")]
        for i, cells in enumerate(trs):
            if "操作利率" in cells:
                col = cells.index("操作利率")
                for values in trs[i+1:]:
                    if values and values[0] == "7天":
                        if len(values) <= col or not values[col].endswith("%"):
                            raise ValueError("Repo rate format changed")
                        add(rows, "repo_7d", stamp[0], values[col][:-1], url, stamp[0], "7 天期实际操作；未操作日无观测")
                break
        if rows:
            break
    return rows


def collect_repo():
    base = "https://www.pbc.gov.cn/zhengcehuobisi/125207/125213/125431/125475/"
    links = set()
    for page in range(1, 4):
        url = base + ("index.html" if page == 1 else f"17081-{page}.html")
        for a in soup_at(url).select("a[href]"):
            if "公开市场业务交易公告" in a.get_text():
                links.add(urljoin(url, a["href"]))
    if not links:
        raise ValueError("No repo announcements")
    rows = []
    for url in sorted(links):
        rows.extend(parse_repo(fetch(url), url))
    if not rows:
        raise ValueError("No explicit 7-day operation rate in recent announcements")
    return rows, {"repo_7d": {"archive": base, "coverage": "首次取最近 3 页公告；后续滚动检查并保留已采集历史，不代表完整政策利率历史"}}


def parse_yields(html, url):
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for table in soup.find_all("table"):
        cells = [[norm(x.get_text()) for x in tr.find_all(["td", "th"], recursive=False)] for tr in table.find_all("tr")]
        header = next((r for r in cells if "1年" in r and "10年" in r), None)
        if header is None:
            continue
        for row in cells:
            if len(row) == len(header) and len(row) > 1 and re.fullmatch(r"\d{4}-\d{2}-\d{2}", row[1]):
                if "国债" not in row[0]:
                    raise ValueError("Wrong government yield curve")
                for key, tenor in [("yield_1y", "1年"), ("yield_10y", "10年")]:
                    add(rows, key, row[1], row[header.index(tenor)], url)
    return rows


def collect_yields():
    today = date.today()
    rows = []
    for offset in range(12, -1, -1):
        serial = today.year * 12 + today.month - 1 - offset
        year, month = serial // 12, serial % 12 + 1
        end = date(year, month, calendar.monthrange(year, month)[1])
        params = urlencode(dict(startDate=f"{year}-{month:02d}-01", endDate=end.isoformat(), gjqx=0, qxId="hzsylqx", locale="zh_CN"))
        url = "https://yield.chinabond.com.cn/cbweb-pbc-web/pbc/historyQuery?" + params
        batch = parse_yields(fetch(url), url)
        if not batch and offset > 0:
            raise ValueError(f"Empty completed yield month {year}-{month}")
        rows.extend(batch)
    return rows, {k: {"curve": "中债国债收益率曲线", "coverage": "首次最近 12 个完整月及当月；滚动更新并保留已采集历史"} for k in ("yield_1y", "yield_10y")}


def parse_fx(xml, url):
    root = ET.fromstring(xml)
    dates = {v.attrib["xid"]: datetime.strptime(v.text.strip(), "%d %b %Y").date().isoformat() for v in root.findall("./xaxis/value")}
    graphs = root.findall("./graphs/graph")
    if len(graphs) != 1 or not dates:
        raise ValueError("FX rolling chart schema changed")
    rows = []
    for value in graphs[0].findall("value"):
        add(rows, "usdcny_mid", dates[value.attrib["xid"]], value.text, url, note="中国货币网 USD/CNY 中间价滚动图；人民币/美元")
    if not rows:
        raise ValueError("Empty FX chart")
    return rows


def collect():
    rows, details = collect_workbooks()
    url = "https://www.chinamoney.com.cn/ags/ms/cm-u-bk-currency/LprChrtCSV?startDate=2019-01-01"
    rows.extend(parse_lpr(json.loads(fetch(url)), url))
    details.update({k: {"url": url, "coverage": "2024 年起月内观察值，非实际发布日"} for k in ("lpr_1y", "lpr_5y")})
    for collector in (collect_repo, collect_yields):
        batch, meta = collector()
        rows.extend(batch)
        details.update(meta)
        print(collector.__name__, len(batch), flush=True)
    url = "https://www.chinamoney.com.cn/r/cms/www/chinamoney/data/fx/ccpr-chrt-usd.xml"
    rows.extend(parse_fx(fetch(url), url))
    details["usdcny_mid"] = {"url": url, "coverage": "来源滚动窗口，首次约一年；日后保留已采集历史"}
    return rows, details

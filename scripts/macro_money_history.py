"""PBC annual monetary and AFRE tables, including archived definitions.

Annual pages expose XLSX, legacy XLS, or HTML tables. Observation periods come
from table headers; sparse annual/quarter-end observations remain sparse.
"""

from datetime import date
from decimal import Decimal
from io import BytesIO
import re
import time
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from openpyxl import load_workbook
import xlrd

from macro_common import add, fetch, number


DIRECTORY = "https://www.pbc.gov.cn/diaochatongjisi/116219/116319/index.html"
LEGACY_FLOW = "https://www.pbc.gov.cn/diaochatongjisi/116219/116225/2863562/index.html"
INITIAL_STOCK = "https://www.pbc.gov.cn/diaochatongjisi/116219/116225/2810586/index.html"
_last_fetch = 0.0


def _fetch(url):
    global _last_fetch
    time.sleep(max(0, 2 - (time.monotonic() - _last_fetch)))
    _last_fetch = time.monotonic()
    return fetch(url)


def _norm(value):
    return re.sub(r"\s+", "", str(value or ""))


def _soup(url):
    return BeautifulSoup(_fetch(url), "html.parser")


def _url(base, href):
    # Archived official links predate HTTPS; the same public path supports TLS.
    return urljoin(base, href).replace("http://www.pbc.gov.cn/", "https://www.pbc.gov.cn/")


def table_cells(data, url):
    """Read an official spreadsheet, or expand its HTML merged cells."""
    if url.endswith(".xlsx"):
        return [list(row) for row in load_workbook(BytesIO(data), read_only=True, data_only=True).active.values]
    if url.endswith(".xls"):
        sheet = xlrd.open_workbook(file_contents=data).sheet_by_index(0)
        return [sheet.row_values(i) for i in range(sheet.nrows)]
    soup = BeautifulSoup(data, "html.parser")
    result, spans = [], {}
    for i, tr in enumerate(soup.select("tr")):
        row, col = [], 0
        for td in tr.find_all(["td", "th"], recursive=False):
            while (i, col) in spans:
                row.append(spans[i, col])
                col += 1
            value = td.get_text(" ", strip=True)
            colspan, rowspan = int(td.get("colspan", 1)), int(td.get("rowspan", 1))
            for offset in range(colspan):
                text = value if offset == 0 else ""
                row.append(text)
                for below in range(1, rowspan):
                    spans[i + below, col + offset] = text
            col += colspan
        result.append(row)
    return result


def _date_headers(cells, year, kind):
    candidates = []
    for index, row in enumerate(cells):
        entries = [(col, value) for col, value in enumerate(row)
                   if re.fullmatch(rf"{year}\.(?:Q[1-4]|\d{{1,2}})", _norm(value), re.I)]
        if entries:
            candidates.append((len(entries), index, entries))
    if not candidates:
        raise ValueError(f"PBC {year} {kind}: period header missing")
    _, _, entries = max(candidates, key=lambda item: item[0])
    result = []
    for position, (col, raw) in enumerate(entries, 1):
        token = _norm(raw).upper()
        if ".Q" in token:
            month = int(token[-1]) * 3
        elif kind in ("money", "stock") and len(entries) == 12:
            # Monetary Excel headers use numeric YYYY.MM: October loses zero.
            month = position
            expected = Decimal(f"{year}.{month:02d}") if kind == "money" else Decimal(f"{year}.{month}")
            if number(raw) != expected:
                raise ValueError(f"PBC {year}: money month order changed: {raw}")
        else:
            month = int(token.split(".", 1)[1])
        if not 1 <= month <= 12:
            raise ValueError(f"PBC invalid period {raw}")
        result.append((col, f"{year}-{month:02d}", ".Q" in token))
    if len({period for _, period, _ in result}) != len(result):
        raise ValueError(f"PBC duplicate table periods {year} {kind}")
    return result


def _row(cells, predicate, description):
    matches = [row for row in cells if predicate(_norm("".join(str(v or "") for v in row[:4])))]
    if len(matches) != 1:
        raise ValueError(f"PBC {description}: expected one data row, got {len(matches)}")
    return matches[0]


def parse_table(data, kind, year, url):
    cells = table_cells(data, url)
    text = _norm("".join(str(v or "") for row in cells for v in row))
    rows = []
    if kind == "money":
        if "亿元" not in text:
            raise ValueError("PBC money unit changed")
        headers = _date_headers(cells, year, kind)
        for key, predicate in [("m2", lambda s: s.startswith("货币和准货币")),
                               ("m1" if year >= 2025 else "m1_old", lambda s: s.startswith(("货币（", "货币(", "货币Money")) and "M2" not in s)]:
            values = _row(cells, predicate, key)
            for col, period, _ in headers:
                value = number(values[col] if col < len(values) else None)
                if value is not None:
                    note = "人民银行年度统计表；月末余额，亿元÷10000=万亿元"
                    if key == "m1_old":
                        note += "；旧 M1 口径，与 2025 年新口径分列"
                    add(rows, key, period, value / 10000, url, note=note)
        if year == 2025 and "2024" in text and "可比" in text:
            headers = _date_headers(cells, 2024, "money")
            balances = _row(cells, lambda s: "余额（亿元）" in s or "余额(亿元)" in s, "restated M1")
            growth = _row(cells, lambda s: "同比增速" in s, "restated M1 growth")
            for col, period, _ in headers:
                add(rows, "m1", period, number(balances[col]) / 10000, url,
                    note="2025 年统计表附注公布的 2024 年新 M1 可比口径官方回溯余额")
                value = growth[col]
                yoy = number(str(value).rstrip("%")) * (1 if str(value).endswith("%") else 100)
                add(rows, "m1_yoy", period, yoy, url,
                    note="2025 年统计表附注公布的 2024 年新 M1 可比口径官方同比")
    elif kind == "flow":
        if "亿元" not in text or "社会融资规模" not in text:
            raise ValueError("PBC AFRE flow schema changed")
        amount_section = True
        for row in cells:
            label = _norm("".join(str(value or "") for value in row[:2]))
            if label.startswith("单位："):
                amount_section = "亿元" in label
            if not amount_section or not row or not re.fullmatch(r"\d{4}\.\d{1,2}", _norm(row[0])):
                continue
            token = _norm(row[0])
            # Flow rows use YYYY.MM; numeric October is rendered YYYY.1.
            month = int((token.split(".")[1] + "0")[:2])
            if not 1 <= month <= 12:
                raise ValueError(f"PBC flow invalid month {token}")
            if number(row[1]) is None:
                continue
            add(rows, "tsf_flow", f"{token[:4]}-{month:02d}", row[1], url,
                note="人民银行年度表公布的单月增量，亿元；不是累计增量或存量差分")
        if not rows:
            # The 2012 release is transposed: months in columns, totals in a row.
            headers = _date_headers(cells, year, "money")
            values = _row(cells, lambda s: s.startswith("社会融资规模Aggregate"), "AFRE flow")
            for col, period, _ in headers:
                if number(values[col]) is not None:
                    add(rows, "tsf_flow", period, values[col], url,
                        note="人民银行年度表公布的单月增量，亿元；原表注释明确为增量概念")
    elif kind == "stock":
        if "万亿元" not in text:
            raise ValueError("PBC AFRE stock unit changed")
        headers = _date_headers(cells, year, kind)
        values = _row(cells, lambda s: s.startswith("社会融资规模存量") and "统计表" not in s, "AFRE stock")
        for col, period, quarterly in headers:
            note = "官方存量和可比口径同比；万亿元/%"
            if quarterly:
                note += "；来源为季度末观测，未复制到其他月份"
            if number(values[col]) is not None:
                add(rows, "tsf_stock", period, number(values[col]).quantize(Decimal(".01")), url, note=note)
            if number(values[col + 1]) is not None:
                add(rows, "tsf_stock_yoy", period, number(values[col + 1]).quantize(Decimal(".1")), url, note=note)
        # 2019 tables publish official revised monthly levels and growth from
        # 2017 in appendices. Levels there use 亿元, unlike the main 万亿元 table.
        appendix = None
        for row in cells:
            label = _norm("".join(str(value or "") for value in row[:3]))
            if "表1：2017年以来" in label:
                appendix = "tsf_stock"
            elif "表2：2017年以来" in label:
                appendix = "tsf_stock_yoy"
            if appendix and len(row) > 2 and re.fullmatch(r"\d{4}\.\d{1,2}", _norm(row[1])):
                token = _norm(row[1])
                month = int((token.split(".")[1] + "0")[:2])
                value = number(row[2])
                if value is not None:
                    add(rows, appendix, f"{token[:4]}-{month:02d}", value / 10000 if appendix == "tsf_stock" else value,
                        url, note="2019 年统计表附表官方回溯：2017 年起纳入政府债券的可比社融数据")
    else:
        raise ValueError(f"Unknown PBC table kind {kind}")
    if not rows:
        raise ValueError(f"PBC {year} {kind}: no observations")
    # Repeated main-table / appendix periods use the explicit revised appendix.
    return list({(row["series_id"], row["period"]): row for row in rows}.values())


def _candidates(annual_url):
    annual = _soup(annual_url)
    categories = {_url(annual_url, a["href"]) for a in annual.select("a[href]")
                  if a.get_text(strip=True) in ("货币统计概览", "社会融资规模")}
    pages = [(annual_url, annual)] + [(url, _soup(url)) for url in sorted(categories)]
    choices = {}
    for page, soup in pages:
        for a in soup.select("a[href]"):
            url = _url(page, a["href"])
            if not re.search(r"\.(htm|xls|xlsx)$", url):
                continue
            title = a.get_text(" ", strip=True)
            if title in ("htm", "xls"):
                tr = a.find_parent("tr")
                title = tr.get_text(" ", strip=True) if tr else title
            if not any(label in title for label in ("货币供应量", "货币概览", "社会融资规模")):
                continue
            kind = "money" if "货币" in title else "stock" if "存量" in title else "flow"
            score = (2 if url.endswith(".xlsx") else 1 if url.endswith(".xls") else 0) + (10 if "供应量" in title else 0)
            if kind not in choices or score > choices[kind][0]:
                choices[kind] = (score, url)
    return {kind: url for kind, (_, url) in choices.items()}


def _ranges(periods):
    result = []
    for period in sorted(set(periods)):
        year, month = map(int, period.split("-"))
        previous = f"{year if month > 1 else year - 1}-{month - 1 if month > 1 else 12:02d}"
        if result and result[-1]["end"] == previous:
            result[-1]["end"] = period
        else:
            result.append({"start": period, "end": period})
    return result


def collect_legacy():
    """The original official flow backfill predates the annual directories."""
    rows = []
    soup = _soup(LEGACY_FLOW)
    text = _norm(soup.get_text())
    if "2002年以来社会融资规模月度数据" not in text or "亿元人民币" not in text:
        raise ValueError("PBC original monthly AFRE archive changed")
    for tr in soup.select("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"], recursive=False)]
        if len(cells) != 9 or not re.fullmatch(r"\d{4}\.\d{2}", cells[0]):
            continue
        add(rows, "tsf_flow", cells[0].replace(".", "-"), cells[1], LEGACY_FLOW,
            "2012-09-13", "人民银行公布的 2002 年起历史单月社融增量；当时统计范围，亿元")
    if len(rows) != 128 or min(row["period"] for row in rows) != "2002-01":
        raise ValueError("PBC original monthly AFRE history incomplete")
    text = _norm(_soup(INITIAL_STOCK).get_text())
    match = re.search(r"2014年末社会融资规模存量为([\d.]+)万亿元，同比增长([\d.]+)%", text)
    if not match:
        raise ValueError("PBC initial AFRE stock release changed")
    for key, value in (("tsf_stock", match[1]), ("tsf_stock_yoy", match[2])):
        add(rows, key, "2014-12", value, INITIAL_STOCK, "2015-02-10",
            "首次社融存量发布的 2014 年末观测；不是 2014 年每月数据")
    return rows


def authoritative_ranges(kind, year, key):
    """Declared table scope includes blank cells, so withdrawals are detected."""
    if year == 1999 and kind == "money":
        return [{"start": "1999-12", "end": "1999-12"}]
    if key == "m1_yoy":
        return [{"start": "2024-01", "end": "2024-12"}]
    start = 2024 if year == 2025 and key == "m1" else 2017 if year == 2019 and kind in ("stock", "flow") else year
    return [{"start": f"{start}-01", "end": f"{year}-12"}]


def collect(backfill=False):
    root = _soup(DIRECTORY)
    years = {int(match[1]): _url(DIRECTORY, a["href"]) for a in root.select("a[href]")
             if (match := re.fullmatch(r"(\d{4})年统计数据", a.get_text(strip=True)))}
    if not years or max(years) < date.today().year - 1:
        raise ValueError("PBC annual directory unavailable")
    if not backfill:
        years = {year: url for year, url in years.items() if year >= date.today().year - 1}
    rows, metadata = [], {}
    if backfill:
        rows = collect_legacy()
        for key in {row["series_id"] for row in rows}:
            points = [row for row in rows if row["series_id"] == key]
            metadata[key] = {"annual_directory": DIRECTORY, "attachments": sorted({row["source_url"] for row in points}),
                             "definition_notes": [], "refresh_ranges": _ranges(row["period"] for row in points)}
    for year, annual in sorted(years.items()):
        for kind, url in _candidates(annual).items():
            batch = parse_table(_fetch(url), kind, year, url)
            rows.extend(batch)
            expected_keys = {"tsf_flow"} if kind == "flow" else {"tsf_stock", "tsf_stock_yoy"} if kind == "stock" else {"m2", "m1" if year >= 2025 else "m1_old"}
            if kind == "money" and year == 2025:
                expected_keys.add("m1_yoy")
            for key in expected_keys:
                entry = metadata.setdefault(key, {"annual_directory": DIRECTORY, "attachments": [], "definition_notes": [], "refresh_ranges": []})
                entry["attachments"].append(url)
                entry["refresh_ranges"].extend(authoritative_ranges(kind, year, key))
            print(f"PBC history {year} {kind}: {len(batch)} observations", flush=True)
    for key, entry in metadata.items():
        entry["coverage"] = "按官方年度目录回溯；早期表的稀疏期间按原样保留" if backfill else "刷新本年与上年年度表，保留更早历史"
        if key.startswith("m1"):
            entry["definition_notes"].append("2025 年 M1 纳入个人活期存款与非银行支付机构客户备付金；新旧序列分列，新口径仅向前使用官方 2024 年回溯")
        if key == "m2":
            entry["definition_notes"].extend([
                "2011 年 10 月起包括住房公积金中心存款和非存款类金融机构在存款类金融机构的存款；不能由跨口径余额机械计算同比",
                "2018 年 1 月起以非存款机构部门持有的货币市场基金替代货币市场基金存款；官方同比使用可比口径",
                "2022 年 12 月起 M0 含流通中数字人民币；官方说明 M1、M2 增速无明显变化",
            ])
        if key.startswith("tsf"):
            entry["definition_notes"].extend([
                "2018 年 7 月纳入存款类金融机构资产支持证券与贷款核销；2018 年 9 月纳入地方政府专项债券",
                "2019 年 9 月企业债券纳入交易所企业资产支持证券；2019 年 12 月纳入国债与地方政府一般债券，采用官方回溯至 2017 年的数据",
                "2023 年 1 月纳入消费金融公司、理财公司、金融资产投资公司等三类机构；贷款及核销调整，旧历史金额不强行回算",
            ])
        if key in ("tsf_stock", "tsf_stock_yoy"):
            entry["coverage_limit"] = "已核验最早 2014 年末单点、2015 年季度末、2016 年起月末；2015 年首次发布说明提及 2002 年存量研究，但未提供可逐期提取的早期存量表，未反推余额"
    return list({(row["series_id"], row["period"]): row for row in rows}.values()), metadata

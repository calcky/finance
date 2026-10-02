"""PBC borrower/maturity RMB loan stocks, preserving changes in sector scope."""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import re

from macro_common import add, number
from macro_money_history import DIRECTORY, _soup, _url, _norm, _fetch, _date_headers, table_cells


def candidates(annual):
    soup = _soup(annual)
    categories = {_url(annual, a["href"]) for a in soup.select("a[href]")
                  if a.get_text(strip=True) == "金融机构信贷收支统计"}
    found = []
    for page, body in [(annual, soup)] + [(u, _soup(u)) for u in sorted(categories)]:
        for a in body.select("a[href]"):
            url = _url(page, a["href"])
            if not re.search(r"\.(htm|xls|xlsx)$", url, re.I):
                continue
            title = a.get_text(" ", strip=True)
            if title in ("htm", "xls", "xlsx"):
                tr = a.find_parent("tr")
                title = tr.get_text(" ", strip=True) if tr else title
            if not _norm(title).startswith("金融机构人民币信贷收支表"):
                continue
            score = (10 if "按部门" in title else 0) + (2 if url.endswith(".xlsx") else 1 if url.endswith(".xls") else 0)
            found.append((score, url))
    return max(found)[1] if found else None


def row_label(value):
    return re.sub(r"^[一二三四五六七八九十\d.、()（）]+", "", _norm(value))


def parse_loans(data, year, url):
    cells = table_cells(data, url)
    text = _norm("".join(str(v or "") for row in cells for v in row))
    if "人民币" not in text or "亿元" not in text:
        raise ValueError("Loan table currency/unit changed")
    headers = _date_headers(cells, year, "money")
    if len(headers) != 12:
        raise ValueError("Loan annual month headers incomplete")
    sector, selected = None, {}
    company = "business_legacy" if year <= 2009 else "business"
    for row in cells:
        label = row_label(row[0]) if row else ""
        field = None
        if label.startswith(("居民户贷款", "住户贷款")):
            sector, field = "household", "total"
        elif label.startswith(("非金融性公司及其他部门贷款", "非金融企业及其他部门贷款", "非金融企业及机关团体贷款", "企（事）业单位贷款", "企(事)业单位贷款")):
            sector, field = company, "total"
        elif label.startswith(("非银行业金融机构贷款", "境外贷款", "债券投资", "股权及其他投资")):
            sector = None
        elif sector:
            if label.startswith("短期贷款") and not label.startswith("短期贷款及"):
                field = "short"
            elif label.startswith("中长期贷款"):
                field = "long"
            elif label.startswith("票据融资"):
                field = "bills"
            elif sector == "household":
                for name, term in [("短期消费性贷款", "short_consumer"), ("短期经营性贷款", "short_operating"),
                                   ("中长期消费性贷款", "long_consumer"), ("中长期经营性贷款", "long_operating")]:
                    if label.startswith(name):
                        field = term
        if field:
            key = f"loan_{sector}_{field}"
            if key in selected:
                raise ValueError(f"Duplicate loan row: {key}")
            values = {period: number(row[col] if col < len(row) else None) for col, period, _ in headers}
            # XLS/XLSX publish 0.00_ in source yuan-100m units; hidden Excel
            # binary-float tails are not additional published precision.
            selected[key] = {p: v.quantize(Decimal(".01"), rounding=ROUND_HALF_UP) if v is not None else None
                             for p, v in values.items()}
    derived = set()
    for term in ("short", "long"):
        key = "loan_household_"+term
        if key not in selected:
            parts = [selected.get(key+"_consumer"), selected.get(key+"_operating")]
            if not all(parts):
                raise ValueError(f"Missing household maturity rows: {year}/{term}")
            selected[key] = {p: sum(part[p] for part in parts) if all(part[p] is not None for part in parts) else None
                             for _, p, _ in headers}
            derived.add(key)
    keys = [f"loan_household_{term}" for term in ("total", "short", "long")] + [
        f"loan_{company}_{term}" for term in ("total", "short", "long", "bills")]
    if set(keys) - selected.keys():
        raise ValueError(f"Missing loan sector/maturity rows: {year}: {set(keys)-selected.keys()}")
    periods = {p for p, v in selected["loan_household_total"].items() if v is not None}
    if not periods or periods != {f"{year}-{m:02d}" for m in range(1, len(periods)+1)}:
        raise ValueError(f"Loan table months truncated/gapped: {year}")
    rows = []
    for key in keys:
        if {p for p, v in selected[key].items() if v is not None} != periods:
            raise ValueError(f"Loan maturity missing months: {year}/{key}")
        for period in sorted(periods):
            value = selected[key][period]
            if value < 0:
                raise ValueError("Negative loan balance")
            note = "人民银行人民币信贷收支表；月末余额，亿元÷10000=万亿元；非当月新增贷款"
            if key in derived:
                note += "；同表消费性＋经营性贷款相加"
            if company == "business_legacy" and "business" in key:
                note += "；旧企业范围含非居民，独立保存"
            if 2010 <= year <= 2014 and "business" in key:
                note += "；来源称非金融企业及其他部门；境内，境外已单列"
            add(rows, key, period, value / Decimal(10000), url, note=note)
    return rows


def collect(backfill=False):
    root = _soup(DIRECTORY)
    years = {int(m[1]): _url(DIRECTORY, a["href"]) for a in root.select("a[href]")
             if (m := re.fullmatch(r"(\d{4})年统计数据", a.get_text(strip=True)))}
    if not years or max(years) < date.today().year-1:
        raise ValueError("Loan annual directory unavailable")
    # Borrower-sector tables are verified from 2007; 2005/2006 aggregate tables
    # have no comparable household split. This is an audited source boundary.
    years = {y: u for y, u in years.items() if y >= (2007 if backfill else date.today().year-1)}
    first_year = 2007 if backfill else date.today().year-1
    if set(years) != set(range(first_year, max(years)+1)):
        raise ValueError("Loan annual directory has missing years")
    rows, metadata = [], {}
    for year, annual in sorted(years.items()):
        url = candidates(annual)
        if not url:
            raise ValueError(f"Loan table not linked for {year}")
        data = _fetch(url)
        batch = parse_loans(data, year, url)
        if year < date.today().year and len(batch) != 7*12:
            raise ValueError(f"Loan completed year truncated: {year}")
        rows.extend(batch)
        for key in {r["series_id"] for r in batch}:
            entry = metadata.setdefault(key, dict(annual_directory=DIRECTORY, attachments=[], refresh_ranges=[]))
            entry["attachments"].append(url)
            entry["refresh_ranges"].append(dict(start=f"{year}-01", end=f"{year}-12"))
        print("Loan balances:", year, len(batch), flush=True)
    for detail in metadata.values():
        detail["coverage"] = "住户与企业人民币贷款余额；已核验2007年起全部年度部门表，包括2012—2014年旧HTML附件；未发布月份不填值"
        detail["definition_notes"] = ["2007—2009企业含非居民，旧序列分列；2010年起境内/境外单列",
            "2023年消费金融公司、理财公司、金融资产投资公司等三类机构纳入金融统计；不由跨范围余额计算可比增速",
            "住户与境内企业余额不穷尽全部金融机构贷款；还包括非银行金融机构和境外等借款人"]
    return rows, metadata

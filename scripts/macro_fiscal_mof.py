"""MOF HTML archives and period-aware budget execution extraction."""

from decimal import Decimal
import re
import time
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from macro_common import add, fetch, number
from macro_fiscal_nbs import compact

BUDGET = "https://gks.mof.gov.cn/tongjishuju/"
DEBT_ARCHIVES = ["https://yss.mof.gov.cn/zhuantilanmu/dfzgl/sjtj/", "https://zwgls.mof.gov.cn/tjsj/"]
ANNUAL = "https://yss.mof.gov.cn/caizhengshuju/"


def html_for(url):
    for attempt in range(2):
        try:
            return fetch(url).decode("utf-8")
        except (OSError, UnicodeError) as error:
            # A verified MOF endpoint occasionally times out or closes the
            # connection. Retry the same public GET once; never retry HTTP
            # access refusals, decode errors, or failed content validation.
            if attempt == 0 and isinstance(error, (TimeoutError, ConnectionError)):
                print("Retrying fiscal connection:", url, flush=True)
                time.sleep(2)
                continue
            raise RuntimeError("Fiscal source unavailable: "+url) from error


def soup_for(url):
    return BeautifulSoup(html_for(url), "html.parser")


def archive(base, pattern, full=True):
    """Treasury has stale active pagination; use both published page counts."""
    entries, seen, pages = [], set(), []
    url = urljoin(base, "index.htm")
    first = html_for(url)
    counts = [int(x) for x in re.findall(r"(?:var\s+countPage\s*=\s*|createPageHTML\(\s*)(\d+)", first)]
    if not counts or not 1 <= max(counts) <= 200:
        raise ValueError("MOF archive pagination missing/implausible: "+url)
    count = max(counts) if full else 1
    signatures = set()
    for page in range(count):
        url = urljoin(base, "index.htm" if page == 0 else f"index_{page}.htm")
        soup = BeautifulSoup(first, "html.parser") if page == 0 else soup_for(url)
        anchors = soup.select(".liBox a[href]")
        if not anchors:
            raise ValueError("MOF archive listing missing: "+url)
        signature = tuple(a["href"] for a in anchors)
        if signature in signatures:
            raise ValueError("MOF archive repeated page: "+url)
        signatures.add(signature)
        pages.append(url)
        for a in anchors:
            title = compact(a.get("title") or a.get_text())
            link = urljoin(url, a["href"]).replace("http:", "https:")
            if re.search(pattern, title) and link not in seen:
                seen.add(link)
                entries.append(dict(title=title, url=link))
    if not entries:
        raise ValueError("MOF archive contains no selected releases")
    return entries, pages


def article(url):
    soup = soup_for(url)
    body = soup.select_one(".my_doccontent") or soup.select_one(".TRS_Editor") or soup.select_one(".Custom_UnionStyle")
    if body is None:
        raise ValueError("MOF article body missing: "+url)
    paragraphs = [compact(p.get_text()) for p in body.find_all("p") if not p.find("p")]
    if not paragraphs:
        paragraphs = [compact(body.get_text())]
    meta = soup.find("meta", attrs={"name": re.compile("^PubDate$", re.I)})
    published = (meta.get("content", "")[:10] if meta else "")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", published):
        match = re.search(r"发布日期[:：](\d{4})年(\d{1,2})月(\d{1,2})日", compact(soup.get_text()))
        published = f"{match[1]}-{int(match[2]):02}-{int(match[3]):02}" if match else ""
    return soup, paragraphs, published


def budget_period(title):
    match = re.match(r"(\d{4})年(.*?)财政收[支入]", compact(title))
    if not match:
        raise ValueError("Unknown fiscal report title: "+title)
    suffix = re.sub(r"(?:全国)?(?:一般公共|公共)?$", "", match[2])
    digits = re.findall(r"\d+", suffix)
    month = int(digits[-1]) if digits else {"": 12, "前三季度": 9, "一季度": 3, "上半年": 6}.get(suffix)
    if month is None or not 1 <= month <= 12:
        raise ValueError("Unknown fiscal report period")
    return f"{match[1]}-{month:02}"


GENERAL = {
    "revenue_ytd": r"全国(?:一般公共预算|一般公共财政|公共财政|财政)收入(?:执行初步统计数为|为)?([\d.]+)亿元",
    "expenditure_ytd": r"全国(?:一般公共预算|一般公共财政|公共财政|财政)支出(?:执行初步统计数为|为)?([\d.]+)亿元",
    "tax_ytd": r"(?<!非)(?<!中央)(?<!地方)税收收入([\d.]+)亿元",
    "nontax_ytd": r"(?<!中央)(?<!地方)非税收入([\d.]+)亿元",
}
FUNDS = {
    "fund_revenue_ytd": r"全国政府性基金(?:预算)?收入([\d.]+)亿元",
    "fund_expenditure_ytd": r"全国政府性基金(?:预算)?支出([\d.]+)亿元",
    "land_ytd": r"(?:国有)?土地(?:使用权)?出让收入([\d.]+)亿元",
}


def parse_budget(title, paragraphs, url, published):
    period = budget_period(title)
    year, month = int(period[:4]), int(period[-2:])
    found, state = {}, None
    for piece in [s for p in paragraphs for s in re.split(r"(?<=。)", p) if s.strip()]:
        p = compact(piece).replace("\u200b", "")
        if re.match(r"(?:二[、.]|三[、.])全国(?:政府性基金|国有资本)", p):
            break
        lead = re.sub(r"^\d{4}年[,，]?", "", p)
        lead = re.sub(r"^全国(?:公共)?财政(?:收入|支出)情况", "", lead)
        cumulative = re.match(r"1[-—–至~](\d+)月", lead)
        if cumulative:
            state = "ytd" if int(cumulative[1]) == month else "other"
        elif re.match(r"(上半年|1至6月)", lead):
            state = "ytd" if month == 6 else "other"
        elif re.match(r"(前三季度|前3季度)", lead):
            state = "ytd" if month == 9 else "other"
        elif re.match(r"(一季度|第一季度)", lead):
            state = "ytd" if month == 3 else "other"
        elif lead.startswith("全年") or re.match(rf"{year}年[,，]全国", p):
            state = "ytd" if month == 12 else "other"
        elif re.match(r"\d+月份?(?:[,，、]|全国|主要收入)", lead):
            state = "ytd" if int(re.match(r"\d+", lead)[0]) == month == 1 else "month"
        if state != "ytd":
            continue
        for key, pattern in GENERAL.items():
            for match in re.finditer(pattern, p):
                before = p[max(0, match.start()-12):match.start()]
                if key in ("tax_ytd", "nontax_ytd") and re.search(r"(中央|地方)(?:本级|财政|一般公共预算)?$", before):
                    continue
                if key == "tax_ytd" and ("其他" in before or before.endswith(("各项", "等"))):
                    continue
                value = number(match[1])
                if key in found:
                    if abs(found[key][0]-value) > Decimal("0.5"):
                        raise ValueError("Conflicting national YTD amounts")
                    # Preserve the more precise duplicate (2011-03 nontax).
                    if value.as_tuple().exponent >= found[key][0].as_tuple().exponent:
                        continue
                found[key] = value, p
    if "revenue_ytd" not in found:
        raise ValueError("No national cumulative revenue: "+title)
    if {"revenue_ytd", "tax_ytd", "nontax_ytd"} <= found.keys():
        if abs(found["revenue_ytd"][0]-found["tax_ytd"][0]-found["nontax_ytd"][0]) > 1:
            raise ValueError("Fiscal tax/nontax sum mismatch")
    text = "".join(paragraphs)
    # Fund section reports YTD even where general-budget paragraphs start with
    # current-month values. Check an explicit matching cumulative period.
    section = re.split(r"[二三][、.]全国政府性基金", text, maxsplit=1)
    if len(section) == 2:
        fund = "全国政府性基金"+section[1]
        context = rf"1[-—–至~]{month}月"
        if month in (3, 6, 9, 12):
            context += "|"+{3: "一季度|第一季度", 6: "上半年", 9: "前三季度|前3季度", 12: rf"全年|{year}年[,，]"}[month]
        if any(re.search(pattern, fund) for pattern in FUNDS.values()) and not re.search(context, fund):
            raise ValueError("Fund cumulative-period context missing")
        for key, pattern in FUNDS.items():
            matches = list(re.finditer(pattern, fund))
            if len(matches) > 1:
                raise ValueError("Ambiguous fund amount")
            if matches:
                m = matches[0]
                found[key] = number(m[1]), fund[max(0, m.start()-35):m.end()+35]
    rows = []
    for key, (value, quote) in found.items():
        if value < 0:
            raise ValueError("Negative fiscal YTD amount")
        add(rows, "fiscal_"+key, period, value, url, published, "年内累计执行数，不是单月；原文："+quote)
    return rows


def collect_budget(backfill=False, supplemental_urls=()):
    entries, pages = archive(BUDGET, r"^\d{4}年.*财政收[支入]", backfill)
    listed = {e["url"] for e in entries}
    entries.extend(dict(url=url, title=None) for url in sorted(set(supplemental_urls)-listed))
    rows = []
    for e in entries:
        soup, paragraphs, published = article(e["url"])
        title = e["title"]
        if title is None:
            heading = soup.select_one("h2.title_con")
            if heading is None:
                raise ValueError("Supplement fiscal release title missing")
            title = compact(heading.get_text())
        batch = parse_budget(title, paragraphs, e["url"], published)
        if e["title"] is None:
            # This old release fills the headline database window only. Its
            # other series would falsely widen their daily refresh intervals.
            batch = [r for r in batch if r["series_id"] in {"fiscal_revenue_ytd", "fiscal_expenditure_ytd"}]
        rows.extend(batch)
    return rows, dict(archive_pages=pages, report_count=len(entries), requested_window_complete=True)

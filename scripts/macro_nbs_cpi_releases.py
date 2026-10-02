"""Backfill CPI components missing from the NBS pre2021 JSON catalogues."""

import hashlib
from html import escape
import json
import math
from pathlib import Path
import re
import time
from urllib.parse import urlencode, urlparse
from urllib.request import Request

from bs4 import BeautifulSoup
import macro_common as common
from macro_common import add, number

SEARCH = "https://api.so-gov.cn/query/s"
LABELS = {"非食品": "nonfood_cpi_yoy", "服务": "services_cpi_yoy",
          "不包括食品和能源": "core_cpi_yoy"}
# The documented public search silently wraps to page1 beyond500 hits.
# Date partitions keep every query below that search limit.
PARTITIONS = [("1900-01-01", "2010-12-31"), ("2011-01-01", "2015-12-31"),
              ("2016-01-01", "2021-01-31")]
# Verified original archive pages omitted by the current public search index.
ARCHIVE_SUPPLEMENTS = {
    "https://www.stats.gov.cn/sj/zxfb/202303/t20230301_1919188.html": {
        "title": "1-2月份国民经济主要指标数据", "published": "2010-03-11"},
}


def search_page(start, end, page, query='("居民消费价格")', title_only=True):
    body = urlencode(dict(siteCode="bm36000002", qt=query, adv="1",
        keyPlace=str(int(title_only)), sort="dateDesc", page=str(page), pageSize="20", timeOption="2",
        startDateStr=start, endDateStr=end)).encode()
    cache = None
    if common.CACHE:
        cache = Path(common.CACHE) / hashlib.sha256(SEARCH.encode() + body).hexdigest()
    if cache and cache.exists():
        return json.loads(cache.read_bytes())
    time.sleep(2)
    with common.OPENER.open(Request(SEARCH, data=body, headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "finance-educational-data/1.0"}), timeout=45) as response:
        raw = response.read()
    result = json.loads(raw)
    if result.get("ok") is not True:
        raise ValueError("Official NBS search failed")
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(raw)
    return result


def discover():
    links, queries = {}, []
    searches = [(a, b, '("居民消费价格")', True) for a, b in PARTITIONS]
    # Some2009–2011 months were published within general economic releases,
    # and title-only CPI search cannot find them. Inspect original paragraphs.
    searches.extend((a, b, '("居民消费价格")', False) for a, b in [
        ("1900-01-01", "2005-12-31"), ("2006-01-01", "2013-01-31")])
    # The search index does not consistently index article bodies: the known
    # February2010 report contains CPI prose/table but is absent above.
    # Discover general reports independently through their actual titles.
    searches.extend(("1900-01-01", "2013-01-31", query, True) for query in [
        '("国民经济")', '("主要统计数据")'])
    # Exact component searches recover pages missing from the CPI phrase
    # search, including the April/May2010 economic reports.
    searches.extend((a, b, query, False)
        for query in ['("非食品")', '("服务项目")', '("扣除食品和能源")']
        for a, b in [("1900-01-01", "2005-12-31"), ("2006-01-01", "2013-01-31")])
    # Broad searches omit some similar monthly reports even below500 hits;
    # narrower date windows demonstrably return those missing URLs.
    searches.extend((f"{year}-01-01", f"{year}-12-31", '("居民消费价格")', False)
                    for year in range(2000, 2012))
    for start, end, query, title_only in searches:
        first = search_page(start, end, 1, query, title_only)
        pages = math.ceil(first["totalHits"] / 20)
        if pages > 25:
            raise ValueError("CPI release search partition exceeds500 results; subdivide dates")
        seen_pages = set()
        for page in range(1, pages + 1):
            result = first if page == 1 else search_page(start, end, page, query, title_only)
            docs = result["resultDocs"]
            signature = tuple(r["id"] for r in docs)
            if signature in seen_pages or not docs:
                raise ValueError("Official CPI search repeated or missing page")
            seen_pages.add(signature)
            for record in docs:
                d = record["data"]
                url, title = d["url"], d["titleO"]
                if urlparse(url).hostname not in ("www.stats.gov.cn", "stats.gov.cn"):
                    continue
                if not any(path in url for path in ("/sj/zxfb/", "/sj/xwfbh/fbhwd/")):
                    continue
                if title_only and query == '("居民消费价格")' and not re.search(r"\d{1,2}月份?", title):
                    continue
                links[url] = {"title": title, "published": d["docDate"]}
        queries.append(dict(start=start, end=end, query=query, title_only=title_only,
                            total_hits=first["totalHits"], pages=pages))
        print("CPI release search:", start, end, len(links), "official links", flush=True)
    links.update(ARCHIVE_SUPPLEMENTS)
    return links, queries


def table_grid(table):
    """Expand real HTML row/column spans before selecting a comparison column."""
    grid, pending = [], {}
    for tr in table.find_all("tr"):
        row = {column: text for column, (text, remaining) in pending.items()}
        following = {column: (text, remaining - 1) for column, (text, remaining)
                     in pending.items() if remaining > 1}
        column = 0
        for cell in tr.find_all(["td", "th"], recursive=False):
            while column in row:
                column += 1
            text = re.sub(r"\s+", "", cell.get_text()).replace("％", "%")
            width, height = int(cell.get("colspan", 1)), int(cell.get("rowspan", 1))
            for position in range(column, column + width):
                row[position] = text
                if height > 1:
                    following[position] = (text, height - 1)
            column += width
        grid.append([row.get(i, "") for i in range(max(row, default=-1) + 1)])
        pending = following
    return grid


def parse_release(html, url, title, published):
    soup = BeautifulSoup(html, "html.parser")
    body = soup.select_one(".txt-content") or soup.select_one(".TRS_Editor")
    if body is None:
        raise ValueError(f"Historical CPI article layout changed: {url}")
    text = re.sub(r"\s+", "", body.get_text()).replace("％", "%")
    match = re.search(r"((?:19|20)\d{2})年(\d{1,2})月份?", title)
    if match:
        year, month = int(match[1]), int(match[2])
    else:
        month_match = re.search(r"(\d{1,2})月份?", title)
        if not month_match:
            return []
        month = int(month_match[1])
        year = int(published[:4]) - (month > int(published[5:7]))
    period = f"{year:04d}-{month:02d}"
    if not 1 <= month <= 12 or period > published[:7]:
        raise ValueError(f"Historical CPI period inconsistent with release: {title}")
    if period >= "2021-01":
        return []
    values = {}
    for table in body.find_all("table"):
        cells = table_grid(table)
        header = next((row for row in cells if any("环比" in x for x in row)
                       and any("同比" in x for x in row)), None)
        if header is None:
            continue
        raw_yoy = next(i for i, x in enumerate(header) if "同比" in x)
        for row in cells:
            if not row:
                continue
            label = re.sub(r"^其中[：:]", "", row[0])
            if label == "服务项目":
                label = "服务"
            if label not in LABELS:
                continue
            if raw_yoy >= len(row):
                raise ValueError(f"CPI historical table header alignment changed: {url}")
            cell = row[raw_yoy]
            value = number(cell)
            if value is not None:
                values[LABELS[label]] = value
    # Early releases contain prose only. Explicit YoY wording is preferred;
    # implicit comparisons are accepted only in the opening YoY paragraph.
    for label, key in LABELS.items():
        if key in values:
            continue
        # A service subcategory such as 家庭设备用品及服务 or 医疗保健服务
        # must never match the national all-services aggregate.
        noun = r"(?<![\u4e00-\u9fff])服务(?:项目)?价格" if label == "服务" else ("非食品价格" if label == "非食品"
            else "(?:扣除|不包括)食品和能源(?:价格)?(?:的|后的)?(?:核心CPI)?")
        comparison = r"(?:同比|比上年同月|比去年同月|与上年同月相比|与去年同月相比)"
        pattern = noun + comparison + r"(?:上涨|上升|增长|下降|降低|下跌)([\d.]+)%"
        explicit = re.search(pattern, text)
        if explicit:
            value = number(explicit[1])
            if any(x in explicit[0] for x in ("下降", "降低", "下跌")):
                value = -value
            values[key] = value
            continue
        opening = re.split(r"环比|比上月(?:上涨|下降|上升|下跌|持平|增长)", text, maxsplit=1)[0][:550]
        if not re.search(comparison, opening):
            continue
        implicit = re.search(noun + r"(?:同比)?(上涨|上升|增长|下降|降低|下跌)([\d.]+)%", opening)
        if implicit:
            value = number(implicit[2])
            values[key] = -value if implicit[1] in ("下降", "降低", "下跌") else value
        elif re.search(noun + r"(?:同比|比上年同月|与上年同月|比去年同月|与去年同月)?持平", opening):
            values[key] = number(0)
    rows = []
    for key, value in values.items():
        add(rows, key, period, value, url, published,
            "国家统计局原始月度CPI公告；同比涨跌幅直接使用；补充旧JSON分类目录未列出的分项")
    return rows


def article(url):
    cached = common.CACHE and (Path(common.CACHE) / hashlib.sha256(url.encode()).hexdigest()).exists()
    if not cached:
        time.sleep(2)
    return common.fetch(url)


def parse_economy_release(html, url, title, published):
    """Only the paragraph explicitly describing a single month's CPI is used."""
    soup = BeautifulSoup(html, "html.parser")
    body = soup.select_one(".txt-content") or soup.select_one(".TRS_Editor")
    if body is None:
        raise ValueError(f"Historical economic release layout changed: {url}")
    rows = {}
    for p in body.find_all("p"):
        text = re.sub(r"\s+", "", p.get_text()).replace("％", "%")
        match = re.search(r"(?<![\d—－–\-、至~～])([1-9]|1[0-2])月份?，(?:全国)?居民消费价格(?:总水平)?(?:同比|比上年同月|比去年同月)", text)
        if not match:
            continue
        # Restrict to the current-month paragraph; a report can also contain
        # quarterly/YTD CPI figures elsewhere in the same document.
        fragment = re.split(r"(?:1[—\-－–至~～]\d+月份?|[一二三四]季度|上半年|前三季度|全年)", text[match.start():], maxsplit=1)[0]
        month = int(match[1])
        year = int(published[:4]) - (month > int(published[5:7]))
        month_title = f"{year}年{month}月份居民消费价格"
        parsed = parse_release('<div class="txt-content">' + escape(fragment) + '</div>', url, month_title, published)
        for row in parsed:
            key = row["series_id"], row["period"]
            if key in rows and rows[key]["value"] != row["value"]:
                raise ValueError(f"Conflicting monthly CPI paragraphs in {url}")
            rows[key] = row
    # Quarterly economic reports often describe quarterly CPI in prose while
    # their appendix separately publishes the last month's component figures.
    for table in body.find_all("table"):
        grid = table_grid(table)
        selected = None
        for header_number, header in enumerate(grid[:10]):
            month_columns = {i: int(match[1]) for i, cell in enumerate(header)
                             if (match := re.fullmatch(r"([1-9]|1[0-2])月", cell))}
            if len(set(month_columns.values())) != 1:
                continue
            for lower in grid[header_number + 1:header_number + 4]:
                columns = [i for i in month_columns if i < len(lower) and "同比" in lower[i]]
                if columns:
                    selected = month_columns[columns[0]], columns[0]
                    break
            if selected:
                break
        if selected is None:
            continue
        month, column = selected
        year = int(published[:4]) - (month > int(published[5:7]))
        period = f"{year:04d}-{month:02d}"
        if period >= "2021-01":
            continue
        in_cpi, index_basis = False, False
        for cells in grid:
            label = next((cell for cell in cells if cell), "")
            if "居民消费价格" in label:
                in_cpi = True
                index_basis = "指数" in label or bool(re.search(r"上年同(?:期|月)[=＝]100", label))
                continue
            if in_cpi and re.match(r"^[一二三四五六七八九十]+、", label):
                in_cpi = False
            label = re.sub(r"^其中[：:]", "", label)
            label = "服务" if label == "服务项目" else label
            if not in_cpi or label not in LABELS or column >= len(cells):
                continue
            value = number(cells[column])
            if value is None:
                continue
            if index_basis:
                value -= 100
            parsed = []
            add(parsed, LABELS[label], period, value, url, published,
                "国家统计局经济运行公告附表；明确选取单月列的CPI分项同比，未使用季度或年内累计列"
                + ("；居民消费价格指数按上年同月=100减100转换" if index_basis else ""))
            row = parsed[0]
            key = row["series_id"], row["period"]
            if key in rows and rows[key]["value"] != row["value"]:
                raise ValueError(f"Monthly CPI prose/table disagree in {url}")
            rows[key] = row
    return list(rows.values())


def collect(backfill=False):
    if not backfill:
        return [], {}
    links, queries = discover()
    unique, examined, without_components = {}, 0, []
    for url, info in sorted(links.items(), key=lambda x: x[1]["published"]):
        parser = parse_release if "居民消费价格" in info["title"] else parse_economy_release
        parsed = parser(article(url), url, info["title"], info["published"])
        examined += 1
        if not parsed:
            without_components.append(url)
        for row in parsed:
            key = row["series_id"], row["period"]
            if key in unique and unique[key]["value"] != row["value"]:
                raise ValueError(f"Conflicting CPI historical releases: {key}")
            unique[key] = row
        if examined % 20 == 0:
            print("CPI historical releases:", examined, "/", len(links), len(unique), "observations", flush=True)
    rows = sorted(unique.values(), key=lambda x: (x["series_id"], x["period"]))
    details = {}
    for key in LABELS.values():
        periods = sorted(r["period"] for r in rows if r["series_id"] == key)
        if periods:
            details[key] = dict(archive="https://www.stats.gov.cn/search/s", search_api=SEARCH,
                queries=queries, examined_articles=examined,
                archive_supplements=ARCHIVE_SUPPLEMENTS,
                articles_without_target_components=without_components,
                refresh_ranges=[dict(start="1900-01", end="2020-12")],
                coverage_note="遍历官方搜索1900年至2021年1月CPI标题分区及全部分页，以分项词和国民经济标题补查早期经济运行公告、新闻发布会文字稿及已核验归档页；搜索索引存在漏收，早期缺少某分项则保留缺口，不把本项目最早有效公告等同官方首次发布。")
    return rows, details

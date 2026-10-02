"""Shanghai resident population and separately scoped registered fertility."""

from datetime import date
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from macro_common import add, fetch, number
from macro_nbs_annual import PROVINCE_ROOT, collect_group
from macro_render import periods_between

BASE = "https://wsjkw.sh.gov.cn"
INDEX = BASE + "/tjsj2/index.html"
POPULATION = {"4810ad6e9ddc41fc804a66134afe587f": ("population_shanghai", "年末常住人口(万人)", "万人")}


def normalize(text):
    return re.sub(r"\s+", "", text)


def discover_pages(html):
    found = re.search(r"totalPage\s*:\s*(\d+)", html)
    if not found or not 1 <= int(found[1]) <= 100:
        raise ValueError("Shanghai archive pagination missing/invalid")
    return [INDEX] + [BASE+f"/tjsj2/index_{i}.html" for i in range(2, int(found[1])+1)]


def discover_reports(html):
    soup = BeautifulSoup(html, "html.parser")
    reports = {}
    for a in soup.find_all("a", href=True):
        title = a.get("title") or a.get_text("", strip=True)
        if not re.search(r"(?:19|20)\d{2}", title):
            continue
        if not ("生育率" in title or "人口" in title or ("计划生育" in title and "统计" in title)
                or ("卫生" in title and "数据" in title)):
            continue
        url = urljoin(INDEX, a["href"])
        if url.startswith(BASE+"/tjsj2/") and not re.search(r"/index(?:_\d+)?\.html$", url):
            reports[url] = title
    if not reports:
        raise ValueError("Shanghai archive page unexpectedly empty")
    return reports


def parse_fertility(html, url, title):
    soup = BeautifulSoup(html, "html.parser")
    text = normalize(soup.get_text())
    candidates = []
    for table in soup.find_all("table"):
        table_text = normalize(table.get_text())
        if "总和" not in table_text or "生育率" not in table_text:
            continue
        for tr in table.find_all("tr"):
            cells = [normalize(td.get_text()) for td in tr.find_all(["td", "th"], recursive=False)]
            if len(cells) >= 2 and cells[0] == "全市":
                value = number(cells[1])
                if value is None or not 0 < value < 10:
                    raise ValueError("Shanghai fertility missing/invalid")
                candidates.append((value, cells))
    if not candidates:
        if "总和生育率" in text or "生育率" in title:
            raise ValueError("Shanghai fertility report structure changed")
        return None
    if "户籍人口" not in text or len({c[0] for c in candidates}) != 1:
        raise ValueError("Shanghai fertility population scope ambiguous")
    year = re.search(r"(?:19|20)\d{2}", title)[0]
    published = re.search(r"\(\s*((?:19|20)\d{2}-\d{2}-\d{2})\s*\)", soup.get_text(" "))
    value, cells = candidates[0]
    rows = []
    add(rows, "fertility_shanghai_registered", year, value, url,
        published=published[1] if published else "",
        note="上海户籍人口总和生育率；不是全体常住人口；原表全市行："+" / ".join(cells))
    return rows[0]


def collect(backfill=False):
    rows, metadata = collect_group("755d5f6efbcf41a6a411ad819aa93c17", POPULATION,
                                  geography="310000000000", place="上海市", root=PROVINCE_ROOT)
    years = sorted(r["period"] for r in rows)
    if years[0] != "2000" or years != periods_between(years[0], years[-1], "A"):
        raise ValueError("Shanghai population history truncated")
    metadata["population_shanghai"]["coverage_note"] = "新版常住人口2000年起；上海年鉴更早历史访问受限，1998—1999旧年鉴只有未明确常住口径的年底总人口，暂不拼接；2000不是统计历史起点"
    first = fetch(INDEX).decode("utf-8-sig")
    pages = discover_pages(first)
    reports = {}
    for url in pages:
        reports.update(discover_reports(first if url == INDEX else fetch(url).decode("utf-8-sig")))
    found, sources = {}, []
    for url, title in sorted(reports.items()):
        row = parse_fertility(fetch(url).decode("utf-8-sig"), url, title)
        if row is None:
            continue
        if row["period"] in found and found[row["period"]]["value"] != row["value"]:
            raise ValueError("Conflicting Shanghai fertility reports")
        found[row["period"]] = row
        sources.append(dict(url=url, title=title, year=row["period"]))
    years = sorted(found)
    if not years or years[0] > "2007" or years[-1] < "2025" or years != periods_between(years[0], years[-1], "A"):
        raise ValueError("Shanghai fertility archive incomplete")
    rows.extend(found.values())
    metadata["fertility_shanghai_registered"] = dict(index_url=INDEX, archive_pages=pages, sources=sources,
        coverage="已遍历卫健委统计数据全部档案页，2007年起连续户籍总和生育率；不是全体常住人口；早期年份尚未核验",
        requested_window_complete=True, refresh_ranges=[dict(start="1949", end=str(date.today().year))])
    print("Shanghai:", len(rows), "observations;", len(pages), "archive pages", flush=True)
    return rows, metadata

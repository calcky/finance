"""National fund finals and local debt actual balances from annual tables."""

import re
from urllib.parse import urljoin

from macro_common import add, number
from macro_fiscal_nbs import compact
from macro_fiscal_mof import ANNUAL, archive, article, soup_for


def table_rows(soup):
    return [[compact(c.get_text()) for c in tr.find_all(["td", "th"], recursive=False)]
            for tr in soup.find_all("tr")]


def parse_fund(title, soup, url, published):
    m = re.match(r"(\d{4})年全国政府性基金(?:预算)?(收入|支出)决算表", compact(title))
    if not m:
        raise ValueError("Not a national fund final table")
    year, side = m.groups()
    grid = table_rows(soup)
    headers = [r for r in grid if "决算数" in r and "预算数" in r]
    if len(headers) != 1 or "单位:亿元" not in compact(soup.get_text()).replace("：", ":"):
        raise ValueError("National fund headers/units changed")
    header = headers[0]
    column = header.index("决算数")
    selected = {}
    for row in grid:
        if not row:
            continue
        if re.fullmatch(r"全国政府性基金(?:预算)?"+side, row[0]):
            key = "fiscal_fund_"+("revenue" if side == "收入" else "expenditure")+"_annual"
        elif side == "收入" and re.fullmatch(r"[一二三四五六七八九十廿卅卌百、.]*国有土地使用权出让金收入", row[0]):
            key = "fiscal_land_fee_annual"
        else:
            continue
        if key in selected or len(row) != len(header) or number(row[column]) is None:
            raise ValueError("National fund final column ambiguous")
        selected[key] = row
    required = 2 if side == "收入" else 1
    if len(selected) != required:
        raise ValueError("National fund totals/land fee missing")
    rows = []
    for key, row in selected.items():
        add(rows, key, year, row[column], url, published,
            "全国年度决算；采用决算数列，不是预算数；原行："+" | ".join(row)+
            ("；出让金为窄口径，不替代月报土地出让收入" if key == "fiscal_land_fee_annual" else ""))
    return rows


def parse_local(title, soup, url, published):
    m = re.match(r"(\d{4})年地方政府(一般|专项)债务余额决算表", compact(title))
    if not m or "亿元" not in soup.get_text():
        raise ValueError("Not a local debt annual table/units missing")
    source_year, kind = m.groups()
    rows = []
    for row in table_rows(soup):
        if not row:
            continue
        label = re.fullmatch(r"[一二三四五六七八九十]+、(\d{4})年末地方政府"+kind+r"债务余额(?:实际数|数)?", row[0])
        if not label:
            continue
        year = label[1]
        if int(source_year)-int(year) not in (0, 1):
            raise ValueError("Unexpected local debt balance year")
        values = [c for c in row[1:] if re.fullmatch(r"\d+(?:\.\d+)?", c)]
        if len(values) != 1:
            raise ValueError("Ambiguous local annual balance")
        add(rows, "fiscal_local_"+("general" if kind == "一般" else "special")+"_annual", year, values[0], url, published,
            "年度债务决算表年末实际余额；来源年度"+source_year+"；原行："+" | ".join(row))
    if not rows or source_year not in {r["period"] for r in rows}:
        raise ValueError("Annual debt current-year actual row missing")
    return rows, int(source_year)


def collect(backfill=False):
    landings, pages = archive(ANNUAL, r"^\d{4}年全国财政决算", full=True)
    entries = {}
    examined = []
    for landing in landings:
        year = int(landing["title"][:4])
        # Earlier landings were audited: only central fund accounts, not a
        # comparable national fund total. Don't substitute those totals.
        if year < 2010:
            continue
        if not backfill and year < max(int(e["title"][:4]) for e in landings)-1:
            continue
        url = landing["url"]
        soup = soup_for(url)
        counts = re.findall(r"(?:var\s+countPage\s*=\s*|createPageHTML\(\s*)(\d+)", str(soup))
        count = max(map(int, counts), default=1)
        if count > 30:
            raise ValueError("Unexpected annual landing pagination")
        for page in range(count):
            pageurl = url if page == 0 else urljoin(url, f"index_{page}.htm")
            if page:
                soup = soup_for(pageurl)
            examined.append(pageurl)
            for a in soup.select("a[href]"):
                title = compact(a.get("title") or a.get_text())
                if re.match(r"^\d{4}年(?:全国政府性基金(?:预算)?(?:收入|支出)决算表|地方政府(?:一般|专项)债务余额决算表)", title):
                    link = urljoin(pageurl, a["href"]).replace("http:", "https:")
                    if not link.endswith(".htm"):
                        raise ValueError("Annual fiscal table format changed")
                    entries[link] = title
    found, revisions = {}, []
    for url, title in sorted(entries.items(), key=lambda e: (e[1][:4], e[0])):
        soup, _, published = article(url)
        if "全国政府性基金" in title:
            batch, source_year = parse_fund(title, soup, url, published), int(title[:4])
        else:
            batch, source_year = parse_local(title, soup, url, published)
        for row in batch:
            identity = row["series_id"], row["period"]
            if identity in found:
                old_year, old = found[identity]
                if old_year == source_year and number(old["value"]) != number(row["value"]):
                    raise ValueError("Conflicting same-vintage annual fiscal data")
                if old_year > source_year:
                    continue
                if number(old["value"]) != number(row["value"]):
                    revisions.append(dict(series_id=row["series_id"], period=row["period"], original=old, revised=row))
            found[identity] = source_year, row
    rows = [row for _, row in found.values()]
    if not rows:
        raise ValueError("No national fiscal final accounts")
    detail = dict(archive_pages=pages, annual_landing_pages=examined, table_count=len(entries), requested_window_complete=True,
        later_vintage_revisions=revisions,
        coverage_note="财政部年度档案2010年起有可核验全国政府性基金决算；已查更早年度入口，不以中央基金表替代全国。地方年度债务表自2015年起，含2014年末实际数。每日核对最近两年表，全量回溯遍历早期表。",
        definition_notes=["地方年度余额采用较晚年度表中的实际数，保留2015/2016等修订前后值与来源；2016基金及对应债务在一般/专项之间调整。",
                          "年度土地出让金为窄口径；不通过加总其他基金反推更宽的土地出让收入，也不接入月度土地线。"])
    return rows, detail

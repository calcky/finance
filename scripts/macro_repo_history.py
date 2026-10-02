"""Resumable first-party PBC announcement archive; never synthesize repo rates."""

import argparse
from collections import Counter
from datetime import date, timedelta
import json
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import macro_common as common
from macro_common import add


BASE = "https://www.pbc.gov.cn/zhengcehuobisi/125207/125213/125431/125475/"
TITLE = re.compile(r"公开市场业务交易公告.*(?:19|20)\d{2}")
RATE_HEADER = re.compile(r"(?:操作利率|中标利率|中标加权平均利率|招标利率|回购利率)")
OTHER_OPERATION = re.compile(r"正回购|中央银行票据|央票|中期借贷便利|MLF|常备借贷便利|SLF|短期流动性调节工具|SLO")


def norm(text):
    return re.sub(r"\s+", "", text).replace("％", "%")


def archive_page(page):
    url = BASE + ("index.html" if page == 1 else f"17081-{page}.html")
    soup = BeautifulSoup(common.fetch(url), "html.parser")
    text = soup.get_text(" ", strip=True)
    total = re.search(r"总记录数\s*[:：]\s*(\d+).*?当前页\s*[:：]\s*\d+\s*/\s*(\d+)", text)
    if not total:
        raise ValueError(f"PBC archive pagination missing: {url}")
    records = []
    for link in soup.select("a[href]"):
        title = link.get_text(" ", strip=True)
        if not TITLE.search(title):
            continue
        cell = link.find_parent("td")
        stamp = re.search(r"\d{4}-\d{2}-\d{2}", cell.get_text() if cell else "")
        if not stamp:
            raise ValueError(f"PBC archive date missing: {link}")
        records.append({"url": urljoin(url, link["href"]), "date": stamp[0], "title": title})
    if not records:
        raise ValueError(f"Empty PBC archive page {page}")
    return records, int(total[1]), int(total[2])


def reverse_table(table, content):
    whole = norm(content.get_text())
    if "逆回购" not in whole:
        return False
    if not OTHER_OPERATION.search(whole):
        return True
    # Mixed-operation documents require the nearest preceding section heading.
    for node in table.previous_elements:
        if getattr(node, "name", None) not in ("p", "h2", "h3", "h4"):
            continue
        if not any(parent is content for parent in node.parents):
            continue
        parent_table = node.find_parent("table")
        # PBC wraps whole pages in layout tables. Only skip paragraphs inside
        # an article's data table, not headings inside that outer page layout.
        if parent_table and any(parent is content for parent in parent_table.parents):
            continue
        text = norm(node.get_text())
        if "逆回购" in text and not OTHER_OPERATION.search(text):
            return True
        if OTHER_OPERATION.search(text):
            return False
    raise ValueError("Ambiguous reverse/positive-repo or bill table context")


def parse_announcement(html, url, archive_date):
    soup = BeautifulSoup(html, "html.parser")
    content = soup.find(id="zoom")
    if content is None:
        raise ValueError("PBC article body #zoom missing")
    text = norm(content.get_text(" ", strip=True))
    affirmative = re.sub(r"(?:不开展|未开展|没有|无)(?:公开市场)?(?:7天(?:期)?)?逆回购(?:操作|交易)?", "", text)
    if "逆回购" not in affirmative:
        if content.find("img"):
            raise ValueError("Image-bearing announcement cannot be classified from text alone")
        return [], "no_operation" if "逆回购" in text else "no_reverse"
    if not re.search(r"(?:7|七)天", text):
        if content.find("img"):
            raise ValueError("Image-bearing reverse-repo announcement has no machine-readable tenor")
        return [], "no_7day"
    if re.search(r"(?:7|七)天(?:期)?逆回购操作量为(?:零|0(?:\.0+)?(?:亿元)?)(?:[。；，,]|$)", text):
        return [], "no_operation"
    publication = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", soup.get_text(" ", strip=True))
    if not publication or publication[1] != archive_date:
        raise ValueError(f"Publication/archive date mismatch: {publication} vs {archive_date}")
    rows, saw_tenor = [], False
    for table in content.find_all("table"):
        grid = [[norm(cell.get_text()) for cell in row.find_all(["td", "th"], recursive=False)]
                for row in table.find_all("tr")]
        tenor_rows = [row for row in grid if any(re.fullmatch(r"(?:7|七)天(?:期)?", cell) for cell in row)]
        if not tenor_rows or not reverse_table(table, content):
            continue
        saw_tenor = True
        headers = [(i, row) for i, row in enumerate(grid) if any(RATE_HEADER.search(cell) for cell in row)]
        if not headers:
            if any("利率" in cell or "%" in cell for row in grid for cell in row):
                raise ValueError("Unrecognized reverse-repo interest-rate table header")
            continue
        if len(headers) != 1:
            raise ValueError("Multiple rate header rows in one reverse-repo table")
        _, header = headers[0]
        rate_columns = [i for i, cell in enumerate(header) if RATE_HEADER.search(cell)]
        if len(rate_columns) != 1:
            raise ValueError("Ambiguous operation rate column")
        rate_col = rate_columns[0]
        amount_columns = [i for i, cell in enumerate(header)
                          if re.fullmatch(r"(?:操作量|中标量|交易量|招标数量)(?:[（(](?:亿元|万元|元)[）)])?", cell)]
        for values in tenor_rows:
            if len(values) != len(header):
                raise ValueError("Reverse-repo table has merged/unknown columns")
            if any(re.fullmatch(r"0(?:\.0+)?(?:亿元|亿|万元|万)?", values[i]) for i in amount_columns):
                continue
            raw = values[rate_col]
            if raw in ("", "-", "—", "无"):
                continue
            if not re.fullmatch(r"\d+(?:\.\d+)?%?", raw):
                raise ValueError(f"Unrecognized reverse-repo rate: {raw}")
            if not raw.endswith("%") and "%" not in header[rate_col]:
                raise ValueError("Reverse-repo rate lacks percent unit")
            add(rows, "repo_7d", archive_date, raw.rstrip("%"), url, archive_date,
                "人民银行公告中的7天逆回购实际操作利率；不填充无操作日；保留原表利率口径")
    if not rows:
        if content.find("img"):
            raise ValueError("Image-bearing reverse-repo announcement has no machine-readable rate")
        if RATE_HEADER.search(text) and not saw_tenor:
            raise ValueError("7-day reverse-repo mention has a rate but no recognized tenor row")
        return [], "no_explicit_rate"
    if len({common.number(row["value"]) for row in rows}) != 1:
        raise ValueError("Conflicting 7-day reverse-repo rates in one announcement")
    return [rows[0]], "observed"


def collect(backfill=False, latest=None, progress=None):
    first, expected, pages = archive_page(1)
    records = list(first)
    # On daily runs inspect at least3pages, then continue back to the known
    # latest point with a31day revision overlap, rather than a permanent cap.
    cutoff = date.fromisoformat(latest) - timedelta(days=31) if latest else date.today() - timedelta(days=90)
    for page in range(2, pages + 1):
        if not backfill and page > 3 and min(r["date"] for r in records) <= cutoff.isoformat():
            break
        batch, current_total, current_pages = archive_page(page)
        if current_total != expected or current_pages != pages:
            raise ValueError("PBC archive changed during scan; resume with a fresh index cache")
        records.extend(batch)
        print("PBC repo archive", page, "/", pages, len(records), flush=True)
    urls = [r["url"] for r in records]
    if len(set(urls)) != len(urls) or (backfill and len(records) != expected):
        raise ValueError("PBC announcement count/uniqueness check failed")
    # Establish the earliest actual tenor/rate early; cache makes reordering
    # harmless to already-fetched recent documents.
    records.sort(key=lambda record: (record["date"], record["url"]))
    print("PBC candidate announcements", len(records), "earliest", min(r["date"] for r in records), flush=True)
    rows, counts, failures, by_period = [], Counter(), [], {}
    archive_start = min(r["date"] for r in records)
    archive_end = max(r["date"] for r in records)
    def result():
        periods = [r["period"] for r in rows]
        return rows, {"repo_7d": {"archive": BASE, "archive_documents": len(records),
            "processed_documents": sum(counts.values()) + len(failures), "counts": dict(counts),
            "skipped": {key: value for key, value in counts.items() if not key.startswith("observed")},
            "failed_urls": failures, "complete_archive": backfill and sum(counts.values()) == len(records) and not failures,
            "requested_window_complete": sum(counts.values()) == len(records) and not failures,
            "first_observation": min(periods) if periods else None,
            "last_observation": max(periods) if periods else None,
            "archive_first_publication": archive_start, "archive_last_publication": archive_end,
            "refresh_ranges": [{"start": archive_start, "end": date.today().isoformat()}],
            "coverage": "逐页核对人民银行公开市场公告档案；只提取有明确利率的实际7天逆回购，非连续政策利率；未操作/其他期限/无显式利率不造数"}}
    for index, record in enumerate(records, 1):
        try:
            batch, reason = parse_announcement(common.fetch(record["url"]), record["url"], record["date"])
            for row in batch:
                if row["period"] in by_period:
                    previous = by_period[row["period"]]
                    if common.number(row["value"]) != common.number(previous["value"]):
                        raise ValueError(f"Conflicting same-day repo rates: {previous['source_url']}")
                    reason = "observed_duplicate_same_rate"
                else:
                    by_period[row["period"]] = row
                    rows.append(row)
            counts[reason] += 1
        except HTTPError as error:
            failures.append({"url": record["url"], "error": str(error)})
            if error.code in (401, 403, 429):
                if progress:
                    progress(*result())
                raise
        except (ValueError, URLError, TimeoutError) as error:
            failures.append({"url": record["url"], "error": str(error)})
        if index % 20 == 0 or index == len(records):
            print("PBC repo documents", index, "/", len(records), dict(counts), "failures", len(failures), flush=True)
            if progress:
                progress(*result())
    if failures or sum(counts.values()) != len(records):
        raise ValueError(f"PBC requested window incomplete: {len(failures)} failed announcements; consult progress metadata")
    return result()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backfill", action="store_true")
    parser.add_argument("--latest")
    parser.add_argument("--cache", default="/tmp/finance-history-repo")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    common.CACHE = args.cache
    def save(rows, meta):
        output = Path(args.output)
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.write_text(json.dumps({"rows": rows, "metadata": meta}, ensure_ascii=False), encoding="utf-8")
        temporary.replace(output)
    save(*collect(args.backfill, args.latest, progress=save))

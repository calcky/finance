"""First-party market history, with a separate resumable initial backfill.

The daily collector refreshes three calendar months of FX/yields and the cheap
complete LPR file. HTTP cache is controlled by macro_common.CACHE. No missing
trading days are synthesized. PBC operation announcements are collected separately.
"""

import argparse
import calendar
import csv
from datetime import date
import hashlib
from io import StringIO
import json
from pathlib import Path
import time
from urllib.parse import urlencode

import macro_common as common
from macro_common import add
from macro_pbc import parse_yields


FX_START = date(2006, 1, 4)  # Earliest date permitted by the official history UI.
YIELD_START = date(2006, 3, 1)  # First returned date; 2002 and 2005 are empty.
LPR_URL = "https://www.chinamoney.com.cn/ags/ms/cm-u-bk-currency/LprChrtCSV?startDate=2013-01-01"
FX_BASE = "https://www.chinamoney.com.cn/ags/ms/cm-u-bk-ccpr/CcprHisNew?"
FX_SOURCE = "https://www.chinamoney.com.cn/chinese/bkccpr/"
YIELD_BASE = "https://yield.chinabond.com.cn/cbweb-pbc-web/pbc/historyQuery?"


def fetch(url):
    # Cached initial-backfill responses make an interrupted crawl resumable.
    key = hashlib.sha256(url.encode()).hexdigest()
    if not common.CACHE or not (Path(common.CACHE) / key).exists():
        time.sleep(max(0, 2 - (time.monotonic() - common._last_request)))
    return common.fetch(url)


def recent_start(today):
    serial = today.year * 12 + today.month - 1 - 2
    return date(serial // 12, serial % 12 + 1, 1)


def month_windows(start, end):
    while start <= end:
        last = min(end, date(start.year, start.month, calendar.monthrange(start.year, start.month)[1]))
        yield start, last
        start = date(start.year + (start.month == 12), start.month % 12 + 1, 1)


def metadata(rows, start, end, **extra):
    periods = [row["period"] for row in rows]
    return dict(first_observation=min(periods) if periods else None,
                last_observation=max(periods) if periods else None,
                observation_count=len(periods),
                refresh_ranges=[{"start": str(start), "end": str(end)}], **extra)


def yield_source_url(period):
    # A one-day query is a working, stable link to this exact observation.
    # The endpoint without date parameters returns an error page.
    return YIELD_BASE + urlencode(dict(startDate=period, endDate=period,
        gjqx=0, qxId="hzsylqx", locale="zh_CN"))


def collect_lpr():
    payload = json.loads(fetch(LPR_URL))
    data = payload["data"]
    if data["columns"] != ["date", "open", "high", "low", "close", "volume", "1Y", "5Y"]:
        raise ValueError("LPR historical columns changed")
    rows = []
    seen = set()
    for values in csv.reader(StringIO(data["csv"].replace("\\r\\n", "\n"))):
        if not values:
            continue
        if len(values) != 8:
            raise ValueError("LPR historical row width changed")
        observed = date.fromisoformat(values[0])
        if observed > date.today():
            raise ValueError("Future LPR observation")
        old = observed < date(2019, 8, 20)
        keys = [("lpr_1y_pre2019" if old else "lpr_1y", 6)]
        if old and values[7].strip():
            raise ValueError("Unexpected 5-year LPR before the reform")
        if not old:
            keys.append(("lpr_5y", 7))
        for key, column in keys:
            pair = key, values[0][:7]
            if pair in seen or not values[column].strip():
                raise ValueError(f"Duplicate or missing LPR observation: {pair}")
            seen.add(pair)
            add(rows, key, pair[1], values[column], LPR_URL,
                note=f"中国货币网月内观察日 {values[0]}，非报价发布日期；" +
                ("2019年8月改革前口径，独立序列" if old else "2019年8月改革后口径"))
    details = {}
    for key, start, end in [("lpr_1y_pre2019", "2013-10", "2019-07"),
                            ("lpr_1y", "2019-08", date.today().strftime("%Y-%m")),
                            ("lpr_5y", "2019-08", date.today().strftime("%Y-%m"))]:
        batch = [row for row in rows if row["series_id"] == key]
        if not batch or batch[-1]["period"] != start:
            raise ValueError(f"LPR earliest coverage changed: {key}")
        details[key] = metadata(batch, start, end, url=LPR_URL, query_urls=[LPR_URL],
            coverage="官方历史月度观察值；改革前后分开，5年以上期限自2019年8月开始；不补造日度报价")
    return rows, details


def parse_fx_history(payload, url, start, end):
    data = payload["data"]
    if data.get("flagMessage") or data.get("searchlist") != ["USD/CNY"]:
        raise ValueError(f"FX source rejected the query or returned another currency: {data}")
    if data["startDate"] != start.isoformat() or data["endDate"] != end.isoformat():
        raise ValueError("FX returned a different date window")
    rows = []
    for record in payload["records"]:
        observed = date.fromisoformat(record["date"])
        if not start <= observed <= end or len(record["values"]) != 1:
            raise ValueError("FX observation outside requested window or wrong width")
        add(rows, "usdcny_mid", record["date"], record["values"][0], FX_SOURCE,
            note="中国货币网人民币汇率中间价历史查询；人民币/美元；非即期成交价")
    return rows


def collect_fx(backfill=False):
    today = date.today()
    start = FX_START if backfill else max(FX_START, recent_start(today))
    rows, queries = [], []
    for first, last in month_windows(start, today):
        page, batch, expected = 1, [], None
        while True:
            # This is the site's ordinary monthly paginated query. Larger page
            # sizes returned403; never escalate or bypass an access rejection.
            params = urlencode(dict(startDate=first.isoformat(), endDate=last.isoformat(),
                                    currency="USD/CNY", pageNum=page, pageSize=30), safe="/")
            url = FX_BASE + params
            queries.append(url)
            payload = json.loads(fetch(url))
            current = parse_fx_history(payload, url, first, last)
            data = payload["data"]
            if data["pageNum"] != page:
                raise ValueError("FX pagination mismatch")
            expected = int(data["total"])
            batch.extend(current)
            if page >= int(data["pageTotal"]):
                break
            if not current:
                raise ValueError("Empty FX page before pagination completed")
            page += 1
        if len(batch) != expected or len({r["period"] for r in batch}) != len(batch):
            raise ValueError("FX total count or uniqueness check failed")
        if last < today.replace(day=1) and not batch:
            raise ValueError(f"Empty completed FX month {first}")
        rows.extend(batch)
        print("FX history", first, len(batch), flush=True)
    if backfill and min(r["period"] for r in rows) != FX_START.isoformat():
        raise ValueError("FX earliest coverage changed")
    return rows, {"usdcny_mid": metadata(rows, start, today,
        source_page=FX_SOURCE, query_urls=queries,
        earliest_verified=FX_START.isoformat(),
        coverage="官方历史查询起点2006-01-04；按月分页核对总条数，不填充非交易日；日常刷新最近三个日历月")}


def collect_yield_history(backfill=False):
    today = date.today()
    start = YIELD_START if backfill else max(YIELD_START, recent_start(today))
    rows, queries = [], []
    for year in range(start.year, today.year + 1):
        first, last = max(start, date(year, 1, 1)), min(today, date(year, 12, 31))
        url = YIELD_BASE + urlencode(dict(startDate=first.isoformat(), endDate=last.isoformat(),
                                         gjqx=0, qxId="hzsylqx", locale="zh_CN"))
        queries.append(url)
        batch = parse_yields(fetch(url), url)
        if not batch and first < today.replace(day=1):
            raise ValueError(f"Empty completed ChinaBond window {first}–{last}")
        if any(not first.isoformat() <= row["period"] <= last.isoformat() for row in batch):
            raise ValueError("ChinaBond returned a different date window")
        if len({(r["series_id"], r["period"]) for r in batch}) != len(batch):
            raise ValueError("Duplicate ChinaBond observations")
        for row in batch:
            row["source_url"] = yield_source_url(row["period"])
        rows.extend(batch)
        print("ChinaBond history", first, len(batch), flush=True)
    details = {}
    for key in ("yield_1y", "yield_10y"):
        batch = [row for row in rows if row["series_id"] == key]
        if backfill and min(r["period"] for r in batch) != YIELD_START.isoformat():
            raise ValueError("ChinaBond earliest coverage changed")
        details[key] = metadata(batch, start, today,
            earliest_verified=YIELD_START.isoformat(), curve="中债国债收益率曲线", query_urls=queries,
            coverage="本公开接口首个实际观察2006-03-01；2002年和2005年查询为空，不宣称所有中债产品历史仅始于此；日常刷新最近三个日历月")
    return rows, details


def collect(backfill=False):
    rows, details = [], {}
    for collector in (collect_lpr, lambda: collect_fx(backfill), lambda: collect_yield_history(backfill)):
        batch, meta = collector()
        rows.extend(batch)
        details.update(meta)
    return rows, details


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backfill", action="store_true")
    parser.add_argument("--cache", default="/tmp/finance-history-market")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    common.CACHE = args.cache
    result, source_meta = collect(args.backfill)
    output = Path(args.output)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps({"rows": result, "metadata": source_meta}, ensure_ascii=False), encoding="utf-8")
    temporary.replace(output)
    print("Market observations:", len(result), flush=True)

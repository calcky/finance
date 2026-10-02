"""Full first-party US rate histories via the Fed's recommended FRED channel."""

import csv
from datetime import date, timedelta
from io import StringIO
from urllib.parse import urlencode

from macro_common import fetch, observation, number

DOWNLOAD = "https://fred.stlouisfed.org/graph/fredgraph.csv?"
FED_TRANSITION = "https://www.federalreserve.gov/data/data-download-fred-information.htm"
SOURCES = {
    "us_effr": ("DFF", "1954-07-01", "D"),
    "us_target": ("DFEDTAR", "1982-09-27", "D"),
    "us_target_lower": ("DFEDTARL", "2008-12-16", "D"),
    "us_target_upper": ("DFEDTARU", "2008-12-16", "D"),
    "us_treasury_2y": ("DGS2", "1976-06-01", "D"),
    "us_treasury_10y": ("DGS10", "1962-01-02", "D"),
    "us_treasury_2y_monthly": ("GS2", "1976-06", "M"),
    "us_treasury_10y_monthly": ("GS10", "1953-04", "M"),
    "us_real_10y": ("DFII10", "2003-01-02", "D"),
}
DERIVED = {
    "us_term_spread": ("us_treasury_10y", "us_treasury_2y", "T10Y2Y"),
    "us_breakeven_10y": ("us_treasury_10y", "us_real_10y", "T10YIE"),
}
# Verified against the Board's independent H.15 full Treasury CSV. Retain
# component values, disclose differences, and reject new unexplained changes.
KNOWN_SPREAD_DIFFERENCES = {
    "T10Y2Y": {"1990-11-21": ("0.72", "0.74"),
               "1991-01-29": ("0.93", "0.95"),
               "1995-11-29": ("0.43", "0.42")},
    "T10YIE": {},
}


def audit_spread(readings, official, reference):
    overlap = readings.keys() & official.keys()
    if not overlap:
        raise ValueError(f"{reference}: no dates overlap independent spread")
    differences = []
    for period in sorted(overlap):
        calculated, published = readings[period], official[period]
        if calculated == published:
            continue
        expected = KNOWN_SPREAD_DIFFERENCES[reference].get(period)
        if expected is None or (calculated, published) != tuple(map(number, expected)):
            raise ValueError(f"{reference}: unexplained spread difference at {period}")
        differences.append(dict(period=period, calculated=str(calculated), reference=str(published)))
    return dict(audited_common_dates=len(overlap), reference_differences=differences,
                reference_only_dates=len(official.keys() - readings.keys()),
                reference_last_observation=max(official))


def url_for(ident, start="1900-01-01", end=None):
    return DOWNLOAD + urlencode(dict(id=ident, cosd=start, coed=end or date.today().isoformat()))


def parse_csv(raw, ident, frequency, start="1900-01-01", end=None):
    end = end or date.today().isoformat()
    reader = csv.DictReader(StringIO(raw.decode("utf-8-sig")))
    if reader.fieldnames != ["observation_date", ident]:
        raise ValueError(f"FRED column identity changed: {ident}: {reader.fieldnames}")
    readings, dates, missing = {}, [], []
    for row in reader:
        stamp = row["observation_date"]
        observed = date.fromisoformat(stamp)
        if not start <= stamp <= end or stamp != observed.isoformat():
            raise ValueError(f"{ident}: observation outside requested window: {stamp}")
        if dates and stamp <= dates[-1]:
            raise ValueError(f"{ident}: duplicate/unordered date: {stamp}")
        if dates:
            previous = date.fromisoformat(dates[-1])
            if frequency == "M":
                expected = date(previous.year + (previous.month == 12), previous.month % 12 + 1, 1)
            else:
                expected = previous + timedelta(days=1)
                if ident not in {"DFF", "DFEDTAR", "DFEDTARL", "DFEDTARU"}:
                    while expected.weekday() >= 5:
                        expected += timedelta(days=1)
            if observed != expected:
                raise ValueError(f"{ident}: missing source calendar row before {stamp}")
        dates.append(stamp)
        if frequency == "M" and observed.day != 1:
            raise ValueError(f"{ident}: monthly timestamp is not month start")
        period = stamp[:7] if frequency == "M" else stamp
        text = row[ident]
        if text in ("", ".", "NA"):
            missing.append(period)
            continue
        value = number(text)
        if value is None or not -20 <= value <= 40:
            raise ValueError(f"{ident}: invalid rate {text}")
        readings[period] = value
    if not readings:
        raise ValueError(f"{ident}: empty history")
    return readings, dict(returned_dates=len(dates), missing_observations=len(missing),
                          first_returned_date=dates[0], last_returned_date=dates[-1])


def split_audit(ident, frequency, full):
    first, last = min(full), max(full)
    middle = (int(first[:4]) + int(last[:4])) // 2
    boundary = f"{middle}-12-31"
    combined = {}
    queries = []
    for start, end in [("1900-01-01", boundary), (f"{middle+1}-01-01", date.today().isoformat())]:
        url = url_for(ident, start, end)
        readings, _ = parse_csv(fetch(url), ident, frequency, start, end)
        if combined.keys() & readings.keys():
            raise ValueError(f"{ident}: split history overlap")
        combined.update(readings)
        queries.append(url)
    if combined != full:
        raise ValueError(f"{ident}: full download differs from split-window history")
    return queries


def collect(backfill=False):
    rows, metadata, values = [], {}, {}
    today = date.today()
    for key, (ident, earliest, frequency) in SOURCES.items():
        url = url_for(ident)
        readings, detail = parse_csv(fetch(url), ident, frequency)
        first, last = min(readings), max(readings)
        if first > earliest:
            raise ValueError(f"{ident}: source truncated known history, expected {earliest}, got {first}")
        if key == "us_target":
            if last != "2008-12-15":
                raise ValueError("Historical single target endpoint changed")
        elif frequency == "D" and last < (today - timedelta(days=14)).isoformat():
            raise ValueError(f"{ident}: unexpectedly stale daily source, last {last}")
        elif frequency == "M" and last < (today - timedelta(days=95)).strftime("%Y-%m"):
            raise ValueError(f"{ident}: unexpectedly stale monthly source, last {last}")
        audits = split_audit(ident, frequency, readings) if backfill else []
        values[key] = readings
        note = "FRED官方分发的美国利率；按来源保留每日观测" if frequency == "D" else "H.15官方月均；与日度独立保存"
        rows.extend(observation(key, p, v, f"https://fred.stlouisfed.org/series/{ident}", note=note)
                    for p, v in readings.items())
        metadata[key] = dict(source_series=ident, source_url=f"https://fred.stlouisfed.org/series/{ident}",
            download_url=url, frequency=frequency, unit="percent per annum", seasonal_adjustment="not seasonally adjusted",
            country="USA", observation_count=len(readings), first_observation=first, last_observation=last,
            requested_window_complete=True, refresh_ranges=[dict(start=earliest, end=today.isoformat() if frequency == "D" else today.strftime("%Y-%m"))],
            split_audit_urls=audits, full_equals_split=True if backfill else None,
            coverage_note="每次读取1900年至当前的完整可用文件；最早观测按序列分别核验。来源中的缺失留空，不跨假期补值，也不将月均扩展成日值。",
            recommended_distribution=FED_TRANSITION, **detail)
        print(f"US rates {ident}: {len(readings)} observations {first}–{last}", flush=True)
    lower, upper = values["us_target_lower"], values["us_target_upper"]
    if lower.keys() != upper.keys() or any(lower[p] > upper[p] for p in lower):
        raise ValueError("Policy target bounds have inconsistent dates/order")
    metadata["us_effr"]["structural_breaks"] = [dict(period="2016-03-01", note="EFFR由经纪商汇总的成交量加权均值改为FR2420交易报告的成交量加权中位数；新版首次于2016-03-02发布。")]
    for key in ("us_treasury_2y", "us_treasury_10y", "us_treasury_2y_monthly", "us_treasury_10y_monthly"):
        metadata[key]["structural_breaks"] = [dict(period="2021-12-06", note="财政部名义曲线改用monotone convex拟合方法；保留此前官方历史。")]
    metadata["us_real_10y"]["structural_breaks"] = [
        dict(period="2008-12-01", note="TIPS实际曲线节点方法调整。"),
        dict(period="2010-02-22", note="实际曲线加入30年期限点。")]
    for key, (left, right, reference) in DERIVED.items():
        common = sorted(values[left].keys() & values[right].keys())
        readings = {p: values[left][p] - values[right][p] for p in common}
        reference_url = url_for(reference)
        official, detail = parse_csv(fetch(reference_url), reference, "D")
        audit = audit_spread(readings, official, reference)
        formula = f"{SOURCES[left][0]} - {SOURCES[right][0]}"
        input_url = DOWNLOAD + urlencode(dict(id=f"{SOURCES[left][0]},{SOURCES[right][0]}", cosd="1900-01-01"))
        rows.extend(observation(key, p, v, input_url,
                                note=f"本项目计算 {formula}；同一观测日；单位百分点；参考利差核对及历史差异见元数据") for p, v in readings.items())
        metadata[key] = dict(formula=formula, inputs=[left, right], input_urls=[metadata[left]["source_url"], metadata[right]["source_url"]],
            source_url=input_url, reference_url=f"https://fred.stlouisfed.org/series/{reference}", audit_url=reference_url,
            **audit, requested_window_complete=True,
            refresh_ranges=[dict(start=min(readings), end=today.isoformat())],
            coverage_note="仅两个输入都存在的同日计算；原始利率为百分比报价，差值为百分点。核对参考利差的重叠日期，公开已核验差异；参考序列可能更早更新，不拿它补齐输入缺口。", **detail)
    return rows, metadata

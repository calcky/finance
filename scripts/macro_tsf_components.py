"""PBC monthly AFRE components, preserving missing cells and official backcasts."""

from datetime import date
import re

from macro_common import add, number
from macro_money_history import (DIRECTORY, LEGACY_FLOW, _soup, _url, _norm,
                                 _fetch, _candidates, _date_headers, table_cells)

LABELS = {
    "社会融资规模": "total", "人民币贷款": "tsf_rmb_flow", "外币贷款": "tsf_fx_flow",
    "委托贷款": "tsf_entrusted_flow", "信托贷款": "tsf_trust_flow",
    "未贴现银行承兑汇票": "tsf_acceptances_flow", "企业债券": "tsf_corporate_bonds_flow",
    "政府债券": "tsf_government_flow", "非金融企业境内股票融资": "tsf_equity_flow",
    "存款类金融机构资产支持证券": "tsf_abs_flow", "贷款核销": "tsf_writeoffs_flow",
}


def field(value):
    text = _norm(value).removeprefix("其中:").removeprefix("其中：").replace("未贴现的银行", "未贴现银行")
    return next((key for label, key in LABELS.items() if text.startswith(label)), None)


def amount(value):
    return None if _norm(value) in ("——", "--") else number(value)


def parse_components(data, year, url):
    cells = table_cells(data, url)
    text = _norm("".join(str(v or "") for row in cells for v in row))
    if "社会融资规模" not in text or "亿元" not in text:
        raise ValueError("AFRE component schema/unit changed")
    result, columns, monetary, total_col = {}, {}, True, None
    for row in cells:
        title = _norm("".join(str(v or "") for v in row[:2]))
        if title.startswith("单位"):
            monetary = "亿元" in title
        recognized = {col: field(value) for col, value in enumerate(row) if field(value)}
        for col, key in recognized.items():
            if key == "total" and col > 0:
                total_col = col
        if len(recognized) >= 4:
            columns = recognized
            if total_col is not None:
                columns[total_col] = "total"
        if not monetary or not columns or not row:
            continue
        token = _norm(row[0])
        if not re.fullmatch(r"\d{4}\.\d{1,2}", token):
            continue
        # These flow tables encode YYYY.MM; Excel drops October's final zero.
        month = int((token.split(".")[1]+"0")[:2])
        if not 1 <= month <= 12:
            raise ValueError(f"Invalid AFRE month {token}")
        period = f"{token[:4]}-{month:02d}"
        for col, key in columns.items():
            value = amount(row[col] if col < len(row) else None)
            if value is not None:
                # Later explicit backcast tables supersede their own main table.
                result[key, period] = value
    if not result:
        headers = _date_headers(cells, year, "money")
        for row in cells:
            key = field(row[0]) if row else None
            if not key or "统计表" in _norm(row[0]):
                continue
            for col, period, _ in headers:
                value = amount(row[col] if col < len(row) else None)
                if value is not None:
                    result[key, period] = value
    if not any(key == "total" for key, _ in result):
        raise ValueError(f"No AFRE component totals in {url}")
    required = ["tsf_rmb_flow", "tsf_fx_flow", "tsf_entrusted_flow", "tsf_trust_flow",
                "tsf_acceptances_flow", "tsf_corporate_bonds_flow", "tsf_equity_flow"]
    if year >= 2019:
        required += ["tsf_government_flow", "tsf_abs_flow", "tsf_writeoffs_flow"]
    for period in {p for k, p in result if k == "total"}:
        for key in required:
            if key == "tsf_trust_flow" and period < "2006-01":
                continue
            if (key, period) not in result:
                raise ValueError(f"AFRE component missing: {key}/{period}")
    return result


def grouped(values):
    """Do not construct sums/residuals unless every required item is observed."""
    result = dict(values)
    for period in sorted({p for _, p in values}):
        for key, members in [
            ("tsf_direct_flow", ["tsf_corporate_bonds_flow", "tsf_equity_flow"]),
            ("tsf_offbalance_flow", ["tsf_entrusted_flow", "tsf_trust_flow", "tsf_acceptances_flow"]),
        ]:
            if all((m, period) in result for m in members):
                result[key, period] = sum(result[m, period] for m in members)
        members = ["tsf_rmb_flow", "tsf_government_flow", "tsf_direct_flow", "tsf_offbalance_flow"]
        if ("total", period) in result and all((m, period) in result for m in members):
            result["tsf_remaining_flow", period] = result["total", period] - sum(result[m, period] for m in members)
    return result


def collect(backfill=False):
    root = _soup(DIRECTORY)
    years = {int(m[1]): _url(DIRECTORY, a["href"]) for a in root.select("a[href]")
             if (m := re.fullmatch(r"(\d{4})年统计数据", a.get_text(strip=True)))}
    if not years or max(years) < date.today().year-1:
        raise ValueError("AFRE annual directory unavailable")
    # The original 2002–2012 release supplies earlier history; annual AFRE
    # tables in the audited directory start at 2012.
    years = {y: u for y, u in years.items() if y >= 2012}
    if not backfill:
        years = {y: u for y, u in years.items() if y >= date.today().year-1}
    first_year = 2012 if backfill else date.today().year-1
    if set(years) != set(range(first_year, max(years)+1)):
        raise ValueError("AFRE annual directory has missing years")
    batches = []
    if backfill:
        batches.append((2012, LEGACY_FLOW, parse_components(_fetch(LEGACY_FLOW), 2012, LEGACY_FLOW)))
    for year, annual in sorted(years.items()):
        choices = _candidates(annual)
        if "flow" not in choices:
            if year >= 2012:
                raise ValueError(f"Missing AFRE annual table: {year}")
            continue
        url = choices["flow"]
        values = parse_components(_fetch(url), year, url)
        months = {p for k, p in values if k == "total" and p.startswith(str(year))}
        expected_count = 12 if year < date.today().year else len(months)
        if not months or months != {f"{year}-{m:02d}" for m in range(1, expected_count+1)}:
            raise ValueError(f"AFRE annual months missing: {year}")
        batches.append((year, url, values))
        print("AFRE components:", year, len(values), flush=True)
    raw, provenance, details = {}, {}, {}
    for year, url, values in batches:
        for identity, value in values.items():
            raw[identity] = value
            provenance[identity] = url
        for key in {k for k, _ in values if k != "total"}:
            entry = details.setdefault(key, dict(annual_directory=DIRECTORY, attachments=[], refresh_ranges=[]))
            entry["attachments"].append(url)
            periods = [p for k, p in values if k == key]
            # Include missing endpoints within the published yearly window.
            start = min(periods)[:4]+"-01"
            entry["refresh_ranges"].append(dict(start=start, end=f"{year}-12"))
    rows = []
    all_values = grouped(raw)
    for (key, period), value in sorted(all_values.items()):
        if key == "total":
            continue
        derived = key in ("tsf_direct_flow", "tsf_offbalance_flow", "tsf_remaining_flow")
        url = provenance["total", period] if derived else provenance[key, period]
        note = "人民银行社融单月分项，亿元；历史口径与缺失按原表保留"
        if derived:
            note += "；本项目计算分组，公式见指标口径；非央行独立发布指标"
        add(rows, key, period, value, url, note=note)
        if derived:
            details.setdefault(key, dict(annual_directory=DIRECTORY, attachments=[], refresh_ranges=[]))
    for key, detail in details.items():
        points = [r for r in rows if r["series_id"] == key]
        detail["attachments"] = sorted(set(detail["attachments"] + [r["source_url"] for r in points]))
        if key in ("tsf_direct_flow", "tsf_offbalance_flow", "tsf_remaining_flow"):
            detail["refresh_ranges"] = [dict(start=min(r["period"] for r in points), end=f"{max(years)}-12")]
        detail["coverage"] = "官方历史分项；2002—2005年信托贷款空白不补零；2019表附录回溯2017年起分项，政府债券不等于旧地方专项债"
        detail["definition_notes"] = [
            "2018年纳入存款类金融机构ABS、贷款核销与地方专项债；2019年纳入国债和地方一般债并官方回溯至2017年",
            "2023年增加消费金融公司、理财公司、金融资产投资公司等三类机构；保留当期统计范围，不反推旧值",
        ]
    return rows, details

"""Monthly local debt stocks and issuance; legacy purposes stay separate."""

from decimal import Decimal
import re

from macro_common import add, number
from macro_fiscal_nbs import compact
from macro_fiscal_mof import DEBT_ARCHIVES, archive, article

NUMBER = r"(\d+(?:\.\d+)?)"


def debt_period(title):
    if title == "2017年11月地方政府债务情况":
        return "2017-11"
    m = re.fullmatch(r"(\d{4})年(\d{1,2})月地方政府债券发行和债务余额情况", compact(title))
    if m:
        return f"{m[1]}-{int(m[2]):02}"
    if title == "2018年地方政府债券发行和债务余额情况":
        return "2018-12"
    raise ValueError("Unknown local debt report title: "+title)


def parse_debt(title, text, url, published):
    period = debt_period(title)
    text = compact(text)
    match = re.search(r"一、全国地方政府债券", text)
    if not match:
        raise ValueError("Local debt issuance heading missing")
    # Source changes subsection layout but always separates current month from
    # YTD. Jan's 1-1 range is the same single month; other ranges are not.
    issue = re.split(r"\(二\)|二、全国地方政府债务|(?:\d{4}年)?1[-—至]\d{1,2}月|2018年[,，]全国发行", text[match.start():], maxsplit=1)[0]
    if not re.search(rf"(?:{period[:4]}年)?{int(period[-2:])}月份?[,，]", issue):
        raise ValueError("Local debt current-month context missing")
    balance = re.split(r"二、全国地方政府债务余额情况", text, maxsplit=1)
    if len(balance) != 2:
        raise ValueError("Local debt balance heading missing")
    # The balance section must identify the same month, not just the limit year.
    month_pattern = rf"(?:{int(period[-2:])}月)?" if period.endswith("-12") else rf"{int(period[-2:])}月"
    if not re.search(rf"截至(?:{period[:4]}年)?{month_pattern}末", balance[1]):
        raise ValueError("Local debt balance period mismatch")
    found = {}

    def record(key, pattern, section, value=None):
        m = re.search(pattern, section)
        if m:
            found[key] = (number(m[1] if value is None else value), m[0])

    record("issuance_gross", r"全国发行地方政府债券(?:合计)?"+NUMBER+r"亿元", issue)
    if "issuance_gross" not in found:
        raise ValueError("Local debt monthly gross amount missing")
    record("issuance_new", r"新增(?:地方政府)?债券"+NUMBER+r"亿元", issue)
    record("issuance_swap_refinancing", r"置换债券[和或]再融资债券(?:\([^)]*\))?"+NUMBER+r"亿元", issue)
    if "issuance_swap_refinancing" not in found:
        record("issuance_refinancing", r"(?<!和)(?<!或)再融资债券(?:\([^)]*\))?"+NUMBER+r"亿元", issue)
        record("issuance_swap", r"置换债券"+NUMBER+r"亿元", issue)
    for key, pattern in [("new", r"全部[为是]新增债券"), ("refinancing", r"全部[为是]再融资债券"),
                         ("swap", r"全部[为是]置换债券(?![或和]再融资)"),
                         ("swap_refinancing", r"全部[为是]置换债券[或和]再融资债券")]:
        full = "issuance_"+key
        if full not in found:
            record(full, pattern, issue, found["issuance_gross"][0])
            if full in found:
                found[full] = found[full][0], found["issuance_gross"][1]+"；"+found[full][1]
    if "issuance_new" not in found:
        record("issuance_new", r"未发行新增债券", issue, Decimal(0))
    for key, pattern in [("total", "全国地方政府债务余额"), ("general", "一般债务"), ("special", "专项债务")]:
        record("local_"+key+"_stock", pattern+NUMBER+r"亿元?", balance[1])
        if "local_"+key+"_stock" not in found:
            raise ValueError("Local debt stock missing")
    if abs(found["local_total_stock"][0]-found["local_general_stock"][0]-found["local_special_stock"][0]) > 1:
        raise ValueError("Local debt stock components mismatch")
    purposes = [k for k in found if k.startswith("issuance_") and k != "issuance_gross"]
    if (len(purposes) >= 2 or "全部" in issue) and abs(found["issuance_gross"][0]-sum(found[k][0] for k in purposes)) > 1:
        raise ValueError("Local debt issuance purpose components mismatch")
    rows = []
    for key, (value, quote) in found.items():
        note = ("月末法定债务存量" if key.endswith("stock") else "当月发行流量；保留原报告用途类别")+"；原文："+quote
        if key.endswith("stock") and not quote.endswith("元"):
            note += "；原文漏写元，按同段明确亿元的分项及加总核验"
        if value < 0:
            raise ValueError("Negative local debt amount")
        add(rows, "fiscal_"+key, period, value, url, published, note)
    return rows


def collect(backfill=False):
    periods, pages, duplicates = {}, [], []
    for base in (DEBT_ARCHIVES if backfill else DEBT_ARCHIVES[-1:]):
        entries, archive_pages = archive(base, r"^(?:\d{4}年(?:\d{1,2}月)?地方政府债券发行和债务余额情况|2017年11月地方政府债务情况)$", backfill)
        pages.extend(archive_pages)
        for e in entries:
            soup, paragraphs, published = article(e["url"])
            period = debt_period(e["title"])
            batch = parse_debt(e["title"], soup.get_text(), e["url"], published)
            if period in periods:
                values = lambda rows: {r["series_id"]: number(r["value"]) for r in rows}
                if values(periods[period]) != values(batch):
                    raise ValueError("Migrated debt reports disagree: "+period)
                duplicates.append(dict(period=period, first_url=periods[period][0]["source_url"], migration_url=e["url"], values_match=True))
                # Keep old URL as stable provenance; avoid migration timestamp churn.
                continue
            periods[period] = batch
    rows = [r for p in sorted(periods) for r in periods[p]]
    detail = dict(archive_pages=pages, report_count=len(periods), migration_checks=duplicates, requested_window_complete=True,
        coverage_note="全量回溯同时查询旧预算司与新债务管理司档案，日常查询现行债务管理司首页；已核验104个月自2017-11起，2018-01/02暂缺。迁移重复项必须数值相同，发布日期采用页面PubDate/页脚，不使用URL迁移日期。",
        definition_notes=["2017—2019早期置换、置换与再融资合计和纯再融资分别存放；未提及不填零。只有明确未发行新增债券才记0。",
                          "部分页脚与正文日期不一致，采用页面PubDate/页脚；3处余额单位漏写元，按同段分项和加总核对，逐行保留说明。"])
    return rows, detail

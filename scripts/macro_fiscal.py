"""Integrate complete fiscal histories with explicit source priority."""

from macro_common import number
from macro_fiscal_nbs import collect as collect_nbs
from macro_fiscal_mof import collect_budget
from macro_fiscal_debt import collect as collect_debt
from macro_fiscal_annual import collect as collect_annual
from macro_render import ROOT, load_topic


def budget_supplements(nbs_rows, previous):
    """Recheck old release-only gaps inside the database's full refresh window."""
    present = {(r["series_id"], r["period"]) for r in nbs_rows}
    return sorted({r["source_url"] for r in previous
                   if r["series_id"] in {"fiscal_revenue_ytd", "fiscal_expenditure_ytd"}
                   and (r["series_id"], r["period"]) not in present
                   and r["source_url"].startswith("https://gks.mof.gov.cn/tongjishuju/")})


def merge_budget(nbs_rows, mof_rows):
    """Revised NBS headline history wins; MOF fills gaps/new periods only."""
    found = {(r["series_id"], r["period"]): r for r in nbs_rows}
    differences = []
    for row in mof_rows:
        identity = row["series_id"], row["period"]
        if identity in found:
            old = found[identity]
            if number(old["value"]) != number(row["value"]):
                differences.append(dict(series_id=row["series_id"], period=row["period"],
                    selected_nbs_value=old["value"], mof_release_value=row["value"], mof_url=row["source_url"]))
            continue
        found[identity] = row
    return list(found.values()), differences


def collect(backfill=False):
    nbs_rows, metadata = collect_nbs(backfill)
    previous = load_topic("fiscal")[0] if (ROOT / "data/macro/fiscal.csv").exists() else []
    budget, budget_detail = collect_budget(backfill, budget_supplements(nbs_rows, previous))
    rows, differences = merge_budget(nbs_rows, budget)
    budget_detail.update(source_priority="NBS年度与月度主体优先；财政部仅补月度金额缺口和新期，税收/非税/基金/土地按财政部原文。不同来源、发布版本分项不强求相等。",
        overlapping_value_differences=differences,
        coverage_note="国库司23页历史起点2008-07；不能相信页面写死的4页。基金累计自2012-06，2013/2014仅季度末；土地2015-03和2019-03至12原文仅有增速，金额留空。",
        definition_notes=["月度金额累计至当前月，早期月报当月与累计并存，按明确期间上下文提取；年度值不补月度12月。"])
    for key in {r["series_id"] for r in budget}:
        detail = metadata.setdefault(key, {})
        detail["supplemental_sources"] = [budget_detail]
    for collector in (collect_debt, collect_annual):
        batch, detail = collector(backfill)
        rows.extend(batch)
        for key in {r["series_id"] for r in batch}:
            metadata[key] = dict(detail)
    identities = [(r["series_id"], r["period"]) for r in rows]
    if len(identities) != len(set(identities)):
        raise ValueError("Duplicate integrated fiscal observation")
    for key in {r["series_id"] for r in rows}:
        periods = [r["period"] for r in rows if r["series_id"] == key]
        metadata[key]["refresh_ranges"] = [dict(start=min(periods), end=max(periods))]
    print("Fiscal total:", len(rows), "observations", flush=True)
    return rows, metadata

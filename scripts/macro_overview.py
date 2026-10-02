"""Generate the macro overview from committed snapshots, without network access."""

import csv
from decimal import Decimal
from html import escape
import json
from pathlib import Path

from macro_catalog import SERIES

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path("docs/data/overview.md")

# A small reading dashboard, not a composite score. Each metric keeps its own clock.
GROUPS = [
    ("增长与景气", "先看季度产出的实际增长，再用月度调查观察方向；年度 GDP 保留作长期背景。", [
        ("quarterly-gdp", "gdp_q_yoy", "独立本季度与上年同季度比较；不是年内累计，也不是季调环比。"),
        ("activity", "pmi_manufacturing", "50 是调查扩张与收缩的分界；指数高低不是 GDP 增速。"),
    ]),
    ("物价", "分清居民消费端与工业生产端；同比增速与价格水平也不同。", [
        ("prices", "cpi_yoy", "同比回落可能只是涨价放缓，需结合环比、核心 CPI 和基数。"),
        ("prices", "ppi_yoy", "反映工业出厂价格，向消费端的传导受成本、利润和需求影响。"),
    ]),
    ("货币与信用", "存款增加与实体融资扩张是两个角度，不能相加。", [
        ("money-credit", "m2_yoy", "采用官方可比同比；M2 增长并不等于消费或投资同比增长。"),
        ("money-credit", "tsf_stock_yoy", "存量融资的同比增速；总量变化还需看政府债券、企业与居民融资结构。"),
    ]),
    ("利率", "政策操作与长期市场收益率分别观察。", [
        ("rates", "repo_7d", "最新有操作且公告明确利率的日期；无操作日不补零、不复制利率。"),
        ("rates", "yield_10y", "国债收益率曲线的 10 年期限，包含政策、通胀及期限溢价预期。"),
    ]),
    ("就业与收入", "劳动力市场与购买力互相补充，但统计频率不同。", [
        ("employment-income", "unemployment", "全国城镇调查口径；还需结合工时、劳动参与和收入理解。"),
        ("employment-income", "income_real_ytd_yoy", "Q2 是上半年、Q3 是前三季度；前后累计同比之差不是单季增速。"),
    ]),
    ("外贸与汇率", "贸易金额与货币价格分开读。", [
        ("trade-fx", "exports", "单月美元金额，含数量与价格影响；前次差额没有剔除季节性。"),
        ("trade-fx", "usdcny_mid", "人民币/美元；数值上升表示人民币对美元贬值，中间价并非成交价。"),
    ]),
]


def numeric(value):
    if value in (None, ""):
        return None
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("Overview cannot use non-finite observations")
    return result


def fmt(value):
    """Match the topic charts' eight-decimal display; arithmetic stays exact."""
    result = format(value, ",.8f")
    return result.rstrip("0").rstrip(".") if "." in result else result


def summarize(rows, key):
    selected = sorted((r for r in rows if r["series_id"] == key and r["country"] == "CHN"),
                      key=lambda r: r["period"])
    if len({r["period"] for r in selected}) != len(selected):
        raise ValueError(f"Duplicate overview periods: {key}")
    valid = [r for r in selected if numeric(r["value"]) is not None]
    if not valid:
        raise ValueError(f"No valid overview observations: {key}")
    latest = valid[-1]
    previous = valid[-2] if len(valid) > 1 else None
    window_year = int(latest["period"][:4]) - 4
    window = [r for r in valid if int(r["period"][:4]) >= window_year]
    values = [numeric(r["value"]) for r in window]
    low, high, current = min(values), max(values), numeric(latest["value"])
    return dict(latest=latest, previous=previous, first=valid[0]["period"],
                available_end=selected[-1]["period"], count=len(valid),
                delta=current-numeric(previous["value"]) if previous else None,
                low=low, high=high, window_first=window[0]["period"],
                window_count=len(window), window_year=window_year,
                position=(current-low)/(high-low)*100 if high != low else None)


def load_snapshots(root):
    topics = {topic for _, _, entries in GROUPS for topic, _, _ in entries}
    snapshots = {}
    for topic in sorted(topics):
        stem = root / ("data/gdp" if topic == "gdp" else f"data/macro/{topic}")
        with stem.with_suffix(".csv").open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        meta = json.loads(stem.with_suffix(".metadata.json").read_text(encoding="utf-8"))
        snapshots[topic] = rows, meta
    return snapshots


def card(topic, key, note, rows, meta):
    summary = summarize(rows, key)
    spec = dict(label="GDP 实际年度增速", unit="%", frequency="A", source="World Bank WDI") if topic == "gdp" else SERIES[key]
    latest, previous = summary["latest"], summary["previous"]
    label, unit = spec["label"], spec["unit"]
    frequency = {"A": "年度", "Q": "季度", "M": "月度", "D": "日度"}[spec["frequency"]]
    if spec["frequency"] == "Q":
        frequency += "（年内累计）" if "_ytd" in key else "（独立单季）"
    change_unit = "个百分点" if unit == "%" else unit
    if previous:
        delta = summary["delta"]
        change = ("+" if delta > 0 else "") + fmt(delta)
        prior = f"上一有效观测：{previous['period']} · {fmt(numeric(previous['value']))} {unit}；差值 **{change} {change_unit}**。"
    else:
        prior = "尚无前次有效观测。"
    low, high = fmt(summary["low"]), fmt(summary["high"])
    if summary["position"] is None:
        meter = "区间内有效观测均相同，位置条不绘制。"
    else:
        description = f"{latest['period']} 的值为 {fmt(numeric(latest['value']))} {unit}；区间最低 {low}，最高 {high}"
        meter = (f'<div class="overview-range" role="img" aria-label="{escape(description, quote=True)}">'
                 f'<span style="left:{summary["position"]:.4f}%"></span></div>')
    gap = (f"已收录期间延伸至 {summary['available_end']}，其末期为空缺，最新有效值仍为 {latest['period']}。\n\n"
           if summary["available_end"] != latest["period"] else "")
    published = latest.get("published_at") or "未提供逐条日期"
    source = latest["source_url"]
    if "stream/esData" in source:
        page = "quarterData" if spec["frequency"] == "Q" else "monthData"
        source = f"https://data.stats.gov.cn/dg/website/page.html#/pc/national/{page}"
    return f''':::{{admonition}} {label}
:class: overview-card
:name: overview-{key}

**{fmt(numeric(latest['value']))} {unit}**

统计期 **{latest['period']}** · {frequency}

{prior}

{gap}{meter}

范围：**{low} — {high} {unit}**；{summary['window_first']} 至 {latest['period']}，{summary['window_count']} 个有效观测。

{note}

[查看完整历史与口径]({topic}.md) · [来源：{spec['source']}]({source})

本项目覆盖 {summary['first']} 至 {latest['period']}（{summary['count']} 条）。来源发布日期：{published}；快照获取：{meta['retrieved_at']}。
:::
'''


GUIDE = '''## 把指标放回传导链

![政策利率影响融资条件，再影响借贷支出、需求产出与物价；每一步均受到风险、收入预期和时间滞后的约束](../images/learning/rate-transmission.drawio.svg)

[下载可编辑源图](../images/learning/rate-transmission.drawio) · [阅读完整的利率解释](../interest-rates.md)

虚线表示可能的影响。各环节的反应强弱与先后没有固定保证，也可能被其他因素抵消。

| 传导环节 | 用哪些数据核对 | 还缺什么证据 |
|---|---|---|
| 政策操作 → 融资条件 | [逆回购、LPR、国债收益率](rates.md) | 实际贷款利率、风险加点、存量合同重定价情况 |
| 融资条件 → 借贷和支出 | [社融总量](money-credit.md)、[融资与信贷结构](credit-structure.md)、[房地产](property.md)、[消费与投资](activity.md) | 贷款用途、订单、收入预期；余额不能替代新增需求 |
| 支出 → 生产与就业 | [工业与 PMI](activity.md)、[就业与收入](employment-income.md) | 库存、工时、劳动参与率、供给约束 |
| 需求与供给 → 价格 | [CPI、核心 CPI、PPI](prices.md) | 能源与食品冲击、进口成本、历史基数 |

政策也会回应经济变化。例如经济走弱可能促使降息，因此“降息与增长偏弱同时出现”不能证明降息造成了走弱。月度、季度和日度序列需要先对齐期间，再讨论先后关系。

## 三种组合，练习怎样读

以下是**条件式阅读示例**，不是对最新数据自动作出的经济判断。展开查看解释，先提出假设，再寻找支持或反对的证据。

<details class="overview-scenario">
<summary>M2 增长，但物价偏弱</summary>

**可以同时发生。** 存款余额增加，不代表资金同等速度地转为消费或投资；居民储蓄意愿、企业订单、融资结构与供给变化都可能影响支出和价格。

先比较 [M2 与社融](money-credit.md)，通过[融资与信贷结构](credit-structure.md)区分渠道和借款人，再看 [社零与投资](activity.md)、[CPI 与核心 CPI](prices.md)。CPI 同比还受基数、食品和能源影响。只凭 M2 与 CPI 两条线，尚不能证明资金“闲置”，也不能推算下一月通胀。

继续学习：[银行怎样创造存款](../banking-and-money-creation.md) · [货币与信用](../money-and-credit.md)

</details>

<details class="overview-scenario">
<summary>出口增长，但人民币对美元贬值</summary>

**出口只是外汇供求的一部分。** 进口、服务贸易、资本流动、结汇意愿、利差及预期都可能同时变化。出口的美元金额还包含数量和价格因素。

核对 [进出口与人民币汇率](trade-fx.md)时，出口按月、中间价按日，不能把两个不同日期的变化直接配对。USD/CNY 中间价上升表示人民币对美元贬值，但中间价不是即期成交价；还需国际收支、资本流动和市场汇率证据。

继续学习：[汇率如何形成](../exchange-rates.md)

</details>

<details class="overview-scenario">
<summary>政策利率下调，长期国债收益率却没有同步下降</summary>

**短期政策操作与长期定价对应不同信息。** 市场可能已提前计价降息，也可能同时上调未来增长、通胀或期限溢价预期。债券供求也会影响收益率。

先在 [利率专题](rates.md)核对操作日期、收益率日期和此前变化，再检查 [物价](prices.md)与[景气](activity.md)。仅凭一次降息，无法确定长期债券价格或收益率将怎样变化。

继续学习：[债券价格与收益率](../investing/bonds.md) · [政策传导](../interest-rates.md)

</details>

## 使用边界

- “最新”指各来源快照的最新有效观测；统计期、来源发布日期与快照获取时间分别列示，获取时间不是发布日期。
- 前次差值只是两个有效观测相减。百分比之差用**个百分点**，PMI 用指数点；它不自动等于环比增速，也不保证两个观测紧邻。
- 位置条是 `(最新值 − 窗口最低值) ÷ (窗口最高值 − 窗口最低值)`，不是历史百分位、经济评分或投资信号。区间内全为同值时不绘制位置。
- 总览最多显示八位小数，计算使用入库原值；完整精度以专题 CSV 为准。
- 窗口以每个指标最新有效观测所属年及此前四年为边界，保留该范围内实际观测；不足五年的只用已有数据。不同卡片可能对应不同窗口，不能比较条长来排名经济表现。
- 高低值可能受到基数、季节性、异常冲击或统计范围变化影响；先读专题中的口径说明。缺失不补零，所有完整历史仍保存在专题图表、表格与 CSV 中。

下一步可按[数据阅读练习](reading-exercise.md)复核一组数据，也可查看[全部专题](index.md)、[历史覆盖与缺口](history-coverage.md)和[最近自动更新状态](https://github.com/calcky/finance/actions/workflows/update-gdp.yml)。
'''


def document(snapshots):
    lines = ["<!-- Generated by scripts/macro_overview.py from committed data. -->",
             "# 中国宏观经济总览", "",
             "先看增长与物价，再看融资条件、家庭状况和对外收支。每张卡片保留指标自己的统计期，帮助选择下一步要读的专题。", "",
             "**读法：最新值 → 前次观测 → 历史范围 → 查口径。** 位置条显示最近五个日历年内已收录观测的最低值、最高值与最新位置；向右只表示数值较高。[季度 GDP](quarterly-gdp.md)观察近期增长，[年度 GDP](gdp.md)用于长期背景。", ""]
    for title, intro, entries in GROUPS:
        lines += [f"## {title}", "", intro, "", "::::{container} overview-grid", ""]
        for topic, key, note in entries:
            rows, meta = snapshots[topic]
            lines += [card(topic, key, note, rows, meta), ""]
        lines += ["::::", ""]
    lines += [GUIDE]
    return "\n".join(lines)


def main():
    # Build all content before publishing; an invalid/missing series keeps the old page.
    text = document(load_snapshots(ROOT))
    target = ROOT / OUTPUT
    if not target.exists() or target.read_text(encoding="utf-8") != text:
        temporary = target.with_suffix(".md.tmp")
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(target)
    print("Overview: 6 dimensions, 12 indicators; source snapshots unchanged.")


if __name__ == "__main__":
    main()

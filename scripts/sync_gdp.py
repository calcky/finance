"""Sync World Bank annual GDP data and build an offline-readable topic.

Default: fetch, validate, render, then publish files. --render-only uses the
committed snapshot. Nothing is written until all requests and rendering pass.
"""

import argparse
import csv
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from io import StringIO
import json
import os
from pathlib import Path
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.worldbank.org/v2"
LICENSE = "https://data.worldbank.org/summary-terms-of-use"
SERIES = {
    "gdp_cny": ("NY.GDP.MKTP.CN", ("CHN",), "CNY", "GDP（现价人民币）"),
    "gdp_growth": ("NY.GDP.MKTP.KD.ZG", ("CHN",), "percent", "GDP 实际年度增速"),
    "gdp_usd": ("NY.GDP.MKTP.CD", ("CHN", "USA"), "USD", "GDP（现价美元）"),
    "gdp_per_capita_usd": ("NY.GDP.PCAP.CD", ("CHN",), "USD/person", "人均 GDP（现价美元）"),
}
FIELDS = ["series_id", "country", "period", "value", "unit", "published_at", "retrieved_at", "source_url", "note"]


def fetch_json(url):
    for attempt in range(3):
        try:
            request = Request(url, headers={"User-Agent": "calcky-finance/1.0 (public WDI educational data)"})
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except (URLError, TimeoutError) as error:
            if isinstance(error, HTTPError) and error.code not in (429, 500, 502, 503, 504):
                raise
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def parse_response(payload, series_id, retrieved_at):
    indicator, countries, unit, _ = SERIES[series_id]
    if not isinstance(payload, list) or len(payload) != 2:
        raise ValueError(f"{series_id}: not a WDI data response")
    meta, observations = payload
    if (meta.get("page") != 1 or meta.get("pages") != 1
            or str(meta.get("sourceid")) != "2"
            or not isinstance(observations, list) or len(observations) != meta.get("total")):
        raise ValueError(f"{series_id}: wrong dataset or incomplete pagination")
    updated = meta.get("lastupdated", "")
    if date.fromisoformat(updated) > datetime.now(timezone.utc).date():
        raise ValueError("Future source update date")
    result, seen = [], set()
    for item in observations:
        country, period = item["countryiso3code"], item["date"]
        if country not in countries or item["indicator"]["id"] != indicator:
            raise ValueError(f"{series_id}: unexpected country or indicator")
        if not isinstance(period, str) or len(period) != 4 or not period.isascii() or not period.isdigit():
            raise ValueError(f"Invalid annual period: {period}")
        if not 1960 <= int(period) < datetime.now(timezone.utc).year:
            raise ValueError(f"Out-of-scope annual period: {period}")
        key = (country, period)
        if key in seen:
            raise ValueError(f"Duplicate observation: {key}")
        seen.add(key)
        value = item["value"]
        if value is not None:
            if isinstance(value, bool):
                raise ValueError("Boolean is not a data value")
            try:
                number = Decimal(str(value))
            except InvalidOperation as error:
                raise ValueError("Non-numeric value") from error
            if not number.is_finite():
                raise ValueError("Non-finite value")
            if (series_id == "gdp_growth" and not -100 < number < 100) or (series_id != "gdp_growth" and number <= 0):
                raise ValueError(f"Implausible {series_id} value: {number}")
            value = str(value)
        result.append(dict(zip(FIELDS, [
            series_id, country, period, value if value is not None else "", unit,
            "", retrieved_at,
            f"{API}/country/{country}/indicator/{indicator}?source=2&date={period}&format=json",
            item.get("obs_status") or "",
        ])))
    for country in countries:
        available = [r for r in result if r["country"] == country and r["value"]]
        if len(available) < 30 or max(int(r["period"]) for r in available) < datetime.now(timezone.utc).year - 3:
            raise ValueError(f"{series_id}/{country}: insufficient or stale history")
    return result, updated


def key(row):
    return row["series_id"], row["country"], row["period"]


def check_revision(old, new):
    previous = {key(r): r for r in old}
    current = {key(r): r for r in new}
    if len(current) != len(new) or len(previous) != len(old):
        raise ValueError("Duplicate snapshot keys")
    if previous.keys() - current.keys():
        raise ValueError("Source lost historical observations; keep the previous snapshot")
    for k, row in previous.items():
        if row["value"] and not current[k]["value"]:
            raise ValueError(f"Source replaced a known value with null: {k}")
        if row["unit"] != current[k]["unit"]:
            raise ValueError(f"Unit changed: {k}")
    added = len(current.keys() - previous.keys())
    revised = sum(previous[k]["value"] != current[k]["value"] for k in previous)
    return added, revised


def meaningful_rows(rows):
    # A check timestamp alone must never generate a daily Git commit.
    return [{k: v for k, v in row.items() if k != "retrieved_at"}
            for row in sorted(rows, key=key)]


def load_snapshot():
    path = ROOT / "data/gdp.csv"
    if not path.exists():
        return [], {}
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    meta = json.loads((ROOT / "data/gdp.metadata.json").read_text(encoding="utf-8"))
    return rows, meta


def collect(old_rows, old_meta):
    retrieved = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows, descriptions = [], {}
    for name, (indicator, countries, unit, label) in SERIES.items():
        url = f"{API}/country/{';'.join(countries)}/indicator/{indicator}?source=2&format=json&per_page=20000"
        batch, updated = parse_response(fetch_json(url), name, retrieved)
        definition = fetch_json(f"{API}/indicator/{indicator}?source=2&format=json")
        if not isinstance(definition, list) or len(definition) != 2 or len(definition[1]) != 1:
            raise ValueError(f"Missing indicator metadata: {indicator}")
        info = definition[1][0]
        if info["id"] != indicator or info["source"]["id"] != "2" or not info.get("sourceNote") or not info.get("sourceOrganization"):
            raise ValueError(f"Invalid indicator metadata: {indicator}")
        descriptions[name] = {
            "indicator": indicator, "countries": list(countries), "unit": unit, "label": label,
            "definition": info["sourceNote"], "providers": info["sourceOrganization"],
            "source_updated": updated, "api_url": url,
        }
        rows.extend(batch)
    rows.sort(key=key)
    added, revised = check_revision(old_rows, rows)
    meta = {
        "dataset": "World Development Indicators (source 2)", "retrieved_at": retrieved,
        "license": "World Bank default CC BY 4.0, subject to dataset exceptions and additional terms",
        "license_url": LICENSE, "series": descriptions,
    }
    # The WDI database refresh date is not the publication date of each value.
    comparable = lambda m: {k: v for k, v in m.items() if k != "retrieved_at"}
    if meaningful_rows(rows) == meaningful_rows(old_rows) and comparable(meta) == comparable(old_meta):
        print("No observations or source metadata changed; snapshot retained.")
        return old_rows, old_meta
    print(f"Snapshot update: {added} added keys, {revised} revised values (metadata may also change).")
    return rows, meta


def values(rows, series, country="CHN"):
    return {int(r["period"]): float(r["value"]) if r["value"] else float("nan")
            for r in rows if r["series_id"] == series and r["country"] == country}


def latest(rows, series, country="CHN"):
    return max((r for r in rows if r["series_id"] == series and r["country"] == country and r["value"]),
               key=lambda r: r["period"])


def render_charts(rows, meta, destination):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    from render_learning_charts import configure_font

    # Match the CI font so render-only builds do not alternate glyph paths.
    configure_font(font_manager.findfont("Droid Sans Fallback", fallback_to_default=False))
    out = destination / "docs/images/data"
    out.mkdir(parents=True)
    charts = [
        ("gdp-china", "中国 GDP：经济规模", "现价人民币，万亿元", "gdp_cny", 1e12, ("CHN",)),
        ("gdp-growth", "中国 GDP：实际增长速度", "实际年度增速，%", "gdp_growth", 1, ("CHN",)),
        ("gdp-per-capita", "中国人均 GDP：总产出除以人口", "现价美元 / 人", "gdp_per_capita_usd", 1, ("CHN",)),
        ("gdp-comparison", "中美 GDP：同一美元计价口径", "现价美元，万亿美元", "gdp_usd", 1e12, ("CHN", "USA")),
    ]
    for filename, title, unit, series, divisor, countries in charts:
        fig, ax = plt.subplots(figsize=(12, 6.5))
        fig.subplots_adjust(left=.12, right=.95, top=.77, bottom=.29)
        fig.text(.06, .92, title, fontsize=25)
        fig.text(.06, .84, unit + "；年度历史数据", fontsize=17)
        for country, color in zip(countries, ("#3675b5", "#268566")):
            data = values(rows, series, country)
            years = sorted(data)
            ax.plot(years, [data[y] / divisor for y in years], linewidth=2.5,
                    color=color, linestyle="--" if country == "USA" else "-",
                    label={"CHN": "中国", "USA": "美国"}[country])
            last = latest(rows, series, country)
            y = float(last["value"]) / divisor
            ax.scatter([int(last["period"])], [y], color=color, s=40, zorder=3)
        ax.set_xlabel("统计年份")
        ax.set_ylabel(unit)
        ax.ticklabel_format(axis="y", style="plain", useOffset=False)
        ax.grid(axis="y", color="#e5eaf0")
        if series == "gdp_growth":
            ax.axhline(0, color="#8492a6", linewidth=1)
        else:
            ax.set_ylim(bottom=0)
        if len(countries) > 1:
            ax.legend(frameon=False)
        last_years = "；".join(f"{ {'CHN': '中国', 'USA': '美国'}[c]}至 {latest(rows, series, c)['period']} 年" for c in countries)
        caveat = {"gdp_cny": "现价金额包含价格变化；不能直接用它计算实际增速。",
                  "gdp_growth": "直接采用 WDI 实际增长序列；不是人民币或美元金额的同比。",
                  "gdp_per_capita_usd": "人均产出不等于个人收入；美元计价还受汇率变化影响。",
                  "gdp_usd": "市场汇率换算，非购买力平价（PPP）；不能据此比较生活水平。"}[series]
        fig.text(.06, .14, f"来源：World Bank · WDI；{last_years}", fontsize=15)
        fig.text(.06, .085, caveat, fontsize=14)
        fig.text(.06, .035, f"来源库更新：{meta['series'][series]['source_updated']}；快照：{meta['retrieved_at'][:10]}（UTC）", fontsize=12)
        buffer = StringIO()
        fig.savefig(buffer, format="svg", metadata={"Date": None, "Title": title,
                    "Description": meta["series"][series]["api_url"]})
        (out / f"{filename}.svg").write_text("\n".join(x.rstrip() for x in buffer.getvalue().splitlines()) + "\n", encoding="utf-8")
        plt.close(fig)


def render_page(rows, meta):
    specs = [("gdp_cny", "CHN", 1e12, "万亿元"), ("gdp_growth", "CHN", 1, "%"),
             ("gdp_per_capita_usd", "CHN", 1, "美元 / 人"), ("gdp_usd", "CHN", 1e12, "万亿美元"),
             ("gdp_usd", "USA", 1e12, "万亿美元")]
    summary = []
    for series, country, divisor, unit in specs:
        row = latest(rows, series, country)
        name = ("美国" if country == "USA" else "中国") + SERIES[series][3]
        summary.append(f"| {name} | {row['period']} | {float(row['value']) / divisor:,.2f} | {unit} |")
    lookup = {key(r): r for r in rows}
    history = []
    for year in sorted({r["period"] for r in rows}, reverse=True):
        cells = []
        for series, country, divisor, _ in specs:
            row = lookup.get((series, country, year))
            cells.append(f"{float(row['value']) / divisor:,.2f}" if row and row["value"] else "—")
        history.append("| " + " | ".join([year, *cells]) + " |")
    updates = ", ".join(sorted({s["source_updated"] for s in meta["series"].values()}))
    sources = "\n".join(f"- [{SERIES[k][3]}](https://data.worldbank.org/indicator/{v['indicator']})：`{v['indicator']}`。"
                        for k, v in meta["series"].items())
    return f"""<!-- Generated by scripts/sync_gdp.py; edit the script, not this page. -->
# GDP 数据专题

从经济规模、实际增长、人均产出和跨国比较四个角度阅读 GDP。这里是真实年度数据，与课程中的教学假设分开；来源为世界银行 World Development Indicators（WDI），不保证与国家统计局最新季度快报同步。

## 最新可得读数

| 指标 | 统计年份 | 数值 | 单位 |
|---|---|---|---|
{chr(10).join(summary)}

- **来源库更新时间**：{updates}。这是 WDI 数据库的更新日期，不是每条观测的发布日期。
- **本快照获取时间**：{meta['retrieved_at']}。只有观测或来源元数据变化才更新快照；最近检查是否成功请看 [GitHub 同步记录](https://github.com/calcky/finance/actions/workflows/update-gdp.yml)。
- **发布时间**：接口未提供逐条发布时间，CSV 的 `published_at` 留空。历史数据可修订，不把本次读数当作当年首次公布值。
- **显示精度**：表格保留两位小数，CSV 保存接口数值。缺失值显示“—”，不是零。

## 1. 经济规模：人民币现价 GDP

![中国历年人民币现价 GDP，纵轴单位万亿元，从零起；包含价格变化，不能据此直接推算实际增速。](../images/data/gdp-china.svg)

这张图回答“一年生产的最终产品与服务，按当期价格合计有多少”。金额增长可能来自产出增加，也可能来自价格上涨。早期值在线性坐标上显得小，不代表那时没有经济活动。

## 2. 增长速度：实际 GDP 年度增速

![中国历年实际 GDP 增速，单位百分比，零线区分增长与收缩。](../images/data/gdp-growth.svg)

实际增速剔除价格变化。增速从 6% 降到 4% 表示增长放慢，通常不是产出下降；低于 0 才表示该期间实际总产出收缩。这条序列直接使用 WDI 的实际增速，不能用上一张现价金额计算后替代。

## 3. 人均 GDP：不等于人均收入

![中国历年人均 GDP，以现价美元每人表示；这是产出与人口之比，不是工资或可支配收入。](../images/data/gdp-per-capita.svg)

人均 GDP 是总产出除以人口，不能理解成每个人能分到这些钱。这里选择美元口径方便跨国阅读，但汇率和价格也会影响走势；讨论真实生活水平，还要参考实际购买力、居民收入及分配。

## 4. 中美对照：美元 GDP

![中国和美国历年现价美元 GDP，在同一坐标轴上对照，单位万亿美元，非购买力平价口径。](../images/data/gdp-comparison.svg)

两条曲线采用相同指标和单位，但用市场汇率换算的美元规模不等于实际产量比较，也不等于 PPP。人民币贬值可能压低美元计价的中国 GDP，即使当年实际产出仍在增长。最新年份分别标明，比较时应使用共同年份。

## 历年明细与下载

{{download}}`下载 CSV <../../data/gdp.csv>` · {{download}}`下载来源元数据 <../../data/gdp.metadata.json>` · [GitHub 数据与说明](https://github.com/calcky/finance/tree/main/data)

| 年份 | 中国 GDP（万亿元） | 中国实际增速（%） | 中国人均 GDP（美元） | 中国 GDP（万亿美元） | 美国 GDP（万亿美元） |
|---|---|---|---|---|---|
{chr(10).join(history)}

## 来源、口径与修订

{sources}

归属：**The World Bank: World Development Indicators**，及指标元数据列明的国家统计机构、央行、OECD 和世界银行估算等提供方。具体定义与提供方保存在下载的元数据中。WDI 是汇编数据源，不能把所有历史观测都称为同一天发布的国家统计局原始值。

遵循[世界银行数据使用条款]({LICENSE})及相应元数据要求；其默认许可为 CC BY 4.0，附加条件和第三方例外以来源为准。本专题的单位换算、中文说明和图表由本项目制作，不代表世界银行认可。

每天检查新值和历史修订。数据、图表、表格由同一快照生成；采集或校验失败不发布新快照。Git 历史保留**本项目开始采集以来**的版本，不提供采集前的历史初值。[查看数据变更](https://github.com/calcky/finance/commits/main/data/gdp.csv)。

继续阅读：[GDP 与通胀原理](../growth-and-inflation.md) · [如何阅读宏观数据](../reading-macro-data.md) · [数据更新规则](index.md)。
"""


def publish(rows, meta):
    # Stage all artifacts before touching the last working snapshot.
    with tempfile.TemporaryDirectory(prefix="finance-gdp-") as directory:
        staging = Path(directory)
        (staging / "data").mkdir()
        with (staging / "data/gdp.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        (staging / "data/gdp.metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        render_charts(rows, meta, staging)
        (staging / "docs/data").mkdir()
        (staging / "docs/data/gdp.md").write_text(render_page(rows, meta), encoding="utf-8")
        changed = []
        for source in sorted(staging.rglob("*")):
            if not source.is_file():
                continue
            relative = source.relative_to(staging)
            target = ROOT / relative
            data = source.read_bytes()
            if target.exists() and target.read_bytes() == data:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
                stream.write(data)
                temp = Path(stream.name)
            temp.chmod(0o644)
            os.replace(temp, target)
            changed.append(str(relative))
        print("Updated files: " + (", ".join(changed) or "none"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render-only", action="store_true", help="Rebuild from the local snapshot without network access")
    args = parser.parse_args()
    rows, meta = load_snapshot()
    if args.render_only:
        if not rows:
            raise ValueError("No committed GDP snapshot")
        check_revision(rows, rows)
    else:
        previous = rows
        rows, meta = collect(rows, meta)
        if rows is previous:
            return
    publish(rows, meta)


if __name__ == "__main__":
    main()

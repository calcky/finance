"""Render formula-based teaching charts; no market data or network calls.

Run from any directory. SVGs go to docs/images/learning; optional PNG previews
go to --preview-dir. A CJK font must be installed, or supplied with --font.
"""

import argparse
from io import StringIO
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import PercentFormatter
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
BLUE = "#3675b5"
GREEN = "#268566"
GRAY = "#8492a6"
INK = "#203047"


def configure_font(path):
    if path:
        font_manager.fontManager.addfont(path)
        family = font_manager.FontProperties(fname=path).get_name()
    else:
        for family in ("Noto Sans CJK SC", "Microsoft YaHei", "Droid Sans Fallback", "PingFang SC"):
            try:
                font_manager.findfont(family, fallback_to_default=False)
                break
            except ValueError:
                continue
        else:
            raise SystemExit("Install a Chinese font or pass --font /path/to/font.ttf")
    plt.rcParams.update({
        "font.family": [family, "DejaVu Sans"],
        "font.size": 18,
        "axes.labelsize": 17,
        "axes.titlesize": 19,
        "xtick.labelsize": 16,
        "ytick.labelsize": 16,
        "text.color": INK,
        "axes.labelcolor": INK,
        "axes.edgecolor": GRAY,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "savefig.facecolor": "white",
        "svg.fonttype": "path",
        "svg.hashsalt": "finance-learning",
        "axes.unicode_minus": False,
    })


def canvas(title, subtitle, panels=1):
    fig, axes = plt.subplots(1, panels, figsize=(12, 6.5), squeeze=False)
    fig.subplots_adjust(left=0.10, right=0.96, bottom=0.20, top=0.72, wspace=0.37)
    fig.text(0.06, 0.92, title, fontsize=25)
    fig.text(0.06, 0.84, subtitle, fontsize=16)
    for ax in axes[0]:
        ax.set_axisbelow(True)
        ax.grid(axis="y", color="#e5eaf0", linewidth=0.8)
    return fig, axes[0]


def render(preview_dir):
    out = ROOT / "docs/images/learning"
    out.mkdir(parents=True, exist_ok=True)
    if preview_dir:
        preview_dir.mkdir(parents=True, exist_ok=True)

    def save(fig, name, description):
        svg = StringIO()
        fig.savefig(svg, format="svg", metadata={"Date": None, "Title": name, "Description": description})
        # Matplotlib leaves spaces after SVG path coordinates; keep exports diff-clean.
        (out / f"{name}.svg").write_text(
            "\n".join(line.rstrip() for line in svg.getvalue().splitlines()) + "\n",
            encoding="utf-8",
        )
        if preview_dir:
            fig.savefig(preview_dir / f"{name}.png", dpi=130)
        plt.close(fig)
        print(name)

    fig, (a, b) = canvas("复利与亏损回本：百分比不能简单相加", "教学假设；左图固定年收益 5%，无费用税项，不代表可获得的投资回报。", 2)
    years = np.arange(21)
    compound = 10000 * 1.05 ** years
    simple = 10000 * (1 + 0.05 * years)
    a.plot(years, compound / 10000, color=BLUE, linewidth=3, label="收益再投入")
    a.plot(years, simple / 10000, color=GREEN, linewidth=3, linestyle="--", label="利息不再生息")
    a.set(xlabel="持有年数", ylabel="累计金额（万元）", xlim=(0, 20), ylim=(0, 3.1))
    a.set_xticks([0, 10, 20])
    a.legend(frameon=False, fontsize=15, loc="upper left")
    a.annotate("2.65 万", (20, compound[-1] / 10000), xytext=(-65, 8), textcoords="offset points", fontsize=16, color=BLUE)
    a.annotate("2.00 万", (20, 2), xytext=(-65, -24), textcoords="offset points", fontsize=16, color=GREEN)
    loss = np.linspace(0, 80, 161)
    recovery = loss / (100 - loss) * 100
    b.plot(loss, recovery, color=BLUE, linewidth=3)
    b.scatter([50], [100], color=GREEN, s=75, zorder=3)
    b.annotate("亏 50%\n需涨 100%", (50, 100), xytext=(-115, 65), textcoords="offset points", fontsize=17,
               arrowprops={"arrowstyle": "-", "color": GRAY})
    b.set(xlabel="先前亏损幅度", ylabel="回本所需涨幅", xlim=(0, 80), ylim=(0, 420))
    b.xaxis.set_major_formatter(PercentFormatter(100))
    b.yaxis.set_major_formatter(PercentFormatter(100))
    fig.text(0.06, 0.055, "左：10000 × 1.05ⁿ；右：所需涨幅 = 亏损幅度 ÷（1 − 亏损幅度）。", fontsize=16)
    save(fig, "compound-and-recovery", "Hypothetical compounding at 5% and mathematical recovery after losses; no observed market data.")

    fig, (ax,) = canvas("未来收到的钱相同，要求收益越高，今天价格越低", "教学假设：一年后确定收到 103 元；忽略违约、费用和税项。")
    rates = np.linspace(0, 10, 201)
    prices = 103 / (1 + rates / 100)
    ax.plot(rates, prices, color=BLUE, linewidth=3)
    for rate, offset in [(3, (-125, 45)), (5, (24, 16))]:
        price = 103 / (1 + rate / 100)
        ax.scatter([rate], [price], s=80, color=GREEN, zorder=3)
        ax.annotate(f"{rate}% → {price:.2f} 元", (rate, price), xytext=offset, textcoords="offset points", fontsize=18)
    ax.set(xlabel="市场要求的年收益率", ylabel="今天的价格（元）", xlim=(0, 10), ylim=(90, 105))
    ax.xaxis.set_major_formatter(PercentFormatter(100))
    fig.text(0.06, 0.055, "价格 = 103 ÷（1 + 收益率）；纵轴从 90 元起，展示价格变化细节。", fontsize=16)
    save(fig, "bond-price-yield", "Price = 103/(1+y) for a fixed one-year payment; hypothetical, not a historical yield curve.")

    fig, (a, b) = canvas("分散的效果，取决于资产是否一起涨跌", "教学假设：期初 A、B 各占 50%，期间不调仓，忽略费用与税项。", 2)
    for ax, vals, title in [(a, [20, -10, 5], "场景一：涨跌不同"), (b, [-20, -20, -20], "场景二：一起下跌")]:
        bars = ax.bar(["资产 A", "资产 B", "组合"], vals, color=[BLUE, GRAY, GREEN], width=0.60)
        ax.axhline(0, color=INK, linewidth=1)
        ax.set(ylim=(-32, 32), title=title, ylabel="期间收益率")
        ax.yaxis.set_major_formatter(PercentFormatter(100))
        ax.bar_label(bars, labels=[f"{v:+d}%" for v in vals], padding=5, fontsize=18)
    fig.text(0.06, 0.055, "组合收益 = 50% × A 收益 + 50% × B 收益；分散不能消除整体市场下跌。", fontsize=16)
    save(fig, "portfolio-scenarios", "Two hypothetical equal-weight portfolio return scenarios: 5% and -20%.")

    fig, (a, b) = canvas("涨价变慢，不等于价格下降", "教学假设：同一篮子商品，第 1 年涨 4%，第 2 年再涨 2%；无实际 CPI 数据。", 2)
    levels = [100, 104, 106.08]
    bars = a.bar(["起点", "第 1 年", "第 2 年"], levels, color=BLUE, width=0.55)
    a.bar_label(bars, labels=["100", "104", "106.08"], padding=6, fontsize=17)
    a.set(ylabel="价格指数（起点 = 100）", ylim=(0, 130), title="价格水平继续上升")
    bars = b.bar(["第 1 年", "第 2 年"], [4, 2], color=GREEN, width=0.5)
    b.bar_label(bars, labels=["4%", "2%"], padding=6, fontsize=18)
    b.set(ylabel="相对上一年的涨幅", ylim=(0, 5.2), title="涨幅有所回落")
    b.yaxis.set_major_formatter(PercentFormatter(100))
    fig.text(0.06, 0.055, "第 2 年价格指数 = 100 × 1.04 × 1.02 = 106.08；仍然高于第 1 年。", fontsize=16)
    save(fig, "inflation-level-rate", "Hypothetical index levels 100,104,106.08 with annual price increases 4%,2%.")

    fig, (ax,) = canvas("同一笔 2 月数据：同比上涨，环比下降", "完全虚构的融资净增量，单位：亿元；沿用本章表格，不是当前经济数据。")
    x = np.arange(2)
    for offset, values, label, color in [(-0.18, [100, 50], "A 年", GRAY), (0.18, [120, 60], "B 年", BLUE)]:
        bars = ax.bar(x + offset, values, width=0.34, label=label, color=color)
        ax.bar_label(bars, padding=5, fontsize=18)
    ax.set_xticks(x, ["1 月", "2 月"])
    ax.set(ylabel="当月净增量（亿元）", ylim=(0, 150))
    ax.legend(frameon=False, loc="upper right")
    fig.text(0.06, 0.09, "B 年 2 月同比：60 ÷ 50 − 1 = +20%（对比 A 年 2 月）", fontsize=17)
    fig.text(0.06, 0.03, "B 年 2 月环比：60 ÷ 120 − 1 = −50%（对比 B 年 1 月）", fontsize=17)
    save(fig, "year-month-comparison", "Fictional financing flow: A Jan 100, A Feb 50, B Jan 120, B Feb 60; YoY +20%, MoM -50%.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview-dir", type=Path)
    parser.add_argument("--font", help="Path to a local Chinese TTF/OTF font")
    args = parser.parse_args()
    configure_font(args.font)
    render(args.preview_dir)

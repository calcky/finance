"""Sphinx configuration shared by local builds and Read the Docs."""

project = "finance"
author = "finance contributors"
language = "zh_CN"
root_doc = "index"

extensions = ["myst_parser"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]
myst_heading_anchors = 3
myst_enable_extensions = ["colon_fence"]
nitpicky = True

html_theme = "sphinx_rtd_theme"
html_title = "finance · 金融知识、数据与指标"
html_theme_options = {"navigation_depth": 3}

html_static_path = ["_static"]


def add_gdp_charts(app, pagename, templatename, context, doctree):
    """Embed the committed snapshot only on the GDP page; no runtime fetch/CDN."""
    if pagename != "data/gdp":
        return
    import csv
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    with (root / "data/gdp.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    meta = json.loads((root / "data/gdp.metadata.json").read_text(encoding="utf-8"))
    series = {}
    for row in rows:
        series.setdefault(row["series_id"], {}).setdefault(row["country"], {})[row["period"]] = (
            float(row["value"]) if row["value"] else None
        )
    payload = {"years": sorted({r["period"] for r in rows}), "series": series,
               "retrieved_at": meta["retrieved_at"], "metadata": meta["series"]}
    body = "window.FINANCE_GDP = " + json.dumps(payload, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c") + ";"
    app.add_css_file("gdp-charts.css")
    app.add_js_file("vendor/echarts-5.6.0.min.js", priority=500, defer="defer")
    app.add_js_file(None, body=body, priority=501)
    app.add_js_file("gdp-charts.js", priority=502, defer="defer")


def setup(app):
    app.connect("html-page-context", add_sync_status)
    app.connect("html-page-context", add_gdp_charts)
    app.connect("html-page-context", add_macro_charts)
    app.add_css_file("macro-overview.css")


def add_sync_status(app, pagename, templatename, context, doctree):
    """Show the saved topic health without browser requests or timestamp churn."""
    from html import escape
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "data/update-status.json"
    if not pagename.startswith("data/") or not path.exists():
        return
    status = json.loads(path.read_text(encoding="utf-8")).get(pagename[5:])
    if status is None:
        return
    failed = status["state"] == "failed"
    label = {"ok": "保存的同步状态：通过", "failed": "同步失败：当前展示上次有效快照",
             "unknown": "逐专题同步状态尚未记录"}[status["state"]]
    target = context["pathto"]("data/update-status")
    context["body"] = (f'<div class="admonition {"warning" if failed else "note"} sync-status">'
                       f'<p>{label}。<a href="{escape(target, quote=True)}">查看更新状态与实际检查时间</a>。</p>'
                       '</div>' + context["body"])


def add_macro_charts(app, pagename, templatename, context, doctree):
    import json
    from pathlib import Path
    import sys

    root = Path(__file__).resolve().parents[1]
    scripts = str(root / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    from macro_catalog import TOPICS
    from macro_render import load_topic, payload

    slug = pagename.removeprefix("data/")
    if pagename != "data/" + slug or slug not in TOPICS:
        return
    rows, meta = load_topic(slug, root)
    body = "window.FINANCE_MACRO = " + json.dumps(payload(slug, rows, meta), ensure_ascii=False, allow_nan=False).replace("<", "\\u003c") + ";"
    app.add_css_file("gdp-charts.css")
    app.add_css_file("macro-charts.css")
    app.add_js_file("vendor/echarts-5.6.0.min.js", priority=500, defer="defer")
    app.add_js_file(None, body=body, priority=501)
    app.add_js_file("macro-charts.js", priority=502, defer="defer")

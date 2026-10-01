"""Sphinx configuration shared by local builds and Read the Docs."""

project = "finance"
author = "finance contributors"
language = "zh_CN"
root_doc = "index"

extensions = ["myst_parser"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]
myst_heading_anchors = 3
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
    app.connect("html-page-context", add_gdp_charts)

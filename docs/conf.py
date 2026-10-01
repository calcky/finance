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

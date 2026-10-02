# 维护与发布

项目使用 Sphinx、MyST Markdown 和 Read the Docs 主题。依赖固定在 `docs/requirements.txt`，本地与托管构建使用同一份依赖和 `docs/conf.py`。

## 目录职责

| 位置 | 用途 |
|---|---|
| `README.md` | GitHub 仓库入口和本地构建方法 |
| `docs/` | 文档首页、学习路线、宏观与跨市场章节、网站配置 |
| `docs/foundations/` | 经济地图、收益与风险、个人财务 |
| `docs/investing/` | 债券、股票、基金与投资组合 |
| `docs/images/` | 原创图解的 Draw.io 图源、SVG，以及公式计算图 |
| `scripts/` | 数值图生成、GDP 数据同步与独立绘图依赖 |
| `scripts/macro_*.py`、`scripts/sync_macro.py` | 七个中国宏观专题的口径、官方采集、校验与生成 |
| `data/macro/` | 七份宏观 CSV 及机器可读元数据 |
| `docs/indicators/` | 指标定义、单位、频率与来源 |
| `docs/data/` | 数据使用说明与更新规范 |
| `data/` | 可公开再分发的小型数据集及说明 |
| `.readthedocs.yaml` | Read the Docs 构建环境和入口 |
| `.github/workflows/update-gdp.yml` | 年度 GDP 与七个宏观专题的统一定时检查、校验和快照提交 |
| `_build/` | 本地生成的网页，已加入 Git 忽略规则 |

## 本地预览

在仓库根目录执行，示例适用于 Linux / WSL：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r docs/requirements.txt
.venv/bin/python -m sphinx -n -W --keep-going -b html docs _build/html
.venv/bin/python -m http.server 8000 --directory _build/html
```

浏览器访问 `http://localhost:8000`。`-W` 将构建警告视为失败；新增页面后要加入 `docs/index.md` 或对应章节的 `toctree`，以便出现在侧栏。

现有正文继续使用普通 Markdown 相对链接。Sphinx 会把文档间的 `.md` 链接转换为站内 HTML 链接，同时保留在 GitHub 阅读时的可用性。网站内的页面不要链接到文档源目录之外的本地文件；需要下载数据时，应明确提供数据发布地址或配置下载资源。

## 首次接入 Read the Docs

1. 登录 [Read the Docs](https://app.readthedocs.org/)，连接 GitHub 账号。
2. 按平台提示为 `calcky/finance` 授权 GitHub 集成，并导入仓库。
3. 使用仓库根目录的 `.readthedocs.yaml`，默认分支选择 `main`。
4. 触发首次构建，检查构建日志、中文导航、站内搜索与文章链接。
5. 构建成功后将平台实际提供的网址补充到仓库 README；不要事先假设 `finance.readthedocs.io` 可用。

仓库配置已准备，但只有完成账号侧的导入和首次构建，才算上线。参考 [Read the Docs 项目导入说明](https://docs.readthedocs.com/platform/stable/intro/add-project.html)和[配置规范](https://docs.readthedocs.com/platform/stable/config-file/v2.html)。

## 后续更新

### 教学内容的组织原则

按“基本概念与个人财务 → 金融产品 → 宏观经济 → 汇率与黄金 → 数据实践”组织主线。新增内容优先接入相应主题，不按财经热词堆放，也不要求读者在入门前掌握高级术语。

每个学习单元先提出具体问题，再解释机制、给出可复算的教学例子，指出误区与适用条件，最后提供自测和参考答案。涉及概率、价格或政策效果时区分可能关系与确定关系；具体制度标明地区与口径。

来源优先使用统计机构、央行、监管机构、交易所及正式产品文件。来源入口只能帮助继续查阅，不能替代每项时效性制度的直接证据。新增当前数值或制度断言时应补充具体发布页和日期。对尚未核实的信息明确保留不确定性。

改变顺序时同步修改首页、学习路线、章节编号和上一章 / 下一章链接。术语表与指标目录服务于回查，不代替循序渐进的解释。

### 图解约定

涉及账目、资金流或多步传导时优先提供图解，每张图回答一个问题。数字与正文一致，图中注明单位与假设；箭头说明支付、结算或因果条件，避免把可能关系画成必然结果。正文保留解释和替代文本，不能只靠颜色传达含义。

可编辑图源与预览并列保存为 `.drawio` 和 `.drawio.svg`。SVG 由 Draw.io 使用 `--embed-diagram --svg-theme light` 导出，使 GitHub 与文档站显示稳定的浅色图，并保留可恢复图源。网站构建直接使用已导出的 SVG，不依赖安装 Draw.io。

图中文字优先使用 Draw.io 普通文本（`html=0;whiteSpace=nowrap`），通过显式换行组织内容，导出为原生 SVG 文本，避免依赖 `foreignObject` 富文本及其可能截断的回退标签。浅色图使用白色画布底板，导出后检查文字与背景，不能仅凭导出命令成功判断兼容性。

修改图源后重新导出 SVG；运行图结构校验并查看 PNG 预览，检查文字、连接和单位。数值曲线使用相应绘图工具生成，注明教学假设或真实数据来源，不把装饰性示意曲线当成历史行情。

### 重建公式计算图

五张教学数值图由 [render_learning_charts.py](https://github.com/calcky/finance/blob/main/scripts/render_learning_charts.py) 根据正文公式生成，不读取网络或真实行情。依赖与文档构建分开维护，Read the Docs 直接使用入库后的 SVG。

```sh
.venv/bin/python -m pip install -r scripts/requirements-plots.txt
.venv/bin/python scripts/render_learning_charts.py --preview-dir /tmp/finance-learning-previews
```

生成图写入 `docs/images/learning/`。本地需要中文字体，脚本会查找常见字体；未找到时可传 `--font /path/to/font.ttf`。SVG 将数值图的字形转成路径以减少阅读端字体依赖，正文的替代文本保留关键结论和数字。重新生成后检查 PNG，核对图与例子的单位、比例和计算结果，再重新构建文档。

### 内容与数据更新

知识更新直接编辑相应 Markdown；数据更新遵循[数据维护规范](data/index.md)，同时记录统计期间、来源与修订说明。

修改后先本地构建，再运行 `git diff --check` 并检查变更。GitHub 集成正常时，推送到 `main` 会触发 Read the Docs 重建；具体构建状态以平台日志为准。

### GDP 同步与离线重建

```sh
# Debian / Ubuntu 安装与 CI 一致的中文字体
sudo apt-get install fonts-droid-fallback
.venv/bin/python -m pip install -r scripts/requirements-plots.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/sync_gdp.py
.venv/bin/python -m sphinx -n -W --keep-going -b html docs _build/html
git diff --check
```

`sync_gdp.py` 每次读取完整年度历史及指标定义，检查数据集、国家、指标、年份、分页完整性、重复键、数值范围与历史覆盖。缺失值保持为空；实际增速使用官方独立序列。全部抓取、校验、渲染成功后才替换本地文件。GitHub 工作流在严格文档构建也通过后才提交，失败时不推送新数据。

运行 `scripts/sync_gdp.py --render-only` 可从已有 CSV 和元数据离线重建页面与四张图，不访问网络。`docs/data/gdp.md` 是自动生成文件，改解读文案时编辑脚本中的页面模板，再离线重建。CSV 原始单位与显示单位分开；生成图使用固定中文字体和浅色背景。

工作流每天 UTC 22:17（次日北京时间 06:17）检查；支持 `workflow_dispatch` 手动运行，同步代码变更推送到 `main` 时也会触发。它使用 GitHub 自带 `GITHUB_TOKEN`，不需世界银行 API key，仅同步 job 获得 `contents: write`。分支保护或组织权限若阻止 bot 提交，任务会失败，不能把工作流文件存在等同于同步成功。

只有观测或来源元数据变化才刷新快照并提交。GitHub 定时任务可能延迟；公开仓库 60 天没有活动可能自动暂停定时任务，需在 Actions 中重新启用。通过 [Actions 运行记录](https://github.com/calcky/finance/actions/workflows/update-gdp.yml) 判断最近一次检查是否成功，页面显示的快照时间不代表最后检查时间。参考 [GitHub schedule 文档](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)。

GDP 部分的自动提交范围限定为 `data/gdp.csv`、`data/gdp.metadata.json`、`docs/data/gdp.md` 和四张 GDP SVG；不改课程正文。推送失败不会强制覆盖远端，下次从最新分支重跑。Read the Docs 是否收到更新、构建是否成功，仍须以其项目状态为准。

### 七个中国宏观专题

统一工作流也会更新季度 GDP、物价、货币与社融、利率、经济活动、就业与收入、贸易与汇率，避免两个定时任务同时写同一分支。宏观数据提交范围另含 `data/macro/`、七个生成页面和 `docs/images/data/macro-*.svg`。每日 UTC 22:17 检查，全部采集、校验、严格构建与浏览器测试成功后才发布；任一来源失败均不提交本次刷新。

```sh
.venv/bin/python -m pip install -r scripts/requirements-data.txt -r scripts/requirements-plots.txt
.venv/bin/python scripts/sync_macro.py
# 完整回溯并复核历史（央行公告可能需要一至两小时）
.venv/bin/python scripts/sync_macro.py --backfill
# 只用已入库快照离线重建，不联网
.venv/bin/python scripts/sync_macro.py --render-only --preview-dir /tmp/finance-macro-previews
.venv/bin/python scripts/macro_overview.py
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m sphinx -n -W --keep-going -b html docs _build/html
# 启动前述本地 HTTP 服务后
node tests/browser/macro.cjs
node tests/browser/overview.cjs
```

`macro_catalog.py` 保存指标、口径和阅读解释。`macro_nbs_history.py`、`macro_nbs_cpi_releases.py`、`macro_income_history.py` 负责统计局历史目录与原始公告，`macro_quarterly_gdp.py` 每次复核季度 GDP 完整历史和定义，`macro_money_history.py` 负责央行年度统计表及回溯，`macro_market_history.py` 负责汇率、LPR 与国债曲线，`macro_repo_history.py` 负责逆回购公告。原 `macro_nbs.py`、`macro_pbc.py` 中部分解析器仍被复用。`macro_render.py` 使用同一快照生成 23 张 SVG、完整明细和交互载荷；Sphinx 构建只需文档依赖，不需要采集或绘图库。

首次接入单一专题可运行 `.venv/bin/python scripts/sync_macro.py --topics quarterly-gdp --backfill`；日常单专题复核去掉 `--backfill`。不指定 `--topics` 时仍更新全部专题。选定专题的全部采集和渲染成功后才写入，不触碰其他专题快照；季度 GDP 每次读取全部季度历史，并核验同比指数减 100、现价/不变价、当季/累计和季调口径。新增专题的广范围查询应再用分段查询交叉验证完整性。

采集使用普通 HTTPS、Cookie 和请求间隔，不模拟登录或绕过访问限制。开发排查可用 `--cache-dir /tmp/finance-macro-cache` 复用响应；定时任务不使用该缓存，避免错过修订。首次接入尽量完成可用历史，不自行设定近年起点；实际覆盖和限制见[历史来源核验](data/history-coverage.md)。公共搜索按日期分段、分页；日度市场数据按月或年查询；央行公告遍历档案并核对总数，未完成或有解析失败的抓取不可发布。

日常查询保留既有早期观测，元数据 `refresh_ranges` 标明本次权威查询范围，`history` 保留全量回溯证据，`history_checked_at` 记录完整回溯时间，`coverage` 记录每个指标的实际首末期间和条数。每月 1 日的定时任务做全量复核，Actions 手动输入 `backfill` 也可开启；首次建立或快照更新与历史复核均超过 60 天时自动全量回溯。仅查询窗口或检查日期变化不会改写没有新数据的日常快照；一次真正完成的全历史核验会更新复核时间。

M1 同比采用统计局转发的央行可比同比，并纳入央行官方 2024 年新定义回溯；不以跨定义余额计算替代。价格指数以 100 为比较基准时减 100 得涨跌幅，PMI 保留指数点。贸易千美元除以 100000 得亿美元，货币亿元除以 10000 得万亿元。社融当月增量不由存量差分代替；收入明确为季度末年内累计。工业与社零的 1—2 月合计使用独立序列和明细表，历史真实单月值仍保留。

所有获取和渲染先在临时目录完成；错误不替换现有快照。完整历史来源缺失已有观测、滚动窗口内已有值消失、单位或结构改变均报错。正常数值修订可更新并由 Git 记录；新窗口之外的日度历史保留，不声称已重新核验它们。观测和元数据没有变化时不刷新获取时间。源机构未给出逐条发布时间的字段留空。

新图延续 GDP 的静态回退，同时支持精确期间选择、固定读数、按月/季度/日历天缩放及自动展开定位表格。每张图使用自己的频率，不将季度值前向填充为月度数据。日历缺口断线，不假设所有工作日都有报价。每页的“本站同版快照”下载对应当前构建，GitHub 原始文件链接则对应主分支最新版本。

### 宏观经济总览

`scripts/macro_overview.py` 从七个宏观专题读取快照，生成 `docs/data/overview.md`。增长卡片使用季度 GDP 当季实际同比，年度 GDP 通过背景链接保留。运行 `.venv/bin/python scripts/macro_overview.py` 即可重新生成，不访问网络、不改写 CSV。同步工作流在年度 GDP 和宏观数据更新成功后生成总览，再通过测试和构建后统一发布。

总览按六个维度展示 12 个指标，各自保留统计期、前次有效观测、来源发布日期、快照获取时间及完整历史入口。差值以原始精度计算，百分比之差使用百分点。位置条使用每个指标最新有效观测所属年及此前四年的有效数据，不混合新旧定义，不填缺口；常值或单点不绘制虚假的相对位置。各卡片窗口可能不同，条长不用于跨指标排名。

总览使用 MyST 卡片、CSS 位置条和原生可展开阅读示例；禁用 JavaScript 时仍可阅读和点击专题链接。传导图复用已有可编辑 Draw.io 图。修改生成器、样式或卡片说明后运行 `tests/test_overview.py`、严格 Sphinx 构建和 `node tests/browser/overview.cjs`；测试会检查生成页面与快照一致，避免数据更新后总览遗留旧值。

### GDP 交互图

文档站的四张 GDP 图使用本地保存的 Apache ECharts 5.6.0，提供悬停读数、点击固定年份、年份下拉框、时间范围滑块和近 10 / 20 年快捷按钮。选中年份后可跳到高亮的历年表格行；下拉框支持键盘，手机可直接点选。图下读数固定保留，移动鼠标只改变悬停提示。

`docs/conf.py` 仅为 GDP 页面嵌入 `data/gdp.csv` 和元数据的快照，并加载 `docs/_static/gdp-charts.js`、样式和本地图表库。浏览器不调用世界银行 API、不依赖 CDN；Read the Docs 不需安装 Node.js。数据更新后重新构建，交互图、静态图和表格使用同一批数值，空值保持缺失而不是零。

Markdown 中的 SVG 继续供 GitHub 阅读与打印使用。只有交互图初始化成功才隐藏静态图；禁用 JavaScript、图表库加载失败时仍可看静态图和明细表。第三方库的许可、NOTICE 和版本来源保存在 `docs/_static/vendor/`。

浏览器回归测试使用 Node.js 20 或更高版本，在文档构建后执行：

```sh
npm ci --prefix tests/browser
# 安装浏览器；Linux 如需系统依赖可增加 --with-deps
cd tests/browser
npx playwright install chromium
cd ../..
# 一个终端启动本地文档服务
.venv/bin/python -m http.server 8767 --bind 127.0.0.1 --directory _build/html
# 另一个终端在仓库根目录运行
node tests/browser/gdp.cjs
```

测试覆盖四张图、真实鼠标悬停与点击、固定读数、精确年份、缩放、键盘、缺失值、负增长、表格定位、手机触摸、打印和静态回退。同步工作流复用 GitHub Ubuntu runner 自带的 Chrome，在这组测试通过后才提交数据更新。可用 `GDP_TEST_URL` 指定另一个本地测试页面，或用 `GDP_BROWSER_CHANNEL=chrome` 测试已安装的 Chrome。推送同步代码的新版本会取消仍在运行的旧版任务；定时与手动任务顺序运行。

# 维护与发布

项目使用 Sphinx、MyST Markdown 和 Read the Docs 主题。依赖固定在 `docs/requirements.txt`，本地与托管构建使用同一份依赖和 `docs/conf.py`。

## 目录职责

| 位置 | 用途 |
|---|---|
| `README.md` | GitHub 仓库入口和本地构建方法 |
| `docs/` | 文档首页、学习路线、宏观与跨市场章节、网站配置 |
| `docs/foundations/` | 经济地图、收益与风险、个人财务 |
| `docs/investing/` | 债券、股票、基金与投资组合 |
| `docs/images/` | 原创图解的 Draw.io 图源与 SVG 预览 |
| `docs/indicators/` | 指标定义、单位、频率与来源 |
| `docs/data/` | 数据使用说明与更新规范 |
| `data/` | 可公开再分发的小型数据集及说明 |
| `.readthedocs.yaml` | Read the Docs 构建环境和入口 |
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

### 内容与数据更新

知识更新直接编辑相应 Markdown；数据更新遵循[数据维护规范](data/index.md)，同时记录统计期间、来源与修订说明。

修改后先本地构建，再运行 `git diff --check` 并检查变更。GitHub 集成正常时，推送到 `main` 会触发 Read the Docs 重建；具体构建状态以平台日志为准。

目前没有自动采集任务或更新时效承诺。后续选定数据源、授权方式和更新频率后，再增加相应采集脚本及调度，数据校验失败时不发布为新读数。

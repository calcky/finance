# 维护与发布

项目使用 Sphinx、MyST Markdown 和 Read the Docs 主题。依赖固定在 `docs/requirements.txt`，本地与托管构建使用同一份依赖和 `docs/conf.py`。

## 目录职责

| 位置 | 用途 |
|---|---|
| `README.md` | GitHub 仓库入口和本地构建方法 |
| `docs/` | 基础知识、文档首页和网站配置 |
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

知识更新直接编辑相应 Markdown；数据更新遵循[数据维护规范](data/index.md)，同时记录统计期间、来源与修订说明。

修改后先本地构建，再运行 `git diff --check` 并检查变更。GitHub 集成正常时，推送到 `main` 会触发 Read the Docs 重建；具体构建状态以平台日志为准。

目前没有自动采集任务或更新时效承诺。后续选定数据源、授权方式和更新频率后，再增加相应采集脚本及调度，数据校验失败时不发布为新读数。

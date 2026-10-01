# finance

面向零基础读者的金融学习与数据资料库。从个人财务和金融产品出发，逐步理解宏观经济、汇率与黄金，再练习用可追溯的数据检验解释。

## 内容定位

- **知识**：从收入、财富、收益与风险，循序渐进学习债券、股票、基金、宏观经济与跨市场关系。
- **指标**：定义、单位、频率、发布机构、解读方法与可比性限制。
- **数据**：记录来源、统计期间、发布时间和获取时间，保留修订说明。

目前提供 15 个学习单元，以及[术语速查](docs/glossary.md)、[指标目录](docs/indicators/index.md)和[数据维护规范](docs/data/index.md)。每章包含具体例子、自测和参考答案；[银行与货币创造](docs/banking-and-money-creation.md)配有五张可编辑图解。尚未接入真实数据集或自动采集任务；正文中的数字例子均为教学假设。

可从[文档首页](docs/index.md)开始阅读。网站使用 **Sphinx + MyST + Read the Docs 主题**构建，Markdown 同时支持 GitHub 阅读。

## 阅读路线

| 顺序 | 主题 | 要回答的问题 |
|---|---|---|
| 1 | [基本概念与个人财务](docs/foundations/economic-map.md) | 收入不等于财富；收益、购买力与风险怎样衡量？ |
| 2 | [金融产品与投资](docs/investing/bonds.md) | 存款、债券、股票、基金分别是什么，如何看组合风险？ |
| 3 | [宏观经济与政策](docs/banking-and-money-creation.md) | 贷款怎样创造存款，M1、M2、社融、GDP 与政策怎样联系？ |
| 4 | [汇率与黄金](docs/exchange-rates.md) | 美元、人民币和黄金怎样影响计价与收益？ |
| 5 | [数据阅读实践](docs/reading-macro-data.md) | 如何核对口径、计算变化，区分事实与推测？ |

完整顺序和每阶段目标见[学习路线](docs/learning-guide.md)。文档用于理解机制、提出问题和检验证据，不以推荐个别产品或预测短期行情为目标。

## 先记住四组区别

- **存量与流量**：M2 是某个时点的余额；GDP 是某段时期的产出。社融既有存量，也有增量。
- **水平与增速**：通胀率下降通常表示涨价变慢，不代表物价已下降。
- **名义与实际**：名义金额按当期价格计算；实际增长剔除价格影响。
- **结果与预期**：资产价格会提前反映预期。同样是降息，超预期与低于预期可能引起不同反应。

理解时可以沿着这条线追问：

```text
增长与通胀情况
  → 政策选择和市场预期
  → 融资成本、信用需求与资金配置
  → 消费、投资、汇率与资产价格
  → 反过来影响增长和通胀
```

箭头表示可能的传导关系，效果取决于条件、时滞和其他变量，不是固定的涨跌公式。

## 范围与资料

货币与社融以中国统计口径为主；利率、美元指数和黄金补充美国及国际市场背景。文中数字例子均为教学假设，不代表当前行情或收益承诺。

资料整理日期：2026-10-01。每篇列出官方或专业机构资料入口；查询历史数据时，应使用发布机构说明的可比口径。涉及制度调整的内容需定期复核。

## 本地构建

需要 Python 3.12。在仓库根目录执行：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r docs/requirements.txt
.venv/bin/python -m sphinx -n -W --keep-going -b html docs _build/html
```

打开 `_build/html/index.html`，或运行 `.venv/bin/python -m http.server 8000 --directory _build/html` 后访问 `http://localhost:8000`。

## Read the Docs 发布

仓库提供 `.readthedocs.yaml`。在 [Read the Docs](https://app.readthedocs.org/) 中连接 GitHub 并导入 `calcky/finance`，选择 `main` 分支构建。项目名称和最终网址以平台实际分配为准；仓库配置本身不会创建托管项目。

接通 GitHub 集成后，推送会触发文档重建。数据采集与文档构建是两个独立步骤，Read the Docs 不负责定时采集金融数据。

具体流程见[维护与发布](docs/maintenance.md)。

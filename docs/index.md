# finance：金融知识、数据与指标

从零开始理解钱、金融产品和经济运行，再学习如何阅读指标、核对数据和判断财经信息。无需经济学背景，先用生活中的例子建立概念，再逐步引入术语和计算。

内容以中国宏观经济与人民币市场为主，并补充美元、国际利率与黄金。资料会持续维护；各指标按其发布频率更新，不把所有数据统一视为“每日行情”。

## 从这里开始

推荐先读[学习路线](learning-guide.md)，然后从[第 1 章：经济与金融](foundations/economic-map.md)开始。共 15 个学习单元，每章包含图示、例子、自测与参考答案。教学部分 19 张图分别说明资金关系、产品原理和数值变化；[银行与货币创造](banking-and-money-creation.md)用其中五张图解释一笔贷款的生命周期。

| 阶段 | 学习内容 | 要回答的问题 |
|---|---|---|
| 1. 建立基础 | [经济与金融](foundations/economic-map.md)、[收益与风险](foundations/money-time-risk.md)、[个人财务](foundations/household-finance.md) | 钱从哪里来，财富如何衡量，风险如何影响生活？ |
| 2. 认识产品 | [存款与债券](investing/bonds.md)、[股票](investing/stocks.md)、[基金](investing/funds.md)、[投资组合](investing/portfolio.md) | 买到什么权利，收益从哪里来，可能怎样亏损？ |
| 3. 看懂宏观 | [银行与货币创造](banking-and-money-creation.md)、[货币与信用](money-and-credit.md)、[增长与通胀](growth-and-inflation.md)、[利率](interest-rates.md) | 银行怎样创造存款，M2、GDP 和降息分别描述什么？ |
| 4. 连接市场 | [汇率](exchange-rates.md)、[黄金](gold.md) | 美元、人民币和黄金有什么联系，又为何经常不同步？ |
| 5. 读懂数据 | [综合阅读](reading-macro-data.md)、[数据练习](data/reading-exercise.md) | 哪些是事实，哪些只是解释，还有什么证据缺失？ |

## 随时可查的资料

- [术语速查](glossary.md)：不必先背缩写，遇到再查。
- [指标目录](indicators/index.md)：定义、单位、频率和数据来源。
- [宏观经济总览](data/overview.md)：六个观察维度、最新数据与历史范围，结合传导图理解指标之间的联系。
- [GDP 数据专题](data/gdp.md)：中国历年 GDP、实际增速、人均 GDP 与中美对照，提供四张趋势图和 CSV 下载。
- [中国宏观数据](data/index.md)：物价、货币与社融、利率、经济活动、就业与收入、进出口与汇率；19 张交互图支持选点、缩放与逐期查表。
- [数据与更新](data/index.md)：每日检查来源新值与历史修订，区分统计期间、来源库更新和快照获取时间。
- [维护与发布](maintenance.md)：贡献内容、本地构建和 Read the Docs 发布方法。

## 阅读时先分清

- **存量和流量**：M2 是时点余额，GDP 是期间产出，社融则既有存量又有增量。
- **名义和实际**：金额增加可能包含价格上涨，不能直接视为产出增加。
- **统计期间和发布时间**：本月发布的数据可能描述上个月或上个季度。
- **事实和示例**：基础文档中的数字是教学假设，真实数据需要明确来源和日期。
- **结果和预期**：市场价格同时反映预期，单个指标不能直接决定资产涨跌。

```{toctree}
:hidden:
:caption: 开始学习
:maxdepth: 1

learning-guide
```

```{toctree}
:hidden:
:caption: 一、基本概念与个人财务
:maxdepth: 1

foundations/economic-map
foundations/money-time-risk
foundations/household-finance
```

```{toctree}
:hidden:
:caption: 二、金融产品与投资
:maxdepth: 1

investing/bonds
investing/stocks
investing/funds
investing/portfolio
```

```{toctree}
:hidden:
:caption: 三、宏观经济与政策
:maxdepth: 1

banking-and-money-creation
money-and-credit
growth-and-inflation
interest-rates
```

```{toctree}
:hidden:
:caption: 四、汇率与黄金
:maxdepth: 1

exchange-rates
gold
```

```{toctree}
:hidden:
:caption: 五、数据阅读实践
:maxdepth: 1

reading-macro-data
data/reading-exercise
```

```{toctree}
:hidden:
:caption: 六、宏观数据专题
:maxdepth: 2

data/index
```

```{toctree}
:hidden:
:caption: 参考资料
:maxdepth: 2

glossary
indicators/index
```

```{toctree}
:hidden:
:caption: 项目维护
:maxdepth: 1

maintenance
```

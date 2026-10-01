# finance：金融知识、数据与指标

这里整理金融基础原理、常用指标和可追溯的数据，帮助理解财经新闻中的数字，以及这些数字成立的条件。

内容以中国宏观经济与人民币市场为主，并补充美元、国际利率与黄金。资料会持续维护；各指标按其发布频率更新，不把所有数据统一视为“每日行情”。

## 从哪里开始

| 入口 | 内容 | 当前状态 |
|---|---|---|
| [基础知识](money-and-credit.md) | 货币与信用 → 增长与通胀 → 利率 → 汇率 → 黄金 → 综合阅读 | 六篇入门文档 |
| [指标目录](indicators/index.md) | 指标定义、单位、频率与官方来源 | 已整理元信息，未采集数值 |
| [数据与更新](data/index.md) | 数据记录、来源与修订规则 | 维护规范，尚无真实数据集 |
| [维护与发布](maintenance.md) | 本地预览、文档发布与后续更新 | Sphinx / Read the Docs 配置 |

## 阅读时先分清

- **存量和流量**：M2 是时点余额，GDP 是期间产出，社融则既有存量又有增量。
- **名义和实际**：金额增加可能包含价格上涨，不能直接视为产出增加。
- **统计期间和发布时间**：本月发布的数据可能描述上个月或上个季度。
- **事实和示例**：基础文档中的数字是教学假设，真实数据需要明确来源和日期。
- **结果和预期**：市场价格同时反映预期，单个指标不能直接决定资产涨跌。

```{toctree}
:hidden:
:caption: 金融基础
:maxdepth: 1

money-and-credit
growth-and-inflation
interest-rates
exchange-rates
gold
reading-macro-data
```

```{toctree}
:hidden:
:caption: 指标与数据
:maxdepth: 2

indicators/index
data/index
```

```{toctree}
:hidden:
:caption: 项目维护
:maxdepth: 1

maintenance
```

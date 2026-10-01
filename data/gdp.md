# GDP 年度历史数据

数据文件：`gdp.csv`；来源定义、提供方、接口地址和来源库更新时间：`gdp.metadata.json`。可读专题见 [GDP 数据专题](../docs/data/gdp.md)。

来源：The World Bank: World Development Indicators（WDI，source 2），以及指标元数据列出的数据提供方。[使用条款](https://data.worldbank.org/summary-terms-of-use)默认采用 CC BY 4.0，需遵循附加条件和第三方例外。中文解释与图形是本项目制作，不代表来源机构认可。

| series_id | 国家 | WDI 指标 | 原始单位 |
|---|---|---|---|
| gdp_cny | CHN | NY.GDP.MKTP.CN | 人民币元，现价 |
| gdp_growth | CHN | NY.GDP.MKTP.KD.ZG | 实际年度增速，百分数 |
| gdp_usd | CHN、USA | NY.GDP.MKTP.CD | 美元，现价，非 PPP |
| gdp_per_capita_usd | CHN | NY.GDP.PCAP.CD | 美元 / 人，现价 |

每行唯一键为 `series_id + country + period`。`period` 为年度 `YYYY`；金额保留原始单位，网页才换算为万亿元或万亿美元。`value` 缺失留空，不插值，不用 0 代替。`note` 保存接口的观测状态代码（如有）。

接口未提供逐条发布时间，`published_at` 留空；`retrieved_at` 是该快照的 UTC 获取时间。元数据中的 `source_updated` 是整个来源库的更新日期，不等于该指标某条观测的发布日期。来源可能包含估算，不能把所有观测视为最终核定数据。

同步每次检查完整历史，允许非空数值修订；历史行消失、已知值变空、单位变化或结构校验失败则报错并保留上次快照。合法修订记录在 Git diff 中。来源元数据发生变化也会更新快照；检查时间变化本身不产生提交。缺失值后来补齐也视为修订。

初次接入后的每个版本可由 [Git 历史](https://github.com/calcky/finance/commits/main/data/gdp.csv) 追溯；没有本项目采集前的历史初值。不要用当前修订后的历史序列假装进行“当时已知信息”的投资回测。

手动同步：`.venv/bin/python scripts/sync_gdp.py`。离线重绘：`.venv/bin/python scripts/sync_gdp.py --render-only`。详细流程见 [维护与发布](../docs/maintenance.md)。

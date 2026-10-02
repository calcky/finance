"""US policy and Treasury rates: distinguish targets, traded rates and tenors."""


def register(define, chart, topics):
    def rate(key, label, basis, frequency="D", source="美联储 H.15，经 FRED 分发", unit="%"):
        define(key, label, unit, frequency, source, basis, country="USA")
    rate("us_effr", "有效联邦基金利率 EFFR", "市场隔夜无担保利率，不是FOMC目标；2016-03-01起改用FR2420交易报告与成交量加权中位数，此前为经纪商数据加权均值。保留H.15原始日历日观测，不自行填充周末。")
    rate("us_target", "联邦基金单点目标（旧）", "1982-09-27至2008-12-15的历史目标系列；1982—1993年为Thornton研究重建，1994年起来自FOMC材料，并非全段都是当时公开声明。与成交利率及随后区间分开。", source="圣路易斯联储，FRED")
    for key, label in [("lower", "下限"), ("upper", "上限")]:
        rate("us_target_"+key, "联邦基金目标区间"+label, "FOMC目标区间自2008-12-16起；不是每笔贷款适用的上下限。沿用来源每日政策状态值，不自行向未来延伸。", source="美联储理事会，经 FRED 分发")
    for years in (2, 10):
        basis = f"{years}年期名义国债固定期限收益率（CMT），由曲线估计的平价收益率；不是某只单券的票息、成交价或实际持有回报。未季调。"
        rate(f"us_treasury_{years}y", f"美国 {years} 年期国债收益率", basis+"日度缺失不填零、不跨假期补值。")
        rate(f"us_treasury_{years}y_monthly", f"美国 {years} 年期国债收益率（月均）", basis+"官方月均，独立于日度；10年期月度历史早于现有日度。", "M")
    rate("us_real_10y", "美国 10 年期 TIPS 实际收益率", "通胀保值国债固定期限实际收益率；不是名义利率减当前CPI，不保证投资者任意持有期间的实际回报。缺失日不填充。")
    rate("us_term_spread", "10 年减 2 年期限利差", "本项目按同日DGS10−DGS2计算，单位百分点；只有两项均观测到时计算。负值表示这两个期限倒挂，不代表整个曲线或确定的衰退预测。", source="美联储 H.15；本项目计算", unit="百分点")
    rate("us_breakeven_10y", "10 年盈亏平衡通胀差值", "本项目按同日DGS10−DFII10计算，单位百分点；差值含通胀预期、通胀风险溢价和相对流动性等，不是纯通胀预测。", source="美联储 H.15；本项目计算", unit="百分点")
    topics["us-rates"] = {
        "title": "美联储与美国利率", "question": "政策目标、实际成交、长短期国债和实际收益率分别告诉我们什么？",
        "intro": "美国数据独立标识为USA。保留目标制度转换、EFFR统计方法变化，以及月度和日度历史的不同起点；不拿月均值填补早期日值。所有收益率为年率报价，利差单位为百分点。数据原始来源为美联储理事会H.15及圣路易斯联储，经FRED分发；所选系列标注Public Domain: Citation requested，本项目不代表来源机构背书。",
        "charts": [
            chart("us-policy-rates", "联邦基金：实际利率与政策目标", ["us_effr", "us_target", "us_target_lower", "us_target_upper"], "EFFR自1954年起，旧单点目标自1982年起，2008年12月16日改为上下限区间。目标系列缺失的早年不代表没有货币政策；EFFR方法在2016年变化。"),
            chart("us-treasury-monthly", "美国国债：完整月度长历史", ["us_treasury_2y_monthly", "us_treasury_10y_monthly"], "10年期月均自1953年4月，比日度历史更早。两条线都是官方月均；早年缺少2年期观测时不填值，也不据此计算完整期限利差。"),
            chart("us-treasury-daily", "美国国债：2 年与 10 年日度收益率", ["us_treasury_2y", "us_treasury_10y"], "同一日比较不同期限，不能把这张随时间变化的图误当成横轴为期限的收益率曲线。周末和假期缺口按来源保留。"),
            chart("us-term-spread", "10 年减 2 年：期限利差与倒挂", ["us_term_spread"], "0为两期限相等；低于0表示10年收益率低于2年。倒挂可能反映未来短端下降预期与期限溢价变化，不能给衰退发生日期下定论。原始相减与T10Y2Y在1990-11-21、1991-01-29、1995-11-29存在来源差异，本页保留原始计算值，详见历史核验说明。", 0),
            chart("us-real-nominal", "10 年期：名义与 TIPS 实际收益率", ["us_treasury_10y", "us_real_10y"], "TIPS实际收益率从2003年起。名义收益率相同也可能对应不同实际利率；早年没有TIPS序列的部分保留缺口，不用CPI倒推。", 0),
            chart("us-breakeven", "10 年盈亏平衡通胀：同日收益率差", ["us_breakeven_10y"], "同日名义10年减实际10年，两个输入缺一则不计算。它包含风险与流动性溢价，不是美联储的通胀目标，也不是无偏预测。", 0),
        ], "reading": "fed-and-us-rates",
    }
    for spec in topics["us-rates"]["charts"]:
        spec["compact_history"] = True

"""Definitions and reading guidance for the China macro data topics."""

SERIES = {}


def define(key, label, unit, frequency, source, basis):
    SERIES[key] = dict(label=label, unit=unit, frequency=frequency, source=source, basis=basis)


for key, label in [("cpi_yoy", "CPI 同比"), ("core_cpi_yoy", "核心 CPI 同比"),
                   ("cpi_mom", "CPI 环比"), ("ppi_yoy", "PPI 同比"),
                   ("food_cpi_yoy", "食品价格同比"), ("nonfood_cpi_yoy", "非食品价格同比"),
                   ("services_cpi_yoy", "服务价格同比")]:
    define(key, label, "%", "M", "国家统计局", "官方各期同比/环比涨跌幅；保留各期权重和分类，不把换基误作只有当年数据，也不连乘同比构造价格指数。")
for key, label in [("m1", "M1 余额"), ("m2", "M2 余额"), ("tsf_stock", "社融存量")]:
    define(key, label, "万亿元", "M", "中国人民银行", "期末存量，不能与当月流量相加；历史范围变化见下方说明。")
SERIES["m1"]["basis"] = "2025 年起新定义，含官方回溯的 2024 年可比余额；旧定义另列，不跨定义拼接。"
SERIES["m1"]["label"] = "M1 余额（新定义）"
SERIES["m2"]["basis"] = "月末货币存量；保留历次官方统计范围，2011、2018、2022 年调整见历史口径说明。"
SERIES["tsf_stock"]["basis"] = "社融期末余额；2014 年仅年末、2015 年仅季度末，2016 年起月度，不复制成不存在的月份。"
for key, label in [("m1_yoy", "M1 同比"), ("m2_yoy", "M2 同比"), ("tsf_stock_yoy", "社融存量同比")]:
    define(key, label, "%", "M", "中国人民银行", "采用官方可比口径同比，不用旧口径余额重新计算 M1 增速。")
define("tsf_flow", "社融当月增量", "亿元", "M", "中国人民银行", "单月融资流量，不是年内累计，也不是存量的机械差分。")
for key in ("m1_yoy", "m2_yoy"):
    SERIES[key]["source"] = "国家统计局（央行数据）"
SERIES["m1_yoy"]["label"] = "M1 同比（新定义）"
SERIES["m1_yoy"]["source"] = "中国人民银行、国家统计局"
for key, label in [("lpr_1y", "1 年期 LPR"), ("lpr_5y", "5 年期以上 LPR")]:
    define(key, label, "%", "M", "中国货币网", "月度观察值，保留来源中的月内观察日；不把观察日冒充 LPR 实际报价发布日期。")
define("repo_7d", "7 天逆回购操作利率", "%", "D", "中国人民银行", "公开市场公告中的实际操作利率；无操作不等于零利率，不向空白日期前向填充。")
for key, label in [("yield_1y", "1 年期国债收益率"), ("yield_10y", "10 年期国债收益率")]:
    define(key, label, "%", "D", "中央国债登记结算有限责任公司", "中债国债到期收益率曲线对应期限；非票面利率、非某只债券成交价。")
for key, label in [("pmi_manufacturing", "制造业 PMI"), ("pmi_nonmanufacturing", "非制造业商务活动指数")]:
    define(key, label, "指数点", "M", "国家统计局", "扩散指数，50 为临界点，不是经济增速百分比。")
define("industry_yoy", "工业增加值实际同比", "%", "M", "国家统计局", "规模以上工业增加值，剔除价格影响；1—2 月合并发布不拆成单月。")
define("retail_yoy", "社零名义同比", "%", "M", "国家统计局", "社会消费品零售总额，名义增速；1—2 月合并发布不拆成单月。")
define("investment_ytd_yoy", "固定资产投资累计同比", "%", "M", "国家统计局", "不含农户，年初至当月累计名义同比；不是当月增速。")
define("unemployment", "城镇调查失业率", "%", "M", "国家统计局", "全国城镇调查口径，不等于登记失业率或青年失业率。")
define("income_nominal_ytd_yoy", "可支配收入名义累计同比", "%", "Q", "国家统计局", "全国居民人均可支配收入，年内累计同比；Q2 指上半年而非单独第二季度。")
define("income_real_ytd_yoy", "可支配收入实际累计同比", "%", "Q", "国家统计局", "年内累计实际同比，扣除价格因素。")
define("income_ytd", "人均可支配收入累计金额", "元/人", "Q", "国家统计局", "年初至季度末累计，不把年末到次年一季度的重置解释为收入暴跌。")
for key, label in [("exports", "当月出口"), ("imports", "当月进口")]:
    define(key, label, "亿美元", "M", "国家统计局（海关统计）", "货物贸易，当月美元金额；不与累计、人民币金额或服务贸易混用。")
define("trade_balance", "当月货物贸易差额", "亿美元", "M", "国家统计局（海关统计）", "同月同币种出口减进口；正值为顺差，不等于企业利润。")
define("usdcny_mid", "美元兑人民币中间价", "人民币/美元", "D", "中国货币网", "人民币汇率中间价，不是即期成交价、银行结售汇价或离岸 CNH。")
define("m1_old", "M1 余额（旧定义）", "万亿元", "M", "中国人民银行", "2025 年以前旧定义，单独保留；不能与增加个人活期存款等项目后的 M1 直接拼接。")
define("m1_old_yoy", "M1 同比（旧定义）", "%", "M", "国家统计局（央行数据）", "旧定义官方同比；与 2025 年起按新定义计算的可比同比分别展示。")
define("lpr_1y_pre2019", "1 年期 LPR（改革前）", "%", "M", "中国货币网", "2013 年至 2019 年 8 月改革前的月度观察值，与改革后报价机制区分。")
define("investment_legacy_ytd_yoy", "投资累计同比（2011 年前旧口径）", "%", "M", "国家统计局", "2011 年前旧统计范围与项目起报点；不与现行不含农户、500 万元及以上项目口径直接连接。")
define("industry_janfeb_yoy", "工业 1—2 月合计实际同比", "%", "M", "国家统计局", "期间编码 YYYY-02 表示 1—2 月合计，不是 2 月单月。")
define("retail_janfeb_yoy", "社零 1—2 月合计名义同比", "%", "M", "国家统计局", "期间编码 YYYY-02 表示 1—2 月合计，不是 2 月单月。")
define("food_cpi_legacy_yoy", "食品价格同比（2001 年前旧分类）", "%", "M", "国家统计局", "2001 年前食品分类包含烟酒，与此后的食品分类区分保留。")


for prefix, label in [("gdp", "GDP"), ("gdp_primary", "第一产业增加值"),
                      ("gdp_secondary", "第二产业增加值"), ("gdp_tertiary", "第三产业增加值")]:
    define(prefix + "_q_nominal", label + "当季现价金额", "亿元", "Q", "国家统计局",
           "独立单季、现价增加值，未季调；包含价格与季节性影响，不用金额变化推算实际增长。")
    define(prefix + "_q_yoy", label + "当季实际同比", "%", "Q", "国家统计局",
           "按不变价计算，与上年同季相比；官方上年同期=100指数减100，不是产业增长贡献率。")
define("gdp_ytd_nominal", "GDP 年内累计现价金额", "亿元", "Q", "国家统计局",
       "年初至季度末的现价增加值；Q2为上半年，Q4为全年；不用累计同比作差得到单季增速。")
define("gdp_ytd_yoy", "GDP 年内累计实际同比", "%", "Q", "国家统计局",
       "按不变价计算，比较本年与上年相同累计期间；不是各季度同比的简单平均。")
define("gdp_qoq_sa", "GDP 季调实际环比", "%", "Q", "国家统计局",
       "季节调整后相对上一季度的实际增速，非年化；直接采用官方百分比，历史会随季调模型更新修订。")


for key, label in [("rmb", "人民币贷款（社融口径）"), ("fx", "外币贷款折人民币"),
                   ("entrusted", "委托贷款"), ("trust", "信托贷款"),
                   ("acceptances", "未贴现银行承兑汇票"), ("corporate_bonds", "企业债券净融资"),
                   ("government", "政府债券净融资"), ("equity", "非金融企业境内股票融资"),
                   ("abs", "存款类金融机构 ABS"), ("writeoffs", "贷款核销")]:
    define(f"tsf_{key}_flow", label, "亿元", "M", "中国人民银行",
           "社融单月分项；不是年内累计、存量差分或所有新签合同金额。负值保留；统计范围按当期原表。")
SERIES["tsf_rmb_flow"]["basis"] += "排除金融机构和境外借款人，与全部金融机构人民币贷款不同。"
SERIES["tsf_government_flow"]["basis"] += "含国债及地方一般债、专项债；官方回溯至2017年，之前缺项不等于零。"
SERIES["tsf_writeoffs_flow"]["basis"] += "核销是统计调整项目，不是当月新增客户借款。"
for key, label, formula in [
    ("direct", "企业债券＋股票融资", "企业债券净融资＋非金融企业境内股票融资"),
    ("offbalance", "委托＋信托＋未贴现票据", "委托贷款＋信托贷款＋未贴现银行承兑汇票"),
    ("remaining", "其余融资及统计调整", "同版社融总量－人民币贷款－政府债券－企业债券/股票组－委托/信托/票据组；含外币贷款、ABS、核销及未列示项和舍入差额"),
]:
    define(f"tsf_{key}_flow", label, "亿元", "M", "中国人民银行（本项目计算分组）",
           f"计算式：{formula}。仅在所需分项全部存在时计算，非央行独立发布的指标。")
for sector, name in [("household", "住户"), ("business", "境内企业等"), ("business_legacy", "非金融公司及其他部门（含非居民旧口径）")]:
    for term, label in [("total", "贷款余额"), ("short", "短期贷款余额"), ("long", "中长期贷款余额"), ("bills", "票据融资余额")]:
        if sector == "household" and term == "bills":
            continue
        define(f"loan_{sector}_{term}", name + label, "万亿元", "M", "中国人民银行",
               "金融机构人民币贷款月末余额，源亿元除以10000；不是当月新增贷款。2023年机构统计范围扩展。")
        if sector == "household":
            SERIES[f"loan_{sector}_{term}"]["basis"] += "早期短期/中长期按同表消费性＋经营性贷款相加；中长期不全是房贷，短期不全是消费贷。"
        elif sector == "business":
            SERIES[f"loan_{sector}_{term}"]["basis"] += "含机关团体等，2010年起境外单列；三类期限图不穷尽企业贷款，另有租赁、垫款等。"
        else:
            SERIES[f"loan_{sector}_{term}"]["basis"] += "2007—2009包含非居民，独立保存，不与境内企业线拼接。"


def chart(id, title, series, explanation, baseline=None, **options):
    result = dict(id=id, title=title, series=series, explanation=explanation)
    if baseline is not None:
        result["baseline"] = baseline
    return dict(result, **options)


TOPICS = {
    "credit-structure": {
        "title": "社融与信贷结构", "question": "融资增长来自谁，通过什么渠道，是否转化成了需求？",
        "intro": "先按渠道拆社融单月增量，再按借款人和期限观察人民币贷款余额。这两套统计不能相加；贷款余额不是当月新增贷款。政府债券支撑总量，不自动说明居民和企业借贷需求回升。",
        "charts": [
            chart("financing-composition", "社融增量：五组来源", ["tsf_rmb_flow", "tsf_government_flow", "tsf_direct_flow", "tsf_offbalance_flow", "tsf_remaining_flow"], "从政府债券官方回溯及全部分组的共同起点2017年开始堆叠；更早分项在后续图和下载中保留。正值向上、负值向下，黑线为净合计，上方柱顶不是总量。其余组为计算差额，含外币贷款、ABS、核销等，不是全新的融资渠道。2023年机构范围扩展需另看口径。", 0, kind="stacked", common_start=True),
            chart("financing-market", "贷款与企业直接融资：单月增量", ["tsf_rmb_flow", "tsf_corporate_bonds_flow", "tsf_equity_flow"], "保留2002年以来可核验历史。债券为净融资，股票融资不是股票市值；不能用曲线大小判断哪类融资更优。2017年政府债券回溯和2023年机构扩围见口径说明。", 0),
            chart("financing-offbalance", "委托、信托与未贴现票据", ["tsf_entrusted_flow", "tsf_trust_flow", "tsf_acceptances_flow"], "三条线是社融单月分项。信托2002—2005原表为缺失/业务很小的标记，不补零。未贴现票据转为贴现时，融资可能从票据项转入贷款项，不能仅凭某一项下降断言融资总量收缩。", 0),
            chart("loan-borrowers", "谁在借款：人民币贷款余额", ["loan_household_total", "loan_business_total", "loan_business_legacy_total"], "这里是月末余额，不能当作当月借款需求。旧企业线含非居民，与2010年起境外单列后的境内企业线分开。2007年起的部门表逐年回溯；2023年机构扩围，不能直接用跨口径余额计算可比增速。"),
            chart("loan-household-terms", "住户贷款：短期与中长期余额", ["loan_household_short", "loan_household_long"], "短期与中长期都可能包含消费和经营用途；中长期不全是房贷，短期也不全是消费贷。早期金额按同表的消费性与经营性分项相加。"),
            chart("loan-business-terms", "境内企业等：贷款期限与票据", ["loan_business_short", "loan_business_long", "loan_business_bills"], "短期贷款、中长期贷款与票据融资分别观察，不把短期贷款及票据融资的合计行再与票据相加。三条线不穷尽所有企业贷款，还包括租赁、垫款等；机关团体也在企业等范围内。"),
        ], "extra": ["tsf_fx_flow", "tsf_abs_flow", "tsf_writeoffs_flow", "loan_business_legacy_short", "loan_business_legacy_long", "loan_business_legacy_bills"],
        "reading": "credit-structure",
    },
    "quarterly-gdp": {
        "title": "中国季度 GDP", "question": "这个季度产出增长多快，和累计增长、上一季度有什么不同？",
        "intro": "使用国家统计局修订后的季度历史，分别展示当季、年内累计和季调环比。现价金额包含价格变化，实际增速剔除价格影响。季度资料与 World Bank 年度 GDP 独立保留，不混接。",
        "charts": [
            chart("gdp-quarter-yoy", "GDP：当季与累计实际同比", ["gdp_q_yoy", "gdp_ytd_yoy"], "当季同比比较本季与上年同季；累计同比比较年初至今与上年同期，例如 Q2 累计是上半年。两者不能相减得到其他季度增速。低基数会放大同比，应结合下一张环比图。", 0),
            chart("gdp-quarter-qoq", "GDP：季调实际环比", ["gdp_qoq_sa"], "比较剔除季节因素后的本季与上季，非年化。0.9% 表示比上季增长 0.9%，不是同比，也不是年增长率。历史值会随新数据和季调模型修订。", 0),
            chart("gdp-quarter-nominal", "GDP：当季现价金额", ["gdp_q_nominal"], "每个点是独立一个季度的产出增加值，未季调。年内起伏包含季节性；金额增长也包含价格因素，不能当作实际增速。累计金额在下方另列。"),
            chart("gdp-quarter-sectors", "三次产业：当季实际同比", ["gdp_primary_q_yoy", "gdp_secondary_q_yoy", "gdp_tertiary_q_yoy"], "比较农业相关、工业建筑相关和服务业的增长节奏；准确分类见口径说明。产业增速不能相加，也不等于对 GDP 增长的贡献率。", 0),
        ], "extra": ["gdp_ytd_nominal", "gdp_primary_q_nominal", "gdp_secondary_q_nominal", "gdp_tertiary_q_nominal"],
        "reading": "data/quarterly-gdp-methodology",
    },
    "prices": {
        "title": "物价与通胀", "question": "消费端和生产端价格怎样变化，涨价是否广泛？",
        "intro": "CPI 描述居民消费价格，核心 CPI 扣除食品和能源，PPI 描述工业生产者出厂价格。同比看相对上年同月，环比看相对上月，不能把同比序列连乘成价格水平。历史涨跌幅按官方发布保留；各期权重、分类变化和确实缺失的时期另作说明。",
        "charts": [
            chart("cpi-core", "CPI 与核心 CPI 同比", ["cpi_yoy", "core_cpi_yoy"], "总 CPI 与核心 CPI 的差异帮助观察食品、能源等因素，但两者之差不是这些项目的精确贡献率。"),
            chart("cpi-monthly", "CPI 环比", ["cpi_mom"], "观察最近一个月的价格变化。这里不是季调环比，春节错位、旅游旺季等季节性需要结合官方解读。"),
            chart("ppi", "生产端价格：PPI 同比", ["ppi_yoy"], "工业出厂价格与消费价格覆盖范围不同。PPI 上升不意味着 CPI 一定等幅上升，传导受成本、利润、库存与需求影响。"),
            chart("cpi-components", "食品、非食品与服务价格", ["food_cpi_yoy", "nonfood_cpi_yoy", "services_cpi_yoy"], "这些是分项涨幅，不是贡献率。服务属于非食品的一部分，三条线不能相加。食品也不等于更大的“食品烟酒”类别。"),
        ], "extra": ["food_cpi_legacy_yoy"], "reading": "growth-and-inflation",
    },
    "money-credit": {
        "title": "货币与社会融资", "question": "货币存量与融资是否增加，它们分别描述什么？",
        "intro": "M1、M2 是月末货币存量，社融从实体经济获得融资的角度统计。2025 年起 M1 增加个人活期存款和非银行支付机构客户备付金。本专题分别保留旧定义历史、新定义以及官方回溯的 2024 年新定义数据，不能把两种余额直接拼接。",
        "charts": [
            chart("money-stock", "M1 与 M2 月末余额", ["m1", "m2", "m1_old"], "M1 包含在 M2 中，不能相加。新旧 M1 分列，2024 年重叠部分展示定义变化的影响；不把 2025 年的口径扩展解读为货币突然暴增。M2 也不是全社会财富。"),
            chart("money-growth", "M1 与 M2 官方同比", ["m1_yoy", "m2_yoy", "m1_old_yoy"], "余额和增速分开看。采用官方可比同比，新旧 M1 分列；不能用跨口径余额自行计算同比，也不能仅凭货币增速推断股市涨跌。"),
            chart("credit-stock", "社融存量同比", ["tsf_stock_yoy"], "衡量存量融资扩张速度，不是当月新增融资增速。社融与 M2 来自不同统计角度，不应相加。"),
            chart("credit-flow", "社融当月增量", ["tsf_flow"], "单月流量可能受季节性和政府债券发行节奏影响。负值也可能出现；不把它与累计值混在同一条线上。"),
        ], "extra": ["tsf_stock"], "reading": "money-and-credit",
    },
    "rates": {
        "title": "利率与融资成本", "question": "政策操作、贷款报价与市场收益率如何变化？",
        "intro": "逆回购操作利率、LPR 和国债收益率对应不同环节。图中纵轴都是年化百分比，但经济含义不同；变动 0.10 个百分点等于 10 个基点。不同图的日度、月度频率不混用。",
        "charts": [
            chart("policy-repo", "7 天逆回购操作利率", ["repo_7d"], "只记录有明确利率的公开市场操作公告。未操作的日期没有观测，不填零，也不把缺失连成连续每日报价。"),
            chart("lpr", "LPR：1 年期与 5 年期以上", ["lpr_1y", "lpr_5y", "lpr_1y_pre2019"], "中国货币网历史图给出月内观察值。2019 年 8 月报价机制改革前的 1 年期 LPR 独立展示，5 年期以上品种自改革后开始。LPR 不等于借款人的实际利率。"),
            chart("bond-yields", "国债收益率：1 年与 10 年", ["yield_1y", "yield_10y"], "这是同一曲线不同期限的收益率，不是债券价格。长短端变化可能不同，利差也不是确定的经济预测。"),
        ], "reading": "interest-rates",
    },
    "activity": {
        "title": "景气、生产、消费与投资", "question": "近期经济活动在哪些环节增强或减弱？",
        "intro": "PMI 是调查扩散指数；工业、零售和投资是实际经营统计。它们观察对象不同，发布时间也不同。规模以上工业是实际增速，社零和投资是名义增速，不能因为单位相同就当成同一种量。",
        "charts": [
            chart("pmi", "制造业与非制造业景气", ["pmi_manufacturing", "pmi_nonmanufacturing"], "50 是扩张与收缩的调查临界点，不是 GDP 的零增长线。非制造业包含建筑业与服务业。", 50),
            chart("production-retail", "工业生产与消费零售同比", ["industry_yoy", "retail_yoy"], "两者可对照方向，但不是直接可比的实际需求增速。1—2 月合并发布值不冒充单独 2 月；图中缺口不插值。"),
            chart("investment", "固定资产投资累计同比", ["investment_ytd_yoy", "investment_legacy_ytd_yoy"], "每个点表示当年 1 月至该月。2011 年前旧范围/项目起报点单独展示；现行口径不含农户。不能把两个月的累计增速相减得到当月增速。"),
        ], "extra": ["industry_janfeb_yoy", "retail_janfeb_yoy"], "reading": "reading-macro-data",
    },
    "employment-income": {
        "title": "就业与居民收入", "question": "经济变化如何体现在就业和家庭购买力上？",
        "intro": "调查失业率是月度比例，居民收入按季度发布、以年内累计为主。本专题不把季度值复制成三个月的数值，也不将调查失业率、登记失业率或不同青年失业率口径拼成一条线。",
        "charts": [
            chart("unemployment", "全国城镇调查失业率", ["unemployment"], "失业率描述调查定义下劳动力中失业者的比例，不是未就业人口占全部人口的比例；单看它也不能反映工时和收入质量。"),
            chart("income-growth", "居民可支配收入：名义与实际累计增速", ["income_nominal_ytd_yoy", "income_real_ytd_yoy"], "实际增速扣除了价格因素。Q1、Q2、Q3、Q4 分别代表一季度、上半年、前三季度、全年累计，不能解读为单季环比。"),
        ], "extra": ["income_ytd"], "reading": "foundations/household-finance",
    },
    "trade-fx": {
        "title": "进出口与人民币汇率", "question": "外需、贸易收支与人民币计价怎样联系？",
        "intro": "货物贸易以单月美元金额展示，汇率单独使用日度人民币中间价。金额变化包含数量和价格因素，中间价不是市场即期成交价。顺差和汇率之间还隔着资本流动、利差、预期与政策等条件。",
        "charts": [
            chart("trade", "货物出口与进口：当月美元金额", ["exports", "imports"], "春节错位会影响单月比较。统计上存在 1—2 月合并发布时，不拆算成两个独立月份。这里不包含服务贸易。"),
            chart("trade-balance", "当月货物贸易差额", ["trade_balance"], "正值为出口大于进口，负值为逆差。保留官方单列的差额原值；部分历史月份与进出口相减不一致，超出舍入精度的差异在下方逐项列出，不擅自改算。贸易差额不等于企业利润或完整的经常账户差额。"),
            chart("exchange-midpoint", "USD/CNY 人民币中间价", ["usdcny_mid"], "数值上升表示一美元可兑换更多人民币，即人民币对美元贬值。这里是中间价，不是可直接成交的银行买卖报价。"),
        ], "reading": "exchange-rates",
    },
}


def topic_series(topic):
    return list(dict.fromkeys([s for c in topic["charts"] for s in c["series"]] + topic.get("extra", [])))

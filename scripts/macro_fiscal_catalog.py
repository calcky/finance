"""Fiscal definitions kept together so stock, flow and vintages stay explicit."""


def register(define, chart, topics):
    source = "财政部、国家统计局"
    annual = "年度来源，亿元、当年价；与12月累计执行数分开保存。1950年起长历史含预算范围与分类变化，不是恒定统计边界。"
    ytd = "年初至该月累计执行数，不是单月，不能按月相加；不含债务融资收入/还本，收入减支出不等于官方赤字。"
    for prefix, label in [("revenue", "一般公共预算收入"), ("expenditure", "一般公共预算支出")]:
        define("fiscal_"+prefix+"_annual", label+"（年度）", "亿元", "A", source, annual)
        define("fiscal_"+prefix+"_annual_yoy", label+"年度同比", "%", "A", source, "官方年度增速，按当期来源口径保存，不从金额重新计算。")
        define("fiscal_"+prefix+"_ytd", label+"累计值", "亿元", "M", source, ytd+"NBS历史优先，财政部补缺和新期。")
        define("fiscal_"+prefix+"_ytd_yoy", label+"累计同比", "%", "M", "国家统计局", "官方累计同比；2011/2015预算范围变化及2022退税等会影响可比性；不从旧金额计算，不与剔除退税后的增速拼接。")
    for key, label in [("tax", "税收收入"), ("nontax", "非税收入")]:
        define("fiscal_"+key+"_annual", label+"（年度）", "亿元", "A", "国家统计局", annual+"非税早期缺口不由差额反推。")
        define("fiscal_"+key+"_ytd", label+"累计值", "亿元", "M", "财政部", ytd+"同版财政部税收/非税合计可能与统计局修订后的总量不同。")
    for key, label in [("fund_revenue", "政府性基金收入"), ("fund_expenditure", "政府性基金支出")]:
        define("fiscal_"+key+"_ytd", label+"累计值", "亿元", "M", "财政部", "全国年内累计执行数；2013—2014只在季度末提供，不复制为月度；2015部分基金转列一般公共预算。")
        define("fiscal_"+key+"_annual", label+"（年度决算）", "亿元", "A", "财政部", "全国政府性基金决算，非中央本级；不含单列融资、调入及结转。独立于12月执行数。")
    define("fiscal_land_ytd", "土地出让收入累计值", "亿元", "M", "财政部", "地方国有土地使用权出让收入，政府性基金收入中的一部分；毛收入不等于可自由支配的净收益；仅同比而无金额时留缺口。")
    define("fiscal_land_fee_annual", "土地出让金收入（窄口径年度决算）", "亿元", "A", "财政部", "原表国有土地使用权出让金收入，不含其他土地相关基金；不可替代较宽的土地出让收入，也不与月报连线。")
    define("fiscal_central_debt_annual", "中央债务余额（年末）", "亿元", "A", "国家统计局", "中央财政法定债务年末存量，含国内/国外债务；不是当年发债、债务限额或全部公共部门负债。")
    for key, label in [("general", "一般"), ("special", "专项")]:
        define("fiscal_local_"+key+"_annual", "地方"+label+"债务余额（年度来源）", "亿元", "A", "财政部", "年度债务决算表的年末实际数；同年及次年表有修订时采用较晚表并记录版本，不将预计执行数当决算。")
        define("fiscal_local_"+key+"_stock", "地方"+label+"债务余额（月末）", "亿元", "M", "财政部", "月末法定地方政府债务存量，非月内新增；不含未纳入法定口径的隐性债务，与年度决算独立。")
    define("fiscal_local_total_stock", "地方债务总余额（月末）", "亿元", "M", "财政部", "法定地方债务，含债券和非债券形式；不把城投全部负债直接加入，不以发行减还本硬推余额。")
    for key, label, note in [
        ("gross", "发行总额", "含新增和偿旧，不等于新增财政刺激。"),
        ("new", "新增债券", "新增债券类别，不表示全部资金都已支出。"),
        ("refinancing", "再融资债券", "纯再融资类别；既可能滚续到期债券，也可能按政策用于化债，不能一律理解为常规到期再融资。"),
        ("swap", "置换债券（早期）", "早期单列置换，保留原类别。"),
        ("swap_refinancing", "置换和再融资合计（早期）", "原文只给合计，不拆分、不冒充纯再融资。"),
    ]:
        define("fiscal_issuance_"+key, "地方债当月"+label, "亿元", "M", "财政部", "当月发行流量，非年内累计。"+note)
    topics["fiscal"] = {
        "title": "财政政策与政府债务", "question": "收入、支出、债务余额与发债各说明什么，哪些数不能相加或直接作差？",
        "intro": "分开观察一般公共预算、政府性基金、法定债务存量和当月发行。年度来源与月度累计执行数独立保存；各年度统计范围会调整。地方债发行不等于同期财政支出，法定债务也不是整个公共部门的全部负债。",
        "charts": [
            chart("fiscal-annual", "一般公共预算：年度收入与支出", ["fiscal_revenue_annual", "fiscal_expenditure_annual"], "1950年起保留来源长历史；1950年代、预算外资金纳入及2007分类改革等口径不同。两条线之差不是正式预算赤字，还需核对调入、结转结余等资金。"),
            chart("fiscal-growth", "一般公共预算：累计同比", ["fiscal_revenue_ytd_yoy", "fiscal_expenditure_ytd_yoy"], "按年初至当前月与上年同期比较；不是当月或环比。NBS入库可能晚于财政部，最新金额与最新同比的统计期需分别看。2015预算调整、2022退税不能忽略。", 0),
            chart("fiscal-tax", "税收与非税：年度金额", ["fiscal_tax_annual", "fiscal_nontax_annual"], "非税历史缺口不按总收入减税收倒推；未找到的年份断线。非税增长不代表税基同比例改善，债券融资也不是这里的非税收入。"),
            chart("fiscal-ytd", "一般公共预算：累计执行金额", ["fiscal_revenue_ytd", "fiscal_expenditure_ytd"], "每年重新从1月累计；年末到次年初回落是期间重置，不是财政断崖。早年有真实1月数据，不统一删除1月。12月缺失不由年度来源填补。"),
            chart("fiscal-funds-annual", "政府性基金：全国年度决算", ["fiscal_fund_revenue_annual", "fiscal_fund_expenditure_annual"], "2010年起的已核验全国决算；中央本级不能替代全国。支出还可由专项债、结转等支持，不要求等于当年基金收入。"),
            chart("fiscal-funds", "政府性基金与土地收入：累计执行", ["fiscal_fund_revenue_ytd", "fiscal_fund_expenditure_ytd", "fiscal_land_ytd"], "土地收入包含在基金收入中，不能叠加。2013—2014只保留季度末；2015年3月、2019年3—12月土地金额缺失，不用同比反推。累计值跨年重置。"),
            chart("fiscal-debt-annual", "中央与地方：年度债务存量", ["fiscal_central_debt_annual", "fiscal_local_general_annual", "fiscal_local_special_annual"], "中央2005年起，地方2014年起；缺少早年地方余额不等于没有债务。一般/专项分类调整与存量认定会改变构成。这里只画法定债务，不合成广义政府债务率。"),
            chart("fiscal-local-stock", "地方一般债与专项债：月末余额", ["fiscal_local_general_stock", "fiscal_local_special_stock"], "存量不是发债量；2017年11月起档案，2018年1—2月暂缺。与年度决算有修订差异时分别保留。"),
            chart("fiscal-issuance", "地方债：当月发行用途", ["fiscal_issuance_gross", "fiscal_issuance_new", "fiscal_issuance_refinancing"], "总发行已含新增和再融资，不能三者相加。早期只给置换或置换+再融资合计的月份，纯再融资留空，见下一张图。"),
            chart("fiscal-issuance-legacy", "早期地方债：置换与合并类别", ["fiscal_issuance_swap", "fiscal_issuance_swap_refinancing"], "两类来自不同报告期间，分别保存；空白不是零，不能将合计拆成单独再融资。"),
        ],
        "extra": ["fiscal_revenue_annual_yoy", "fiscal_expenditure_annual_yoy", "fiscal_tax_ytd", "fiscal_nontax_ytd", "fiscal_land_fee_annual", "fiscal_local_total_stock"],
        "reading": "fiscal-policy-and-debt",
    }

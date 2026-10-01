/* GDP progressive enhancement. Static images remain if initialization fails. */
(() => {
  "use strict";
  const snapshot = window.FINANCE_GDP;
  if (!snapshot || !window.echarts) return;
  const years = snapshot.years;
  const definitions = [
    {id: "gdp-china", title: "中国 GDP：经济规模", series: "gdp_cny", unit: "万亿元", divisor: 1e12, countries: ["CHN"]},
    {id: "gdp-growth", title: "中国 GDP：实际增长速度", series: "gdp_growth", unit: "%", divisor: 1, countries: ["CHN"]},
    {id: "gdp-per-capita", title: "中国人均 GDP", series: "gdp_per_capita_usd", unit: "美元 / 人", divisor: 1, countries: ["CHN"]},
    {id: "gdp-comparison", title: "中美 GDP 对照", series: "gdp_usd", unit: "万亿美元", divisor: 1e12, countries: ["CHN", "USA"]},
  ];
  const names = {CHN: "中国", USA: "美国"};
  const format = new Intl.NumberFormat("zh-CN", {minimumFractionDigits: 2, maximumFractionDigits: 2});
  const tableRows = new Map();
  // Give the existing accessible Markdown table stable, linkable year rows.
  document.querySelectorAll("table tbody tr").forEach(row => {
    const year = row.cells[0]?.textContent.trim();
    if (years.includes(year) && row.cells.length === 6) {
      row.id = `gdp-year-${year}`;
      row.tabIndex = -1;
      tableRows.set(year, row);
    }
  });

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  for (const spec of definitions) {
    const image = document.querySelector(`img[src$="/${spec.id}.svg"]`);
    if (!image) continue;
    const fallback = image.closest("p") || image;
    const wrapper = element("section", "gdp-interactive");
    wrapper.id = `interactive-${spec.id}`;
    wrapper.setAttribute("aria-label", spec.title + "交互图");
    let chart;
    try {
      const tools = element("div", "gdp-tools");
      const yearLabel = element("label", "", "固定年份 ");
      const select = element("select", "gdp-year");
      select.setAttribute("aria-label", `${spec.title}：固定年份`);
      years.forEach(year => select.add(new Option(year, year)));
      yearLabel.append(select);
      tools.append(yearLabel);
      const rangeButtons = [];
      for (const [label, count] of [["全部", 0], ["近 20 年", 20], ["近 10 年", 10]]) {
        const button = element("button", "gdp-range", label);
        button.type = "button";
        button.setAttribute("aria-pressed", String(count === 0));
        tools.append(button);
        rangeButtons.push([button, count]);
      }
      wrapper.append(tools);
      const surface = element("div", "gdp-canvas");
      surface.setAttribute("role", "img");
      surface.setAttribute("aria-label", `${spec.title}，单位${spec.unit}。可用上方年份选择器读取数据。`);
      wrapper.append(surface);
      const readout = element("p", "gdp-readout");
      readout.setAttribute("aria-live", "polite");
      wrapper.append(readout);
      const rowLink = element("a", "gdp-row-link", "查看该年完整指标 →");
      wrapper.append(rowLink);
      wrapper.append(element("p", "gdp-help", "悬停查看 · 点击曲线区域固定年份 · 拖动下方滑块缩放。固定读数不会随鼠标移动改变。"));
      const metadata = snapshot.metadata[spec.series];
      wrapper.append(element("p", "gdp-source", `来源：World Bank · WDI · ${metadata.indicator}｜来源库更新 ${metadata.source_updated}｜快照 ${snapshot.retrieved_at.slice(0, 10)}（UTC）`));
      fallback.before(wrapper);
      chart = echarts.init(surface, null, {renderer: "svg"});
      const value = (country, year) => snapshot.series[spec.series][country][year] ?? null;
      const formatted = (country, year) => {
        const raw = value(country, year);
        return raw === null ? "缺失" : `${format.format(raw / spec.divisor)} ${spec.unit}`;
      };
      chart.setOption({
        animation: false,
        color: ["#3675b5", "#268566"],
        textStyle: {fontFamily: "sans-serif", fontSize: 13},
        grid: {left: 16, right: 22, top: 60, bottom: 90, containLabel: true},
        legend: {show: spec.countries.length > 1, top: 24},
        tooltip: {trigger: "axis", confine: true, axisPointer: {type: "line"},
          formatter: params => {
            if (!params.length) return "";
            const year = params[0].axisValue;
            return `${year} 年<br>` + spec.countries.map(country => `${names[country]}：${formatted(country, year)}`).join("<br>");
          }},
        xAxis: {type: "category", data: years, boundaryGap: false, axisLabel: {hideOverlap: true}},
        yAxis: {type: "value", name: spec.unit, nameLocation: "end", min: spec.series === "gdp_growth" ? null : 0,
          axisLabel: {formatter: v => v.toLocaleString("zh-CN")}},
        dataZoom: [{type: "slider", xAxisIndex: 0, bottom: 16, height: 24,
          start: 0, end: 100, filterMode: "none", minValueSpan: 1}],
        series: spec.countries.map(country => ({
          name: names[country], type: "line", showSymbol: false, connectNulls: false,
          lineStyle: {width: 2.5, type: country === "USA" ? "dashed" : "solid"},
          data: years.map(year => value(country, year) === null ? null : value(country, year) / spec.divisor),
        })),
      });

      function pin(year, highlight = true) {
        select.value = year;
        wrapper.dataset.selectedYear = year;
        readout.replaceChildren(element("span", "", `已固定 ${year} 年`),
          ...spec.countries.map(country => element("span", "", `${names[country]} ${formatted(country, year)}`)));
        rowLink.href = `#gdp-year-${year}`;
        chart.setOption({series: [{markLine: {silent: true, symbol: "none",
          lineStyle: {type: "dashed", color: "#607d8b"},
          label: {formatter: `${year} 年`, position: "insideEndTop"}, data: [{xAxis: year}]}}]});
        if (highlight) {
          tableRows.forEach(row => row.classList.remove("gdp-selected-row"));
          tableRows.get(year)?.classList.add("gdp-selected-row");
        }
      }
      select.addEventListener("change", () => {
        // A keyboard-selected year should always be visible, even after zooming.
        chart.dispatchAction({type: "dataZoom", start: 0, end: 100});
        rangeButtons.forEach(([button, count]) => button.setAttribute("aria-pressed", String(count === 0)));
        pin(select.value);
      });
      chart.getZr().on("click", event => {
        const position = [event.offsetX, event.offsetY];
        if (!chart.containPixel({gridIndex: 0}, position)) return;
        const index = Math.round(chart.convertFromPixel({xAxisIndex: 0}, event.offsetX));
        if (years[index]) pin(years[index]);
      });
      chart.on("datazoom", () => {
        rangeButtons.forEach(([button]) => button.setAttribute("aria-pressed", "false"));
      });
      rangeButtons.forEach(([button, count]) => button.addEventListener("click", () => {
        chart.dispatchAction({type: "dataZoom", startValue: Math.max(0, years.length - (count || years.length)), endValue: years.length - 1});
        rangeButtons.forEach(([b]) => b.setAttribute("aria-pressed", String(b === button)));
      }));
      rowLink.addEventListener("click", () => {
        const row = tableRows.get(select.value);
        tableRows.forEach(r => r.classList.remove("gdp-selected-row"));
        row?.classList.add("gdp-selected-row");
        row?.focus({preventScroll: true});
      });
      pin(years[years.length - 1], false);
      // Hide fallback only after a complete, successful initialization.
      fallback.classList.add("gdp-static-fallback");
      const observer = new ResizeObserver(() => chart.resize());
      observer.observe(surface);
    } catch (error) {
      chart?.dispose();
      wrapper.remove();
      fallback.classList.remove("gdp-static-fallback");
      console.error("GDP interactive chart unavailable; using static image.", error);
    }
  }
})();

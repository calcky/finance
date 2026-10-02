/* Progressive enhancement; committed data only, no API or CDN requests. */
(() => {
  "use strict";
  const snapshot = window.FINANCE_MACRO;
  if (!snapshot || !window.echarts) return;
  const format = new Intl.NumberFormat("zh-CN", {maximumFractionDigits: 8});
  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }
  for (const spec of snapshot.charts) {
    const image = document.querySelector(`img[src$="/macro-${spec.id}.svg"]`);
    if (!image) continue;
    const fallback = image.closest("p") || image;
    const wrapper = element("section", "gdp-interactive macro-interactive");
    wrapper.id = `interactive-${spec.id}`;
    wrapper.setAttribute("aria-label", spec.title + "交互图");
    let chart;
    try {
      const tools = element("div", "gdp-tools");
      const label = element("label", "", "固定期间 ");
      const select = element("select", "macro-period");
      select.setAttribute("aria-label", spec.title + "：固定期间");
      spec.periods.forEach(p => select.add(new Option(p, p)));
      label.append(select);
      tools.append(label);
      const counts = spec.frequency === "A" ? [["近 10 年", 10], ["近 20 年", 20]] : spec.frequency === "M" ? [["近 12 个月", 12], ["近 5 年", 60]] : spec.frequency === "Q" ? [["近 4 季度", 4], ["近 5 年", 20]] : [["近 60 天", 60], ["近 5 年", 1826]];
      const buttons = [["全部", 0], ...counts].map(([text, count]) => {
        const button = element("button", "gdp-range", text);
        button.type = "button";
        button.setAttribute("aria-pressed", String(count === 0));
        tools.append(button);
        return [button, count];
      });
      wrapper.append(tools);
      const surface = element("div", "gdp-canvas");
      surface.setAttribute("role", "img");
      surface.setAttribute("aria-label", spec.title + "，可用期间选择器读取数据");
      const readout = element("p", "gdp-readout");
      readout.setAttribute("aria-live", "polite");
      const link = element("a", "gdp-row-link", "查看该期数据表 →");
      wrapper.append(surface, readout, link);
      wrapper.append(element("p", "gdp-help", "悬停查看 · 点击绘图区固定期间 · 下拉框可选缺失期 · 拖动滑块缩放；缺失处不插值。"));
      const sources = [...new Set(spec.series.map(k => snapshot.definitions[k].source))].join("、");
      wrapper.append(element("p", "gdp-source", `来源：${sources}｜快照 ${snapshot.metadata.retrieved_at.slice(0, 10)}（UTC）｜单位：${spec.unit}`));
      fallback.before(wrapper);
      chart = echarts.init(surface, null, {renderer: spec.frequency === "D" ? "canvas" : "svg"});
      const valueText = (key, period) => {
        const value = spec.values[key][period];
        return value == null ? "缺失" : `${format.format(value)} ${spec.unit}`;
      };
      const stacked = spec.kind === "stacked";
      const plotSeries = spec.series.map((key, i) => ({name: snapshot.definitions[key].label,
        type: stacked ? "bar" : "line", stack: stacked ? "flow" : undefined, stackStrategy: "samesign",
        connectNulls: false, showSymbol: true, symbolSize: spec.frequency === "D" ? 3 : 6,
        lineStyle: {width: 2, type: i === 1 ? "dashed" : "solid"},
        data: spec.periods.map(p => stacked && spec.totals[p] == null ? null : (spec.values[key][p] ?? null)),
      }));
      if (stacked) plotSeries.push({name: "净合计", type: "line", connectNulls: false,
        itemStyle: {color: "#203047"}, lineStyle: {width: 2}, symbolSize: 4,
        data: spec.periods.map(p => spec.totals[p] ?? null)});
      chart.setOption({
        animation: false, color: ["#3675b5", "#268566", "#ab6540", "#8064a2", "#c09028", "#3a858a"],
        textStyle: {fontFamily: "sans-serif", fontSize: 12},
        grid: {left: 10, right: 20, top: 90, bottom: 90, containLabel: true},
        legend: {top: 8, type: "scroll"},
        tooltip: {trigger: "axis", confine: true, formatter: items => {
          if (!items.length) return "";
          const period = items[0].axisValue;
          return period + "<br>" + spec.series.map(k => `${snapshot.definitions[k].label}：${valueText(k, period)}`).join("<br>") +
            (stacked ? `<br>净合计：${spec.totals[period] == null ? "缺失" : format.format(spec.totals[period])} ${spec.unit}` : "");
        }},
        xAxis: {type: "category", data: spec.periods, boundaryGap: stacked, axisLabel: {hideOverlap: true}},
        yAxis: {type: "value", name: spec.unit, scale: !stacked},
        dataZoom: [{type: "slider", bottom: 16, height: 24, filterMode: "none", start: 0, end: 100, minValueSpan: 1}],
        series: plotSeries,
      });
      function pin(period) {
        select.value = period;
        wrapper.dataset.selectedPeriod = period;
        readout.replaceChildren(element("span", "", `已固定 ${period}`), ...spec.series.map(k => element("span", "", `${snapshot.definitions[k].label} ${valueText(k, period)}`)));
        if (stacked) readout.append(element("span", "", `净合计 ${spec.totals[period] == null ? "缺失" : format.format(spec.totals[period])} ${spec.unit}`));
        link.href = `#macro-${spec.id}-${period}`;
        const markers = [{xAxis: period}];
        if (spec.baseline !== undefined) markers.push({yAxis: spec.baseline, label: {formatter: "临界点 " + spec.baseline}});
        chart.setOption({series: [{markLine: {silent: true, symbol: "none", lineStyle: {type: "dashed", color: "#8492a6"}, label: {show: false}, data: markers}}]});
      }
      select.addEventListener("change", () => {
        chart.dispatchAction({type: "dataZoom", start: 0, end: 100});
        buttons.forEach(([b, n]) => b.setAttribute("aria-pressed", String(n === 0)));
        pin(select.value);
      });
      chart.getZr().on("click", event => {
        if (!chart.containPixel({gridIndex: 0}, [event.offsetX, event.offsetY])) return;
        const i = Math.round(chart.convertFromPixel({xAxisIndex: 0}, event.offsetX));
        if (spec.periods[i]) pin(spec.periods[i]);
      });
      chart.on("datazoom", () => buttons.forEach(([b]) => b.setAttribute("aria-pressed", "false")));
      buttons.forEach(([button, count]) => button.addEventListener("click", () => {
        chart.dispatchAction({type: "dataZoom", startValue: Math.max(0, spec.periods.length-(count || spec.periods.length)), endValue: spec.periods.length-1});
        buttons.forEach(([b]) => b.setAttribute("aria-pressed", String(b === button)));
      }));
      link.addEventListener("click", () => {
        const row = document.getElementById(`macro-${spec.id}-${select.value}`);
        row.closest("details").open = true;
        row.closest("table").querySelectorAll(".gdp-selected-row").forEach(r => r.classList.remove("gdp-selected-row"));
        row.classList.add("gdp-selected-row");
        row.focus({preventScroll: true});
      });
      pin(spec.periods.at(-1));
      fallback.classList.add("gdp-static-fallback");
      new ResizeObserver(() => chart.resize()).observe(surface);
    } catch (error) {
      chart?.dispose();
      wrapper.remove();
      fallback.classList.remove("gdp-static-fallback");
      console.error("Macro chart unavailable; using static image.", error);
    }
  }
})();

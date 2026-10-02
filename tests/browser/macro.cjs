// Build and serve docs first. Uses the same browser configuration as GDP tests.
const {chromium} = require("playwright");
const assert = require("node:assert/strict");
const base = process.env.MACRO_TEST_URL || "http://127.0.0.1:8767";
let checking = "launch";
const topics = {"quarterly-gdp": 4, prices: 4, "money-credit": 4, "credit-structure": 6, property: 6, fiscal: 10, rates: 3, "us-rates": 6, activity: 3, "employment-income": 2, "trade-fx": 3, population: 5, "shanghai-population": 2, "housing-prices": 4, "housing-wealth": 2};

(async () => {
  const browser = await chromium.launch({headless: true, channel: process.env.GDP_BROWSER_CHANNEL || undefined});
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 1100}});
    const errors = [], remote = [];
    page.on("pageerror", e => errors.push(e.message));
    page.on("request", r => {if (!r.url().startsWith(base)) remote.push(r.url());});
    for (const [slug, count] of Object.entries(topics)) {
      checking = slug;
      await page.goto(`${base}/data/${slug}.html`);
      assert(await page.locator(".sync-status").isVisible());
      assert.equal(await page.locator(".sync-status a").getAttribute("href"), "update-status.html");
      const specs = await page.evaluate(() => FINANCE_MACRO.charts);
      assert.equal(specs.length, count);
      for (const spec of specs) {
        checking = `${slug}/${spec.id}`;
        const preview = page.locator(`img[src$="/macro-${spec.id}.svg"]`);
        if (await preview.isVisible()) await preview.scrollIntoViewIfNeeded();
        const widget = page.locator(`#interactive-${spec.id}`);
        await widget.waitFor();
        async function selectPeriod(period) {
          if (spec.compact_history && spec.frequency === "D") {
            await widget.locator('input[type="date"]').fill(period);
            await widget.locator('input[type="date"]').dispatchEvent("change");
          } else await widget.locator("select").selectOption(period);
        }
        const period = spec.periods[Math.floor(spec.periods.length / 2)];
        await selectPeriod(period);
        assert.match(await widget.locator(".gdp-readout").innerText(), new RegExp(period));
        const pinned = await widget.locator(".gdp-readout").innerText();
        const format = new Intl.NumberFormat("zh-CN", {maximumFractionDigits: 8});
        for (const key of spec.series) {
          const value = spec.values[key][period];
          assert(pinned.includes(value == null ? "缺失" : format.format(value)));
        }
        // Early history must remain selectable independently of the visible
        // zoom window, including archived definitions and calendar gaps.
        await selectPeriod(spec.periods[0]);
        assert.match(await widget.locator(".gdp-readout").innerText(), new RegExp(spec.periods[0]));
        await selectPeriod(period);
        await widget.locator(".gdp-row-link").click();
        const row = page.locator(`#macro-${spec.id}-${period}`);
        assert(await row.isVisible());
        assert.match(await row.getAttribute("class"), /gdp-selected-row/);
        assert.equal(new URL(page.url()).hash, `#macro-${spec.id}-${period}`);
        const countWanted = spec.frequency === "A" ? 10 : spec.frequency === "M" ? 12 : spec.frequency === "Q" ? 4 : 60;
        await widget.locator("button").nth(1).click();
        const zoom = await widget.locator(".gdp-canvas").evaluate(node => echarts.getInstanceByDom(node).getOption().dataZoom[0]);
        assert.equal(zoom.endValue - zoom.startValue, Math.min(countWanted, spec.periods.length) - 1);
        await widget.getByRole("button", {name: "全部", exact: true}).click();
        const canvas = widget.locator(".gdp-canvas");
        await canvas.scrollIntoViewIfNeeded();
        const hit = await canvas.evaluate((node, spec) => {
          const chart = echarts.getInstanceByDom(node);
          const index = spec.periods.findIndex((p, i) => i > 0 && i < spec.periods.length - 1 && spec.values[spec.series[0]][p] != null);
          if (index < 0) throw new Error("No observed interior point to click");
          // Twenty years of daily dates can share a physical screen pixel.
          // Zoom before asserting exact mouse selection; the dropdown above
          // separately verifies exact dates at full-history scale.
          const span = spec.frequency === "D" ? 60 : spec.frequency === "M" ? 24 : 8;
          chart.dispatchAction({type: "dataZoom", startValue: Math.max(0, index - 5), endValue: Math.min(spec.periods.length - 1, index + span - 6)});
          const x = chart.convertToPixel({xAxisIndex: 0}, index);
          const y = chart.convertToPixel({yAxisIndex: 0}, spec.values[spec.series[0]][spec.periods[index]] ?? 0);
          const rect = node.getBoundingClientRect();
          return {x: rect.x+x, y: rect.y+y, period: spec.periods[index]};
        }, spec);
        await page.mouse.click(hit.x, hit.y);
        assert.equal(await widget.getAttribute("data-selected-period"), hit.period);
        await page.mouse.move(1, 1);
        assert.match(await widget.locator(".gdp-readout").innerText(), new RegExp(hit.period));
      }
      assert.equal(await page.locator(".macro-interactive").count(), count);
      const downloads = page.locator("a.reference.download");
      assert.equal(await downloads.count(), 2);
      const csvUrl = await downloads.first().getAttribute("href");
      const response = await page.request.get(new URL(csvUrl, page.url()).href);
      assert(response.ok());
      assert.match(await response.text(), /^series_id,country,period,value,unit,frequency,published_at,source_url,note/);
      const metaUrl = await downloads.nth(1).getAttribute("href");
      const metadata = await (await page.request.get(new URL(metaUrl, page.url()).href)).json();
      assert.equal(metadata.retrieved_at, await page.evaluate(() => FINANCE_MACRO.metadata.retrieved_at));
      assert.equal(metadata.schema_version, 2);
      for (const [key, coverage] of Object.entries(metadata.coverage)) {
        assert(coverage.first <= coverage.last && coverage.count > 0, key);
      }
      if (slug === "activity") {
        const widget = page.locator("#interactive-production-retail");
        await widget.locator("select").selectOption("2025-02");
        assert.match(await widget.locator(".gdp-readout").innerText(), /缺失/);
        const nulls = await widget.locator(".gdp-canvas").evaluate(node => echarts.getInstanceByDom(node).getOption().series.map(s => [s.connectNulls, s.data.includes(null)]));
        assert(nulls.every(([connect, missing]) => !connect && missing));
      }
      if (slug === "us-rates") {
        assert.equal(await page.locator(".macro-details tbody tr").count() <= 360, true);
        assert.equal(await page.locator('input[type="date"]').count(), 5);
        assert.equal(specs.find(s => s.id === "us-treasury-monthly").periods[0], "1953-04");
        assert(Object.values(metadata.series).every(s => s.country === "USA"));
        assert.match(await response.text(), /us_effr,USA,1954-07-01,1.13,/);
        const widget = page.locator("#interactive-us-term-spread");
        const input = widget.locator('input[type="date"]');
        await input.fill("1990-11-21");
        await input.dispatchEvent("change");
        assert.match(await widget.locator(".gdp-readout").innerText(), /0.72/);
        await widget.locator(".gdp-row-link").click();
        const details = page.locator("#details-us-term-spread");
        assert.match(await page.locator("#macro-us-term-spread-1990-11-21").innerText(), /0.72/);
        const before = await details.locator("tbody tr").first().innerText();
        await details.getByRole("button", {name: "更早60期", exact: true}).click();
        assert.notEqual(await details.locator("tbody tr").first().innerText(), before);
        await input.fill("1976-06-01");
        await input.dispatchEvent("change");
        await widget.locator(".gdp-row-link").click();
        assert(await details.getByRole("button", {name: "更早60期", exact: true}).isDisabled());
        for (const invalid of ["", "1900-01-01", "2099-01-01"]) {
          await input.fill(invalid);
          await input.dispatchEvent("change");
          assert.equal(await input.inputValue(), "1976-06-01");
          await widget.locator(".gdp-row-link").click();
          assert(await page.locator("#macro-us-term-spread-1976-06-01").isVisible());
        }
        if (process.env.US_RATES_SCREENSHOT) await widget.screenshot({path: process.env.US_RATES_SCREENSHOT});
      }
      if (slug === "credit-structure") {
        const widget = page.locator("#interactive-financing-composition");
        await widget.locator("select").selectOption("2026-08");
        assert.match(await widget.locator(".gdp-readout").innerText(), /净合计 16,577 亿元/);
        const series = await widget.locator(".gdp-canvas").evaluate(node => echarts.getInstanceByDom(node).getOption().series);
        assert.equal(series.length, 6);
        assert(series.slice(0, 5).every(s => s.type === "bar" && s.stack === "flow" && s.stackStrategy === "samesign"));
        assert(series.slice(0, 5).some(s => s.data.some(v => v < 0)));
        assert.equal(series[5].name, "净合计");
        assert.equal(series[5].type, "line");
        assert.equal(await widget.locator(".gdp-canvas").evaluate(node => echarts.getInstanceByDom(node).getOption().yAxis[0].scale), false);
        assert.equal(await page.locator("#macro-financing-composition-2026-08 td").last().innerText(), "16,577");
        const early = page.locator("#interactive-financing-offbalance");
        await early.locator("select").selectOption("2002-01");
        assert.match(await early.locator(".gdp-readout").innerText(), /信托贷款 缺失/);
      }
      if (slug === "property") {
        const widget = page.locator("#interactive-property-investment-level");
        await widget.locator("select").selectOption("2026-02");
        assert.doesNotMatch(await widget.locator(".gdp-readout").innerText(), /缺失/);
        await widget.locator("select").selectOption("2026-01");
        assert.match(await widget.locator(".gdp-readout").innerText(), /缺失/);
        assert(await widget.locator(".gdp-canvas").evaluate(node => {
          const option = echarts.getInstanceByDom(node).getOption();
          const index = option.xAxis[0].data.indexOf("2026-01");
          return option.series.every(s => s.data[index] === null && !s.connectNulls);
        }));
        const sales = specs.find(s => s.id === "property-sales-growth");
        assert.equal(sales.periods[0], "2006-02");
        // Scope transitions remain downloadable, without splicing them into
        // the current-scope chart or silently dropping the transition year.
        const key = "property_sales_area_ytd_transition";
        assert.equal(metadata.coverage[key].count, 11);
        assert.equal(metadata.coverage[key].first, "2005-02");
        assert.match(await response.text(), new RegExp(`${key},CHN,2005-02,`));
        assert.match(await page.locator("body").textContent(), /2005-02/);
      }
      if (slug === "population") {
        assert.equal(specs.find(s => s.id === "population-china").periods[0], "1949");
        const fertility = specs.find(s => s.id === "population-fertility");
        assert.equal(fertility.periods[0], "1950");
        assert.equal(fertility.periods.at(-1), "2023");
        const households = page.locator("#interactive-population-households");
        await households.locator("select").selectOption("2021");
        assert.match(await households.locator(".gdp-readout").innerText(), /缺失/);
        assert(specs.find(s => s.id === "population-households").series.every(k =>
          specs.find(s => s.id === "population-households").values[k]["2021"] == null));
      }
      if (slug === "housing-prices") {
        const spec = specs.find(s => s.id === "housing-shanghai-yoy");
        assert.equal(spec.periods[0], "2006-01");
        assert.equal(spec.values.housing_shanghai_new_yoy["2006-01"], undefined);
        assert.equal(typeof spec.values.housing_shanghai_new_yoy_legacy["2006-01"], "number");
        assert.equal(spec.values.housing_shanghai_new_yoy_legacy["2011-01"], undefined);
      }
      if (slug === "housing-wealth") {
        const spec = specs.find(s => s.id === "housing-wealth");
        assert.equal(spec.values.housing_wealth_history["2021"], undefined);
        assert.equal(typeof spec.values.housing_wealth_extension["2021"], "number");
        const lines = await page.locator("#interactive-housing-wealth .gdp-canvas")
          .evaluate(node => echarts.getInstanceByDom(node).getOption().series);
        assert.equal(lines[1].lineStyle.type, "dashed");
      }
      if (slug === "fiscal") {
        const annual = page.locator("#interactive-fiscal-annual");
        await annual.locator("select").selectOption("1950");
        assert.match(await annual.locator(".gdp-readout").innerText(), /62\.17/);
        assert.equal(specs.find(s => s.id === "fiscal-annual").frequency, "A");
        const funds = page.locator("#interactive-fiscal-funds");
        await funds.locator("select").selectOption("2013-04");
        assert.match(await funds.locator(".gdp-readout").innerText(), /缺失/);
        if (process.env.FISCAL_SCREENSHOT) await annual.screenshot({path: process.env.FISCAL_SCREENSHOT});
      }
      await page.emulateMedia({media: "print"});
      assert.equal(await page.locator(".macro-interactive:visible").count(), 0);
      assert.equal(await page.locator(".gdp-static-fallback:visible").count(), count);
      await page.emulateMedia({media: "screen"});
      console.log(`macro ${slug}: ${count} charts passed`);
    }
    assert.deepEqual(errors, []);
    assert.deepEqual(remote, []);
    const mobile = await browser.newPage({viewport: {width: 390, height: 844}, isMobile: true, hasTouch: true});
    await mobile.goto(`${base}/data/fiscal.html`);
    const fiscal = mobile.locator("#interactive-fiscal-annual");
    await fiscal.locator("select").selectOption("1950");
    assert.match(await fiscal.locator(".gdp-readout").innerText(), /62\.17/);
    await fiscal.locator(".gdp-row-link").tap();
    assert(await mobile.locator("#macro-fiscal-annual-1950").isVisible());
    assert.equal(await mobile.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
    await mobile.goto(`${base}/data/prices.html`);
    const widget = mobile.locator("#interactive-cpi-core");
    await widget.locator("select").selectOption("2026-03");
    assert.match(await widget.locator(".gdp-readout").innerText(), /2026-03/);
    await widget.locator(".gdp-row-link").tap();
    assert(await mobile.locator("#macro-cpi-core-2026-03").isVisible());
    const overflow = await mobile.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
    assert.equal(overflow, false);
    if (process.env.MACRO_SCREENSHOT) {
      await widget.scrollIntoViewIfNeeded();
      await widget.screenshot({path: process.env.MACRO_SCREENSHOT});
    }
    await mobile.goto(`${base}/data/quarterly-gdp.html`);
    const quarterly = mobile.locator("#interactive-gdp-quarter-yoy");
    await quarterly.locator("select").selectOption("1993-Q1");
    assert.match(await quarterly.locator(".gdp-readout").innerText(), /1993-Q1/);
    await quarterly.locator(".gdp-row-link").tap();
    assert(await mobile.locator("#macro-gdp-quarter-yoy-1993-Q1").isVisible());
    assert.equal(await mobile.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
    if (process.env.QUARTER_GDP_SCREENSHOT) await quarterly.screenshot({path: process.env.QUARTER_GDP_SCREENSHOT});
    await mobile.goto(`${base}/data/credit-structure.html`);
    const credit = mobile.locator("#interactive-financing-composition");
    await credit.locator("select").selectOption("2026-08");
    assert.match(await credit.locator(".gdp-readout").innerText(), /净合计 16,577 亿元/);
    await credit.locator(".gdp-row-link").tap();
    assert(await mobile.locator("#macro-financing-composition-2026-08").isVisible());
    assert.equal(await mobile.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
    if (process.env.CREDIT_SCREENSHOT) await credit.screenshot({path: process.env.CREDIT_SCREENSHOT});
    await mobile.goto(`${base}/data/property.html`);
    const property = mobile.locator("#interactive-property-building-growth");
    await property.locator("select").selectOption("2000-04");
    assert.match(await property.locator(".gdp-readout").innerText(), /缺失/);
    await property.locator(".gdp-row-link").tap();
    assert(await mobile.locator("#macro-property-building-growth-2000-04").isVisible());
    assert.equal(await mobile.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
    if (process.env.PROPERTY_SCREENSHOT) await property.screenshot({path: process.env.PROPERTY_SCREENSHOT});
    await mobile.goto(`${base}/data/us-rates.html`);
    await mobile.locator('img[src$="/macro-us-policy-rates.svg"]').scrollIntoViewIfNeeded();
    const us = mobile.locator("#interactive-us-policy-rates");
    await us.locator('input[type="date"]').fill("1954-07-01");
    await us.locator('input[type="date"]').dispatchEvent("change");
    assert.match(await us.locator(".gdp-readout").innerText(), /1.13/);
    await us.locator(".gdp-row-link").tap();
    assert(await mobile.locator("#macro-us-policy-rates-1954-07-01").isVisible());
    assert.equal(await mobile.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
    for (const slug of ["population", "shanghai-population", "housing-prices", "housing-wealth"]) {
      await mobile.goto(`${base}/data/${slug}.html`);
      const chart = mobile.locator(".macro-interactive").first();
      const select = chart.locator("select");
      await select.selectOption({index: 0});
      await chart.locator(".gdp-row-link").tap();
      assert.equal(await mobile.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
    }
    // Synthetic missing component: never render a partial stack as a total.
    const missing = await browser.newPage();
    await missing.addInitScript(() => {
      Object.defineProperty(window, "FINANCE_MACRO", {configurable: true, set(value) {
        const spec = value.charts.find(c => c.id === "financing-composition");
        if (spec) {
          delete spec.values[spec.series[0]]["2026-08"];
          delete spec.totals["2026-08"];
        }
        Object.defineProperty(window, "FINANCE_MACRO", {value, writable: true});
      }});
    });
    await missing.goto(`${base}/data/credit-structure.html`);
    const gap = missing.locator("#interactive-financing-composition");
    await gap.locator("select").selectOption("2026-08");
    assert.match(await gap.locator(".gdp-readout").innerText(), /净合计 缺失/);
    assert(await gap.locator(".gdp-canvas").evaluate(node => {
      const option = echarts.getInstanceByDom(node).getOption();
      const index = option.xAxis[0].data.indexOf("2026-08");
      return option.series.every(s => s.data[index] === null && !s.connectNulls);
    }));
    await missing.close();
    for (const js of [false, true]) {
      const fallback = await browser.newPage({javaScriptEnabled: js});
      if (js) await fallback.route("**/vendor/echarts-*.js*", route => route.abort());
      await fallback.goto(`${base}/data/prices.html`);
      assert.equal(await fallback.locator(".macro-interactive").count(), 0);
      assert.equal(await fallback.locator('img[src*="macro-"]:visible').count(), 4);
      await fallback.goto(`${base}/data/us-rates.html`);
      assert.equal(await fallback.locator(".macro-interactive").count(), 0);
      assert.equal(await fallback.locator('img[src*="macro-"]:visible').count(), 6);
      assert.equal(await fallback.locator(".macro-details tbody tr").count(), 360);
      assert.equal(await fallback.locator("a.reference.download").count(), 2);
      await fallback.close();
    }
    console.log("Macro mobile, downloads, missingness, print and static fallbacks passed");
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(`While checking ${checking}:`, error);
  if (process.env.GITHUB_ACTIONS) console.error("::error title=Macro browser test::" +
    `${checking}: ${error.stack || error}`.replaceAll("%", "%25").replaceAll("\r", "%0D").replaceAll("\n", "%0A"));
  process.exitCode = 1;
});

// Run after building and serving _build/html; GDP_TEST_URL may override localhost.
const {chromium} = require("playwright");
const assert = require("node:assert/strict");
const url = process.env.GDP_TEST_URL || "http://127.0.0.1:8767/data/gdp.html";

(async () => {
  const browser = await chromium.launch({headless: true});
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 1050}});
    const errors = [];
    const requests = [];
    page.on("pageerror", error => errors.push(error.message));
    page.on("request", request => requests.push(request.url()));
    await page.goto(url);
    await page.locator(".gdp-interactive").last().waitFor();
    assert.equal(await page.locator(".gdp-interactive").count(), 4);
    assert.equal(await page.locator(".gdp-static-fallback:visible").count(), 0);
    assert.equal(requests.filter(request => !request.startsWith(new URL(url).origin)).length, 0);

    for (const id of ["gdp-china", "gdp-growth", "gdp-per-capita", "gdp-comparison"]) {
      const widget = page.locator(`#interactive-${id}`);
      await widget.locator("select").selectOption("2020");
      assert.match(await widget.locator(".gdp-readout").innerText(), /已固定 2020 年/);
      assert.equal(await page.locator("#gdp-year-2020.gdp-selected-row").count(), 1);
      await widget.getByRole("button", {name: "近 10 年", exact: true}).click();
      const zoom = await widget.locator(".gdp-canvas").evaluate(node => {
        const chart = echarts.getInstanceByDom(node);
        return chart.getOption().dataZoom[0];
      });
      assert.equal(zoom.endValue - zoom.startValue, 9);
      await widget.getByRole("button", {name: "近 20 年", exact: true}).click();
      const zoom20 = await widget.locator(".gdp-canvas").evaluate(node => echarts.getInstanceByDom(node).getOption().dataZoom[0]);
      assert.equal(zoom20.endValue - zoom20.startValue, 19);
      await widget.getByRole("button", {name: "全部", exact: true}).click();

      const canvas = widget.locator(".gdp-canvas");
      await canvas.scrollIntoViewIfNeeded();
      // Drag the rendered right handle of the pinned ECharts 5.6 slider.
      const handle = canvas.locator('path[transform^="matrix(12,0,0,-12"]').last();
      const handleBox = await handle.boundingBox();
      assert(handleBox, "Missing time range handle");
      await page.mouse.move(handleBox.x + handleBox.width / 2, handleBox.y + handleBox.height / 2);
      await page.mouse.down();
      await page.mouse.move(handleBox.x - 100, handleBox.y + handleBox.height / 2, {steps: 12});
      await page.mouse.up();
      await page.waitForFunction(id => echarts.getInstanceByDom(document.querySelector(`#interactive-${id} .gdp-canvas`)).getOption().dataZoom[0].end < 99, id);
      await widget.getByRole("button", {name: "全部", exact: true}).click();
      const point = await canvas.evaluate(node => {
        const chart = echarts.getInstanceByDom(node);
        const index = window.FINANCE_GDP.years.indexOf("2010");
        const data = chart.getOption().series[0].data[index];
        const [x, y] = chart.convertToPixel({seriesIndex: 0}, [index, data]);
        const rect = node.getBoundingClientRect();
        return {x: rect.x + x, y: rect.y + y};
      });
      await page.mouse.move(point.x, point.y);
      // Axis tooltip is HTML; check actual visible hover content, not just state.
      await page.getByText("2010 年", {exact: false}).last().waitFor({state: "visible"});
      await page.mouse.click(point.x, point.y);
      assert.match(await widget.locator(".gdp-readout").innerText(), /已固定 2010 年/);
      await page.mouse.move(1, 1);
      assert.match(await widget.locator(".gdp-readout").innerText(), /已固定 2010 年/);
    }

    const comparison = page.locator("#interactive-gdp-comparison");
    await comparison.locator("select").selectOption("2025");
    const pinned = await comparison.locator(".gdp-readout").innerText();
    const cells = await page.locator("#gdp-year-2025 td").allTextContents();
    assert(pinned.includes(`中国 ${cells[4].trim()} 万亿美元`));
    assert(pinned.includes(`美国 ${cells[5].trim()} 万亿美元`));
    await comparison.locator(".gdp-row-link").click();
    assert.equal(new URL(page.url()).hash, "#gdp-year-2025");
    assert.equal(await page.locator("#gdp-year-2025.gdp-selected-row").count(), 1);

    const growth = page.locator("#interactive-gdp-growth");
    // Explicit display fixtures: future source revisions may fill early gaps.
    await page.evaluate(() => {
      FINANCE_GDP.series.gdp_growth.CHN["1960"] = null;
      FINANCE_GDP.series.gdp_growth.CHN["1961"] = -5;
    });
    await growth.locator("select").selectOption("1960");
    assert.match(await growth.locator(".gdp-readout").innerText(), /缺失/);
    await growth.locator("select").selectOption("1961");
    assert.match(await growth.locator(".gdp-readout").innerText(), /中国 -/);

    // Keyboard access to exact values does not depend on hitting tiny points.
    await comparison.locator("select").focus();
    await page.keyboard.press("ArrowUp");
    await page.keyboard.press("Enter");
    assert.match(await comparison.locator(".gdp-readout").innerText(), /2024/);
    await comparison.scrollIntoViewIfNeeded();
    if (process.env.GDP_SCREENSHOT) await comparison.screenshot({path: process.env.GDP_SCREENSHOT});
    await page.emulateMedia({media: "print"});
    assert.equal(await page.locator(".gdp-interactive:visible").count(), 0);
    assert.equal(await page.locator(".gdp-static-fallback:visible").count(), 4);
    assert.deepEqual(errors, []);

    const mobile = await browser.newContext({viewport: {width: 390, height: 844}, isMobile: true, hasTouch: true, deviceScaleFactor: 1});
    const touch = await mobile.newPage();
    await touch.goto(url);
    const mobileWidget = touch.locator("#interactive-gdp-comparison");
    await mobileWidget.getByRole("button", {name: "近 10 年", exact: true}).tap();
    const touchCanvas = mobileWidget.locator(".gdp-canvas");
    await touchCanvas.scrollIntoViewIfNeeded();
    const point = await touchCanvas.evaluate(node => {
      const c = echarts.getInstanceByDom(node), i = FINANCE_GDP.years.indexOf("2020");
      const [x, y] = c.convertToPixel({seriesIndex: 0}, [i, c.getOption().series[0].data[i]]);
      const r = node.getBoundingClientRect();
      return {x: r.x + x, y: r.y + y};
    });
    await touch.touchscreen.tap(point.x, point.y);
    assert.match(await mobileWidget.locator(".gdp-readout").innerText(), /2020/);
    const bounds = await mobileWidget.boundingBox();
    assert(bounds.x >= 0 && bounds.x + bounds.width <= 391, "Chart overflows mobile viewport");
    if (process.env.GDP_MOBILE_SCREENSHOT) await mobileWidget.screenshot({path: process.env.GDP_MOBILE_SCREENSHOT});

    const noJS = await browser.newContext({javaScriptEnabled: false});
    const plain = await noJS.newPage();
    await plain.goto(url);
    assert.equal(await plain.locator('img[src*="gdp-"]:visible').count(), 4);
    assert.equal(await plain.locator("table").count() >= 2, true);
    const broken = await browser.newPage();
    await broken.route("**/vendor/echarts-*.js*", route => route.abort());
    await broken.goto(url);
    assert.equal(await broken.locator('img[src*="gdp-"]:visible').count(), 4);
    console.log("PASS: four charts, hover, click pin, exact values, ranges, keyboard, null/negative data, table link, touch, print, offline assets and fallback.");
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });

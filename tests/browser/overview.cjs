// A snapshot overview must work without JavaScript, on mobile, and in print.
const {chromium} = require("playwright");
const assert = require("node:assert/strict");
const base = process.env.MACRO_TEST_URL || "http://127.0.0.1:8767";

(async () => {
  const browser = await chromium.launch({headless: true, channel: process.env.GDP_BROWSER_CHANNEL || undefined});
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 1050}, javaScriptEnabled: false});
    const errors = [], remote = [];
    page.on("pageerror", e => errors.push(e.message));
    page.on("request", r => {if (!r.url().startsWith(base)) remote.push(r.url());});
    await page.goto(`${base}/data/overview.html`);
    assert.equal(await page.locator(".overview-grid").count(), 6);
    assert.equal(await page.locator(".overview-card:visible").count(), 12);
    const diagram = page.locator('img[src*="rate-transmission"]');
    assert.equal(await diagram.count(), 1);
    assert(await diagram.evaluate(n => n.complete && n.naturalWidth > 0));
    const editable = await page.getByRole("link", {name: "下载可编辑源图"}).getAttribute("href");
    assert((await page.request.get(new URL(editable, page.url()).href)).ok());
    for (const card of await page.locator(".overview-card").all()) {
      const text = await card.innerText();
      assert.match(text, /统计期/);
      assert.match(text, /上一有效观测/);
      assert.match(text, /来源发布日期/);
      assert.match(text, /快照获取/);
      assert.match(text, /本项目覆盖/);
      const link = card.getByRole("link", {name: "查看完整历史与口径"});
      const href = await link.getAttribute("href");
      assert(href.endsWith(".html"), href);
      assert((await page.request.get(new URL(href, page.url()).href)).ok());
    }
    const bars = page.locator(".overview-range");
    assert((await bars.count()) >= 10);
    for (const bar of await bars.all()) {
      assert.match(await bar.getAttribute("aria-label"), /区间最低.*最高/);
      const value = Number.parseFloat(await bar.locator("span").evaluate(n => n.style.left));
      assert(value >= 0 && value <= 100);
    }
    for (const scenario of await page.locator(".overview-scenario").all()) {
      const summary = scenario.locator("summary");
      await summary.focus();
      await page.keyboard.press("Enter");
      assert.equal(await scenario.getAttribute("open"), "");
      assert(await scenario.locator("p").first().isVisible());
      assert((await scenario.locator("a[href$='.html']").count()) > 0, "Scenario Markdown must render into links");
    }
    for (const link of await page.locator("main a.reference.internal, .rst-content a.reference.internal").all()) {
      const href = await link.getAttribute("href");
      if (href && !href.startsWith("#")) assert((await page.request.get(new URL(href, page.url()).href)).ok(), href);
    }
    await page.getByRole("link", {name: "查看完整历史与口径"}).first().click();
    assert(new URL(page.url()).pathname.endsWith("/data/quarterly-gdp.html"));
    await page.goto(`${base}/data/overview.html`);
    if (process.env.OVERVIEW_SCREENSHOT) await page.screenshot({path: process.env.OVERVIEW_SCREENSHOT, fullPage: true});
    const mobile = await browser.newPage({viewport: {width: 390, height: 844}, isMobile: true, hasTouch: true});
    await mobile.goto(`${base}/data/overview.html`);
    assert.equal(await mobile.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
    const cards = mobile.locator(".overview-card");
    const a = await cards.nth(0).boundingBox(), b = await cards.nth(1).boundingBox();
    assert(b.y >= a.y + a.height, "Cards must stack on mobile");
    await mobile.locator(".overview-scenario summary").first().tap();
    assert.equal(await mobile.locator(".overview-scenario").first().getAttribute("open"), "");
    if (process.env.OVERVIEW_MOBILE_SCREENSHOT) await mobile.screenshot({path: process.env.OVERVIEW_MOBILE_SCREENSHOT, fullPage: true});
    await page.emulateMedia({media: "print"});
    assert.equal(await page.locator(".overview-card:visible").count(), 12);
    assert.deepEqual(errors, []);
    assert.deepEqual(remote, []);
    console.log("PASS: overview cards, source clocks, ranges, topic links, keyboard/touch scenarios, mobile layout, print, no-JS and local assets.");
  } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exitCode = 1;});

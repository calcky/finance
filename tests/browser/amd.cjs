// Run after building and serving _build/html; AMD_TEST_URL may override localhost.
const {chromium} = require("playwright");
const assert = require("node:assert/strict");

const url = process.env.AMD_TEST_URL || "http://127.0.0.1:8767/investing/amd.html";

(async () => {
  const browser = await chromium.launch({
    headless: true,
    channel: process.env.AMD_BROWSER_CHANNEL || process.env.GDP_BROWSER_CHANNEL || undefined,
    executablePath: process.env.AMD_BROWSER_EXECUTABLE || undefined,
  });
  try {
    const page = await browser.newPage({javaScriptEnabled: false});
    await page.goto(url);
    const chart = page.getByRole("img", {name: /AMD.*股价趋势/});
    assert(await chart.isVisible(), "AMD chart must be visible without JavaScript");
    const image = await chart.evaluate(node => ({width: node.naturalWidth, height: node.naturalHeight}));
    assert(image.width >= 900 && image.height >= 400, "AMD chart image did not load");
    assert.match(await chart.locator("xpath=ancestor::a").getAttribute("href"), /amd-price-history-tradingview\.png$/);
    const mobile = await browser.newPage({viewport: {width: 390, height: 844}, javaScriptEnabled: false});
    await mobile.goto(url);
    const bounds = await mobile.getByRole("img", {name: /AMD.*股价趋势/}).boundingBox();
    assert(bounds && bounds.x >= 0 && bounds.x + bounds.width <= 391, "AMD chart overflows mobile viewport");
    console.log("PASS: AMD price chart is visible without JavaScript.");
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});

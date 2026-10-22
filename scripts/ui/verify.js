/**
 * 前端浏览器验证脚本（无头 Chromium）。
 *
 * 用法：
 *   node scripts/ui/verify.js [BASE_URL]        默认 http://127.0.0.1:8787
 *
 * 依赖：
 *   - npm i playwright && npx playwright install chromium
 *   - WSL 下无头 Chromium 缺系统库时见 DEVELOPMENT.md「无头浏览器」一节
 *
 * 检查项：多视口栅格列数、无横向溢出、图表渲染、无 console 报错，并截图。
 */

const path = require("path");
const { createRequire } = require("module");

/** playwright 装在哪儿不固定（仓库不 vendoring），按候选目录依次解析。 */
function loadPlaywright() {
  const bases = [
    process.env.PLAYWRIGHT_HOME,
    "/tmp/uitest",
    process.cwd(),
    __dirname,
  ].filter(Boolean);
  for (const base of bases) {
    try {
      return createRequire(path.join(base, "noop.js"))("playwright");
    } catch {
      /* 试下一个 */
    }
  }
  throw new Error(
    "找不到 playwright。先执行：mkdir -p /tmp/uitest && cd /tmp/uitest && npm i playwright"
  );
}

const { chromium } = loadPlaywright();

const BASE = process.argv[2] || process.env.BASE || "http://127.0.0.1:8787";
const OUT = process.env.SHOT_DIR || "/tmp/aidash-shots";
const VIEWPORTS = [
  ["wide", 1680, 1150],
  ["laptop", 1280, 950],
  ["tablet", 820, 950],
  ["phone", 414, 880],
];

(async () => {
  const fs = require("fs");
  fs.mkdirSync(OUT, { recursive: true });

  const browser = await chromium.launch();
  let failed = false;

  for (const [name, width, height] of VIEWPORTS) {
    const page = await browser.newPage({ viewport: { width, height } });
    const errors = [];
    page.on("pageerror", (e) => errors.push(`PAGEERROR: ${e.message}`));
    page.on("console", (m) => {
      if (m.type() === "error") errors.push(`CONSOLE: ${m.text()}`);
    });

    await page.goto(BASE, { waitUntil: "networkidle" });
    await page.waitForTimeout(1200);
    await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true });

    const info = await page.evaluate(() => {
      const board = document.querySelector(".board");
      const cards = [...document.querySelectorAll(".card")];
      return {
        cards: cards.length,
        cols: board ? getComputedStyle(board).gridTemplateColumns.split(" ").length : 0,
        rows: new Set(cards.map((c) => Math.round(c.getBoundingClientRect().top))).size,
        donuts: document.querySelectorAll("svg.donut").length,
        stacked: document.querySelectorAll("svg.chart--stacked").length,
        scrollW: document.documentElement.scrollWidth,
        innerW: window.innerWidth,
        title: document.querySelector(".topbar h1")?.textContent,
      };
    });

    const expectCols = width >= 1180 ? 3 : width >= 760 ? 2 : 1;
    const problems = [];
    if (info.cols !== expectCols) problems.push(`列数 ${info.cols} != 期望 ${expectCols}`);
    if (info.scrollW > info.innerW) problems.push(`横向溢出 ${info.scrollW}>${info.innerW}`);
    if (errors.length) problems.push(...errors);

    console.log(
      `${problems.length ? "FAIL" : "OK  "} ${name.padEnd(7)} cols=${info.cols} rows=${info.rows} ` +
        `cards=${info.cards} donuts=${info.donuts} stacked=${info.stacked}` +
        (problems.length ? ` | ${problems.join("; ")}` : "")
    );
    if (problems.length) failed = true;
    await page.close();
  }

  await browser.close();
  process.exit(failed ? 1 : 0);
})();

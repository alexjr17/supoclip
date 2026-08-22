import { chromium } from "playwright";

const URL = "http://127.0.0.1:3001/";

async function run(scenario) {
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  const page = await browser.newPage();
  const logs = [];
  page.on("console", (m) => {
    const type = m.type();
    if (["error", "warning"].includes(type)) logs.push(`[${type}] ${m.text().slice(0, 300)}`);
  });
  page.on("pageerror", (e) => logs.push(`[pageerror] ${String(e).slice(0, 300)}`));

  if (scenario === "extension") {
    await page.addInitScript(() => {
      const apply = () => document.documentElement.setAttribute("nighteye", "disabled");
      if (document.documentElement) apply();
      else document.addEventListener("readystatechange", apply);
    });
  }

  await page.goto(URL, { waitUntil: "networkidle", timeout: 60000 });
  await page.waitForTimeout(3000);

  const result = await page.evaluate(() => {
    const html = document.documentElement;
    const link = document.querySelector('link[rel="stylesheet"][href*=".css"]');
    const sheets = [...document.styleSheets].map((s) => s.href || "inline").slice(0, 5);
    const bodyBg = getComputedStyle(document.body).backgroundColor;
    const bodyColor = getComputedStyle(document.body).color;
    const h1 = document.querySelector("h1");
    const h1Color = h1 ? getComputedStyle(h1).color : null;
    const overlay = document.querySelector("nextjs-portal");
    return {
      nighteye: html.getAttribute("nighteye"),
      linkHref: link ? link.href : null,
      sheets,
      bodyBg,
      bodyColor,
      h1Text: h1 ? h1.textContent.slice(0, 40) : null,
      h1Color,
      hasDevOverlay: !!overlay,
    };
  });

  console.log(`\n=== SCENARIO: ${scenario} ===`);
  console.log(JSON.stringify(result, null, 2));
  console.log("--- CONSOLE ---");
  console.log(logs.join("\n") || "(sin errores)");
  await browser.close();
}

await run("control");
await run("extension");

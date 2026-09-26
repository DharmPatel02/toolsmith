// Synthetic screen history (plan §3): walks the mock-site flows the synthetic history describes,
// screenshots each step and posts them to /capture/batch backdated to past weekdays, the same path
// the Chrome extension uses, so the Why? evidence strip shows real screenshots of "past" sessions.
//
//   node scripts/synth_frames.mjs [--api http://localhost:8000] [--site http://localhost:8081] [--days 3]
// Needs Playwright (web/node_modules) and the mock site + API running.
import { chromium } from "../web/node_modules/playwright/index.mjs";

const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`);
  return i > 0 ? process.argv[i + 1] : fallback;
};
const API = arg("api", "http://localhost:8000");
const SITE = arg("site", "http://localhost:8081");
const DAYS = Number(arg("days", "3"));
const USER = "u_1";

// flow -> steps: [path, what the user did (ui event), trigger]
const FLOWS = {
  uc3: [
    ["/products", { kind: "nav", role: "document", name: "PriceWatch products" }],
    ["/competitor-b/products", { kind: "nav", role: "document", name: "ShopB catalog" }],
    ["/report", { kind: "click", role: "button", name: "Save report" }],
    ["/apps/slack", { kind: "submit", role: "form", name: "Post to #pricing" }],
  ],
  uc2: [
    ["/apps/inbox", { kind: "nav", role: "document", name: "Inbox" }],
    ["/apps/tracker", { kind: "submit", role: "form", name: "Update tracker row" }],
    ["/apps/slack", { kind: "submit", role: "form", name: "Post to #warehouse" }],
    ["/apps/jira", { kind: "click", role: "button", name: "Create issue" }],
  ],
};

function pastWeekdays(n) {
  const out = [];
  const d = new Date();
  while (out.length < n) {
    d.setUTCDate(d.getUTCDate() - 1);
    if (d.getUTCDay() !== 0 && d.getUTCDay() !== 6) out.push(new Date(d));
  }
  return out.reverse();
}

// Playwright screenshots are PNG/JPEG; re-encode in the browser as 1280px WebP q0.7, like the extension.
async function toWebpB64(page, png) {
  return page.evaluate(async (b64) => {
    const img = new Image();
    img.src = `data:image/png;base64,${b64}`;
    await img.decode();
    const scale = Math.min(1, 1280 / img.width);
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(img.width * scale);
    canvas.height = Math.round(img.height * scale);
    canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL("image/webp", 0.7).split(",")[1];
  }, png.toString("base64"));
}

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
let posted = 0;
for (const [flow, steps] of Object.entries(FLOWS)) {
  for (const [dayIndex, day] of pastWeekdays(DAYS).entries()) {
    const start = new Date(day);
    start.setUTCHours(flow === "uc3" ? 9 : 14, 0, 0, 0);
    const sessionId = `synth_${flow}_${dayIndex + 1}`;
    const events = [];
    const frames = [];
    for (const [i, [path, ev]] of steps.entries()) {
      await page.goto(SITE + path, { waitUntil: "load" });
      const ts = new Date(start.getTime() + i * 45_000).toISOString();
      const clientId = `${sessionId}_f${i}`;
      const shot = await page.screenshot({ type: "png" });
      frames.push({
        client_id: clientId,
        ts,
        trigger: ev.kind === "nav" ? "nav" : "click",
        app: "chrome",
        window_title: await page.title(),
        url_template: SITE + path.replace(/\/m\d+\//, "/{id}/"),
        image_webp_b64: await toWebpB64(page, shot),
      });
      events.push({
        ts,
        kind: ev.kind,
        url_template: SITE + path.replace(/\/m\d+\//, "/{id}/"),
        element: { role: ev.role, name: ev.name, data_attr: {} },
        value_shape: null,
        frame_id: clientId,
      });
    }
    const res = await fetch(`${API}/capture/batch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: USER, capture_session_id: sessionId, source: "chrome", events, frames }),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(`${sessionId}: ${res.status} ${JSON.stringify(body).slice(0, 300)}`);
    posted += frames.length;
    console.log(`${sessionId} ${start.toISOString().slice(0, 10)}: ${body.ui_events} events, ${body.frames_kept} frames kept`);
  }
}
await browser.close();
console.log(`done: ${posted} frames posted`);

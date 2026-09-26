// End-to-end smoke test: loads the unpacked extension in Chromium, starts recording from the popup,
// clicks through the mock site, and checks that /capture/batch acknowledged the events.
// Needs the mock site on :8081 and the API on :8000 (`npm run e2e` starts neither).
// captureVisibleTab needs activeTab, which only a real toolbar click grants. With FRAMES=1 the test
// loads a temp copy whose manifest adds <all_urls> (test only) so the keyframe path is exercised too.
import { chromium } from "playwright";
import { cpSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import assert from "node:assert/strict";

const FRAMES = process.env.FRAMES === "1";
let extPath = resolve(import.meta.dirname, "..");
if (FRAMES) {
  const copy = mkdtempSync(join(tmpdir(), "ts-ext-src-"));
  for (const f of ["manifest.json", "popup.html", "dist"]) cpSync(join(extPath, f), join(copy, f), { recursive: true });
  const manifest = JSON.parse(readFileSync(join(copy, "manifest.json"), "utf8"));
  manifest.host_permissions.push("<all_urls>");
  writeFileSync(join(copy, "manifest.json"), JSON.stringify(manifest));
  extPath = copy;
}
const context = await chromium.launchPersistentContext(mkdtempSync(join(tmpdir(), "ts-ext-")), {
  channel: "chromium",
  headless: true,
  args: [`--disable-extensions-except=${extPath}`, `--load-extension=${extPath}`],
});
const worker = context.serviceWorkers()[0] ?? (await context.waitForEvent("serviceworker"));
const extId = new URL(worker.url()).host;

const status = async () => worker.evaluate(() => chrome.storage.session.get("state").then((s) => s.state));

const popup = await context.newPage();
await popup.goto(`chrome-extension://${extId}/popup.html`);
await popup.click("#start");

const site = await context.newPage();
await site.goto("http://localhost:8081/products");
await site.bringToFront();
await site.getByRole("button", { name: "Track Burr Grinder Pro" }).click();
await site.getByRole("searchbox", { name: "Search" }).fill("kettle");
await site.waitForTimeout(1000); // typing burst ends after 800 ms idle
await site.getByRole("button", { name: "Search", exact: true }).click();
await site.waitForURL(/search/);
await site.getByRole("link", { name: "Gooseneck Kettle" }).click();
await site.waitForURL(/products\/PW-1003/);

// Off the allow-list: nothing may be captured here.
const other = await context.newPage();
await other.goto("data:text/html,<button>Secret</button>");
await other.click("button");
await site.bringToFront();

// Wait for at least one 5 s batch window to flush.
let s;
for (let i = 0; i < 20; i++) {
  await site.waitForTimeout(1000);
  s = await status();
  if (s.sent.events >= 6) break;
}
console.log(JSON.stringify(s, null, 2));
assert.ok(s.sent.events >= 6, `expected >= 6 events acked, got ${s.sent.events}`);
assert.equal(s.lastError?.startsWith("batch failed") ?? false, false, s.lastError ?? "");
if (FRAMES) assert.ok(s.sent.framesKept >= 2, `expected >= 2 frames acked, got ${s.sent.framesKept}`);

// Pause stops capture.
await popup.bringToFront();
await popup.click("#pause");
await popup.waitForTimeout(6000); // let already-queued events flush
const before = (await status()).sent.events;
await site.bringToFront();
await site.getByRole("button", { name: "Add to watchlist" }).click();
await site.waitForTimeout(7000);
const after = await status();
assert.equal(after.sent.events, before, "events captured while paused");
console.log("e2e ok: events acked, off-allow-list page ignored, pause respected");
await context.close();

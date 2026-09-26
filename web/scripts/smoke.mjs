// Loads every page and fails on console errors / page errors / failed requests.
// Usage: node scripts/smoke.mjs [baseUrl]   (dev server must be running; mock mode by default)
import { chromium } from "playwright";

const base = process.argv[2] ?? "http://localhost:3000";
const pages = ["/", "/suggestions", "/chat", "/policy", "/capture", "/demo", "/tools/tool_uc1", "/candidates/candidate_fixture"];
const browser = await chromium.launch();
const page = await browser.newPage();
const problems = [];
page.on("console", (m) => m.type() === "error" && problems.push(`console: ${m.text()}`));
page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
page.on("requestfailed", (r) => problems.push(`requestfailed: ${r.url()} ${r.failure()?.errorText}`));
for (const path of pages) {
  const before = problems.length;
  await page.goto(base + path, { waitUntil: "networkidle" });
  await page.waitForTimeout(600);
  const h1 = await page.locator("h1").first().textContent().catch(() => null);
  console.log(`${problems.length === before ? "ok  " : "FAIL"} ${path} — ${h1}`);
}
// Interaction checks (mock mode): each maps to a task's Test line.
const check = async (name, fn) => {
  try {
    await fn();
    console.log(`ok   ${name}`);
  } catch (e) {
    problems.push(`${name}: ${e.message.slice(0, 200)}`);
    console.log(`FAIL ${name}`);
  }
};
const t = { timeout: 10000 };
await check("P3.1.4 accept → P3.2.1 stepper reaches passed", async () => {
  await page.goto(base + "/suggestions");
  await page.getByRole("button", { name: "Accept" }).click();
  await page.getByText("Gate passed").waitFor(t);
  await page.getByRole("button", { name: "Approve", exact: true }).waitFor(t);
});
await check("P3.1.4 decline with never-for scope", async () => {
  await page.goto(base + "/suggestions");
  await page.getByRole("button", { name: "Decline" }).first().click();
  await page.getByRole("switch", { name: "Never for this" }).click();
  await page.getByLabel("Scope").fill("/finance");
  await page.getByRole("dialog").getByRole("button", { name: "Decline" }).click();
  await page.getByText("never for /finance").waitFor(t);
});
await check("P3.1.4 why drawer shows episodes + evidence strip", async () => {
  await page.goto(base + "/suggestions");
  await page.getByRole("button", { name: "Why?" }).click();
  await page.getByText("Matching episodes").waitFor(t);
  if ((await page.locator("figure img").count()) < 3) throw new Error("expected 3 evidence thumbnails");
});
await check("P3.2.2 dry run → preview → confirm → result", async () => {
  await page.goto(base + "/tools/tool_uc1");
  await page.getByRole("button", { name: "Dry run" }).click();
  await page.getByText("would write").waitFor(t);
  await page.getByRole("button", { name: "Confirm and run" }).click();
  await page.getByText(/Done in/).waitFor(t);
});
await check("P3.2.3 chat renders reply cards", async () => {
  await page.goto(base + "/chat");
  await page.getByRole("button", { name: /Why did you suggest/ }).click();
  await page.getByText("Recalled episodes").waitFor(t);
});
await check("P3.3.7 race streams both sides and freezes on final numbers", async () => {
  await page.goto(base + "/tools/tool_uc1");
  await page.getByRole("button", { name: /Race: agent from scratch/ }).click();
  await page.getByText(/^Final:/).waitFor({ timeout: 20000 });
});
await check("P3.3.2 metrics page renders charts", async () => {
  await page.goto(base + "/policy");
  await page.getByText("Logs only vs logs + screen").waitFor(t);
  await page.waitForTimeout(800);
  const bars = await page.locator(".recharts-bar-rectangle").count();
  if (bars < 4) throw new Error(`expected bars, got ${bars}`);
  await page.getByRole("button", { name: "Table" }).first().click();
  await page.getByRole("cell", { name: "Workflows found" }).waitFor(t);
});
await check("P3.3.1 policy strip shows because + approves pending change", async () => {
  await page.goto(base + "/");
  await page.getByText(/because/).first().waitFor(t);
  await page.getByRole("button", { name: /^Approve/ }).first().click();
  await page.getByText("Change approved").waitFor(t);
});
await check("P3.3.3 demo: switch v2 -> heal timeline with time to heal", async () => {
  await page.goto(base + "/demo");
  await page.getByRole("button", { name: "Switch to v2" }).click();
  await page.getByText(/time to heal/).waitFor({ timeout: 15000 });
  await page.getByRole("button", { name: "Run prune" }).click();
  await page.getByText(/Prune ran/).waitFor(t);
});
await check("P3.3.6 capture: pause flips state, audit list renders", async () => {
  await page.goto(base + "/capture");
  await page.getByRole("button", { name: "Pause" }).click();
  await page.getByRole("button", { name: "Resume" }).waitFor(t);
  await page.getByRole("button", { name: "Resume" }).click();
  await page.getByText("Capture audit").waitFor(t);
});
await check("P4.2.4 chat idea -> Build it -> candidate link", async () => {
  await page.goto(base + "/chat");
  await page.getByRole("button", { name: /I have an idea/ }).click();
  await page.getByRole("button", { name: "Build it" }).click();
  await page.getByText(/Forging: follow candidate/).waitFor(t);
});
await browser.close();
if (problems.length) {
  console.error(problems.join("\n"));
  process.exit(1);
}

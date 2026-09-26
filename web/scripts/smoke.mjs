// Loads every page and fails on console errors / page errors / failed requests.
// Usage: node scripts/smoke.mjs [baseUrl]   (dev server must be running; mock mode by default)
import { chromium } from "playwright";

const base = process.argv[2] ?? "http://localhost:3000";
const pages = ["/", "/onboarding", "/suggestions", "/approvals", "/connectors", "/chat", "/policy", "/capture", "/demo", "/tools/tool_uc1", "/candidates/candidate_fixture"];
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
await check("plan: card shows what will be automated; approve needs permissions first", async () => {
  await page.goto(base + "/suggestions");
  await page.getByRole("heading", { name: "What will be automated" }).first().waitFor(t);
  await page.getByRole("button", { name: "Review & approve" }).first().click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("list", { name: "What will be automated" }).waitFor(t);
  const build = dialog.getByRole("button", { name: /Grant \d+ permission|Approve and build/ });
  if (/Grant/.test(await build.innerText())) {
    for (const btn of await dialog.getByRole("button", { name: "Connect" }).all()) await btn.click();
  }
  await dialog.getByRole("button", { name: "Approve and build" }).click();
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
  await page.getByRole("button", { name: "Why?" }).first().click();
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
await check("onboarding: consent -> load demo history", async () => {
  await page.goto(base + "/onboarding");
  await page.getByRole("button", { name: "Allow screen activity" }).click();
  await page.getByText("You allowed screen activity").waitFor(t);
  await page.getByRole("button", { name: "Load demo history" }).click();
  await page.getByRole("link", { name: "See suggestions" }).waitFor(t);
});
await check("connected apps: connect and revoke", async () => {
  await page.goto(base + "/connectors");
  const slack = page.locator("[data-slot=card]", { hasText: "Slack" });
  if (await slack.getByRole("button", { name: "Revoke" }).count()) await slack.getByRole("button", { name: "Revoke" }).click();
  await slack.getByRole("button", { name: "Connect" }).click();
  await slack.getByRole("button", { name: "Revoke" }).waitFor(t);
  await slack.getByRole("button", { name: "Revoke" }).click();
  await slack.getByRole("button", { name: "Connect" }).waitFor(t);
});
await check("approvals: reject needs a reason, approve executes", async () => {
  await page.goto(base + "/approvals");
  const card = page.locator("[data-slot=card]").first();
  await card.getByRole("button", { name: "Approve" }).click();
  await page.getByText(/Approved: \d+ action/).waitFor(t);
});
await check("tool: confirmed run shows in history and can be undone", async () => {
  await page.goto(base + "/tools/tool_uc1");
  await page.getByRole("button", { name: "Dry run" }).click();
  await page.getByRole("button", { name: "Confirm and run" }).click();
  await page.getByText(/Done in/).waitFor(t);
  const history = page.getByRole("list", { name: "Run history" });
  await history.getByRole("button", { name: "Undo" }).first().click();
  await page.getByText(/Undone: \d+ action/).waitFor(t);
});
await check("tool: delete with don't-suggest-again", async () => {
  await page.goto(base + "/tools/tool_uc1");
  await page.getByRole("button", { name: "Delete tool" }).click();
  await page.getByRole("switch", { name: "Don't suggest again" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Delete", exact: true }).click();
  await page.getByText(/won't be suggested again/).waitFor(t);
});
await browser.close();
if (problems.length) {
  console.error(problems.join("\n"));
  process.exit(1);
}

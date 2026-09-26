// Typed client for every endpoint in task board §3.4.
// Mock mode (NEXT_PUBLIC_USE_MOCKS=true, or the sidebar switch which overrides it per browser)
// serves web/mocks/*.json and records each call in `mockLog`, so pages can be built without a backend.
import type {
  ActionItem,
  Approval,
  AutomationPlan,
  CaptureSession,
  Connector,
  RunSummary,
  CaptureState,
  Candidate,
  ChatCard,
  ChatReply,
  EpisodeHit,
  IdeaAnalysis,
  LineageTree,
  Metrics,
  PolicyDoc,
  RunResult,
  Suggestion,
  ToolDetail,
  ToolSummary,
  ToolVersion,
  WhyResponse,
} from "./types";

import candidateMock from "@/mocks/candidate_uc1.json";
import candidateUc2Mock from "@/mocks/candidate_uc2.json";
import chatReplyMock from "@/mocks/chat_reply.json";
import declinedMock from "@/mocks/declined.json";
import ideaCoveredMock from "@/mocks/idea_covered.json";
import ideaNewMock from "@/mocks/idea_new.json";
import metricsMock from "@/mocks/metrics.json";
import patternMock from "@/mocks/pattern_uc1.json";
import policyMock from "@/mocks/policy.json";
import runResultMock from "@/mocks/run_result.json";
import suggestionsMock from "@/mocks/suggestions.json";
import toolInvoiceMock from "@/mocks/tool_invoice.json";
import toolMock from "@/mocks/tool_uc1.json";
import toolsMock from "@/mocks/tools.json";
import whyMock from "@/mocks/why_uc1.json";
import whyUc2Mock from "@/mocks/why_uc2.json";

export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000").replace(/\/$/, "");
const ENV_MOCKS = process.env.NEXT_PUBLIC_USE_MOCKS !== "false";
const MOCK_KEY = "toolsmith.isMockMode";

export function isMockMode(): boolean {
  if (typeof window === "undefined") return ENV_MOCKS;
  try {
    const override = window.localStorage.getItem(MOCK_KEY);
    return override === null ? ENV_MOCKS : override === "true";
  } catch {
    return ENV_MOCKS;
  }
}

export function setUseMocks(value: boolean | null) {
  try {
    if (value === null) window.localStorage.removeItem(MOCK_KEY);
    else window.localStorage.setItem(MOCK_KEY, String(value));
  } catch {
    /* storage blocked: env default stays */
  }
}

export const mockLog: { method: string; path: string; body?: unknown; at: number }[] = [];

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(`${status}: ${detail}`);
  }
}

function clone<T>(value: unknown): T {
  return structuredClone(value) as T;
}

async function request<T>(method: "GET" | "POST", path: string, body?: unknown, mock?: () => unknown): Promise<T> {
  if (isMockMode() && mock) {
    mockLog.push({ method, path, body, at: Date.now() });
    console.info(`[mock] ${method} ${path}`, body ?? "");
    await new Promise((r) => setTimeout(r, 150));
    const value = clone<T>(mock());
    saveMockState(); // mocks mutate the demo state (connect, approve, run, delete, ...)
    return value;
  }
  const res = await fetch(API_BASE + path, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const json = await res.json();
      detail = typeof json.detail === "string" ? json.detail : JSON.stringify(json.detail ?? json);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

const get = <T>(path: string, mock?: () => unknown) => request<T>("GET", path, undefined, mock);
const post = <T>(path: string, body?: unknown, mock?: () => unknown) => request<T>("POST", path, body ?? {}, mock);

// Mock step labels are generated from backend/app/automation/plan.py STEPS (keep in sync).
// Mock-only state so the demo flow (accept → forge → approve, pause, layout switch) behaves plausibly.
const mockState = {
  paused: false,
  mocksite: "v1" as "v1" | "v2",
  connected: new Set<string>(),
  approvals: [] as Approval[],
  runs: [] as (RunSummary & { tool_id: string })[],
  deletedTools: new Set<string>(),
  promoted: new Set<string>(), // tools built during this demo session
  hiddenPatterns: new Set<string>(), // accepted, declined or snoozed suggestions
  deletedAt: null as string | null,
};

// Invoice demo (UC2): what the real invoice tool reports for each synthetic invoice
// (data/artifacts/uc2_invoices; verified by running the tool on the PDFs).
const UC2_INVOICES: Record<string, { number: string; vendor: string; po: string; note: string }> = {
  "inv-2201.pdf": { number: "INV-2201", vendor: "Northwind Supplies", po: "PO-4101", note: "" },
  "inv-2202.pdf": { number: "INV-2202", vendor: "Acme Packaging", po: "PO-4102", note: "AC-14 qty 165 vs PO 150" },
  "inv-2203.pdf": { number: "INV-2203", vendor: "BlueRiver Logistics", po: "PO-4103", note: "" },
  "inv-2204.pdf": { number: "INV-2204", vendor: "Northwind Supplies", po: "PO-4104", note: "" },
  "inv-2205.pdf": { number: "INV-2205", vendor: "Acme Packaging", po: "PO-4105", note: "AC-30 unit_price 2.45 vs PO 2.1" },
  "inv-2206.pdf": { number: "INV-2206", vendor: "BlueRiver Logistics", po: "PO-4106", note: "" },
  "inv-2207.pdf": { number: "INV-2207", vendor: "Acme Packaging", po: "PO-4107", note: "AC-14 qty 260 vs PO 220" },
};

function invoiceActions(file: string): ActionItem[] {
  const inv = UC2_INVOICES[file] ?? UC2_INVOICES["inv-2202.pdf"];
  const status = inv.note ? "mismatch" : "matched";
  const items: ActionItem[] = [
    {
      kind: "tracker.upsert",
      payload: { ref: inv.number, vendor: inv.vendor, status, note: inv.note },
      description: `Mark ${inv.number} as ${status} in the tracker${inv.note ? ` (${inv.note})` : ""}`,
      needs_approval: false,
      status: "pending",
    },
  ];
  if (inv.note) {
    const text = `${inv.number} (${inv.vendor}) does not match ${inv.po}: ${inv.note}`;
    items.push(
      { kind: "slack.post", payload: { channel: "#warehouse", text }, description: `Post in #warehouse: ${text}`, needs_approval: true, status: "pending" },
      {
        kind: "jira.create",
        payload: { summary: `${inv.number} mismatch vs ${inv.po}`, description: inv.note },
        description: `Open Jira ticket: ${inv.number} mismatch vs ${inv.po}`,
        needs_approval: true,
        status: "pending",
      },
    );
  }
  return items;
}

function mockInvoiceRun(toolId: string, params: Record<string, unknown>, confirm: boolean): RunResult {
  const file = String(params.invoice ?? "inv-2202.pdf");
  const inv = UC2_INVOICES[file] ?? UC2_INVOICES["inv-2202.pdf"];
  const items = invoiceActions(file);
  const runId = `run_mock_${mockState.runs.length + 1}`;
  const summary = `${inv.number} from ${inv.vendor}: ${inv.note ? `mismatch (${inv.note})` : "matched"}`;
  let status: RunResult["status"] = "preview";
  if (confirm) {
    for (const item of items) {
      if (!item.needs_approval) Object.assign(item, { status: "done", receipt: { id: `row_${inv.number}` } });
    }
    status = inv.note ? "awaiting_approval" : "done";
    mockState.runs.unshift({ run_id: runId, tool_id: toolId, started_at: new Date().toISOString(), mode: "live", outcome: "success", status, duration_ms: 780, actions: items });
    if (inv.note) {
      mockState.approvals.unshift({
        run_id: runId,
        tool_id: toolId,
        tool_title: "Invoice check and notify",
        created_at: new Date().toISOString(),
        summary,
        actions: items.filter((i) => i.needs_approval),
      });
    }
  }
  return {
    run_id: runId,
    mode: confirm ? "live" : "dry_run",
    output: { summary },
    intended_writes: items.map((i) => ({ path: i.kind, kind: `action:${i.kind}`, payload: i.payload })),
    needs_confirm: !confirm,
    duration_ms: 780,
    tokens: 0,
    route: "found",
    tool_id: toolId,
    score: 1,
    status,
    actions: items,
  };
}

function mockSuggestions(): Suggestion[] {
  return (suggestionsMock as Suggestion[])
    .filter((s) => !mockState.hiddenPatterns.has(s.pattern_id))
    .map((s) =>
      s.pattern_id === "pat_uc2" && mockState.deletedTools.has("tool_invoice")
        ? { ...s, deleted_at: mockState.deletedAt, deleted_tool_id: "tool_invoice", reason: `${s.reason} Since you deleted the tool, you did it by hand 2 more times.` }
        : s,
    );
}

// Demo state survives a refresh during a presentation (per tab; Sets stored as arrays).
const MOCK_STATE_KEY = "toolsmith.mockState";
function saveMockState() {
  try {
    window.sessionStorage.setItem(MOCK_STATE_KEY, JSON.stringify(mockState, (_k, v) => (v instanceof Set ? { __set: [...v] } : v)));
  } catch {
    /* storage blocked: state lives until reload */
  }
}
function restoreMockState() {
  try {
    const raw = typeof window === "undefined" ? null : window.sessionStorage.getItem(MOCK_STATE_KEY);
    if (!raw) return;
    const saved = JSON.parse(raw, (_k, v) => (v && typeof v === "object" && Array.isArray(v.__set) ? new Set(v.__set) : v));
    Object.assign(mockState, saved);
  } catch {
    /* corrupt or blocked: start fresh */
  }
}
restoreMockState();

/** Starts the demo story over (Demo controls). */
export function resetMockState() {
  try {
    window.sessionStorage.removeItem(MOCK_STATE_KEY);
  } catch {
    /* ignore */
  }
}

/** Mock mode: the consent popup (real consent page on the mock site) reports back here. */
export function markMockConnected(app: string) {
  mockState.connected.add(app);
  saveMockState();
}

const MOCKSITE_PUBLIC = (process.env.NEXT_PUBLIC_MOCKSITE_URL ?? "http://localhost:8081").replace(/\/$/, "");

type MockStep = [label: string, automation: "auto" | "approval" | "manual", connector: string | null, scope: string | null];
const MOCK_STEPS: Record<string, MockStep> = {
  "file.open": ["Open the input file", "auto", null, null],
  "file.save": ["Save the result", "auto", null, null],
  "file.download": ["Download the file", "auto", null, null],
  "file.upload": ["Upload a file", "approval", null, null],
  "file.copy": ["Copy the file", "auto", null, null],
  "table.rename": ["Rename columns", "auto", null, null],
  "table.dropna": ["Drop empty rows", "auto", null, null],
  "table.cast": ["Fix column types", "auto", null, null],
  "table.pivot": ["Pivot the table", "auto", null, null],
  "table.filter": ["Filter rows", "auto", null, null],
  "table.join": ["Match against the reference table", "auto", null, null],
  "table.sort": ["Sort rows", "auto", null, null],
  "table.groupby": ["Group and summarize", "auto", null, null],
  "table.dedupe": ["Remove duplicates", "auto", null, null],
  "table.aggregate": ["Aggregate totals", "auto", null, null],
  "table.select": ["Pick columns", "auto", null, null],
  "table.compare": ["Compare against the competitor", "auto", null, null],
  "chart.bar": ["Draw a bar chart", "auto", null, null],
  "chart.line": ["Draw a trend line", "auto", null, null],
  "chart.scatter": ["Draw a scatter plot", "auto", null, null],
  "export.html": ["Write the HTML report", "auto", null, null],
  "export.pdf": ["Write the PDF report", "auto", null, null],
  "export.csv": ["Write the CSV export", "auto", null, null],
  "report.html": ["Write the HTML report", "auto", null, null],
  "doc.read": ["Read the document", "auto", null, null],
  "doc.extract": ["Extract the key fields", "auto", null, null],
  "web.navigate": ["Open the site", "auto", "web", null],
  "web.fetch": ["Fetch the pages", "auto", "web", null],
  "web.extract": ["Read products and prices", "auto", "web", null],
  "web.click": ["Click through the site", "auto", "web", null],
  "web.submit": ["Submit a form on the site", "manual", "web", null],
  "email.open": ["Read new invoices from the inbox", "auto", "email", "mail:read"],
  "email.reply": ["Reply to the vendor", "approval", "email", "mail:send"],
  "msg.send": ["Send an email", "approval", "email", "mail:send"],
  "pdf.extract": ["Extract invoice number, lines and totals from the PDF", "auto", null, null],
  "invoice.validate": ["Check quantities and prices against the PO", "auto", null, null],
  "tracker.upsert": ["Add or update the tracker row", "auto", "tracker", "rows:write"],
  "slack.post": ["Post an alert in Slack", "approval", "slack", "chat:write"],
  "jira.create": ["Open a Jira ticket for the mismatch", "approval", "jira", "issues:write"],
};

function mockPlan(signature: string[], minutes = 0): AutomationPlan {
  const steps = signature.map((raw) => {
    const verb = raw.split(":")[0];
    const [label, automation, connector] = MOCK_STEPS[verb] ?? [verb.replace(".", " "), "auto", null, null];
    return { step: raw, label, automation, connector };
  });
  const needed = new Map<string, string[]>();
  for (const raw of signature) {
    const entry = MOCK_STEPS[raw.split(":")[0]];
    if (entry && entry[2] && entry[2] !== "web" && entry[3]) needed.set(entry[2], [entry[3]]);
  }
  const counts = { auto: 0, approval: 0, manual: 0 };
  for (const step of steps) counts[step.automation] += 1;
  return {
    steps,
    permissions: [...needed].map(([connector, scopes]) => ({ connector, scopes, granted: mockState.connected.has(connector) })),
    counts,
    est_minutes_saved_week: minutes,
  };
}

const MOCK_CONNECTORS: [app: string, name: string, scopes: string[]][] = [
  ["slack", "Slack", ["chat:write"]],
  ["jira", "Jira", ["issues:write"]],
  ["tracker", "Shipment tracker", ["rows:write"]],
  ["email", "Email inbox", ["mail:read"]],
];

/** Resolves a server-relative asset path (e.g. frame thumb_url) against the API. */
export function assetUrl(path: string): string {
  if (/^https?:/.test(path)) return path;
  if (isMockMode()) return path.startsWith("/mock/") ? path : "/mock-frame.webp";
  return API_BASE + path;
}

/** P2's concierge emits `{type: "episodes"|"tools"|"run", items|result}`; the UI renders `{kind, ...}`. */
function normalizeCard(card: unknown): ChatCard | null {
  const c = card as Record<string, unknown>;
  if (typeof c?.kind === "string") return c as unknown as ChatCard;
  switch (c?.type) {
    case "episodes":
      return { kind: "episodes", episodes: (c.items ?? []) as EpisodeHit[] };
    case "tools":
      return { kind: "tool_hits", hits: (c.items ?? []) as { tool_id: string; name: string; score: number }[] };
    case "run":
      return { kind: "run", run: { ...(c.result as RunResult), tool_id: (c.tool_id as string) ?? (c.result as RunResult)?.tool_id } };
    default:
      return null;
  }
}

export const api = {
  // Ingest + capture (P1)
  observationsBulk: (body: { user_id: string; events: unknown[] }) =>
    post<{ inserted: number; sessions_touched: number }>("/observations/bulk", body, () => ({ inserted: body.events.length, sessions_touched: 1 })),
  captureBatch: (body: unknown) =>
    post<{ ui_events: number; frames_kept: number; frames_dropped: number; paused: boolean }>("/capture/batch", body, () => ({
      ui_events: 0,
      frames_kept: 0,
      frames_dropped: 0,
      paused: mockState.paused,
    })),
  frameThumbUrl: (frameId: string) => assetUrl(`/frames/${frameId}/thumb`),
  captureSessions: () =>
    get<CaptureSession[]>("/capture/sessions", () => [
      {
        _id: "cap_mock",
        started_at: new Date(Date.now() - 20 * 60_000).toISOString(),
        ended_at: null,
        sources: ["chrome"],
        apps_seen: ["chrome"],
        frames_kept: 41,
        frames_dropped_by_rule: { rate_limit: 12, sensitive_focus: 1, not_allowed: 3 },
        paused: mockState.paused,
      },
    ]),
  captureState: () =>
    get<CaptureState>("/capture/state", () => ({ paused: mockState.paused, allowed_origins: ["http://localhost:8081"] })),
  capturePause: () => post<{ ok: boolean }>("/capture/pause", undefined, () => ((mockState.paused = true), { ok: true })),
  captureResume: () => post<{ ok: boolean }>("/capture/resume", undefined, () => ((mockState.paused = false), { ok: true })),
  captureDeleteLast: (minutes = 5) =>
    post<{ deleted_frames: number; deleted_events: number }>(`/capture/delete_last?minutes=${minutes}`, undefined, () => ({
      deleted_frames: 6,
      deleted_events: 14,
    })),

  // Suggestions (P1)
  suggestions: () => get<Suggestion[]>("/suggestions", () => mockSuggestions()),
  declinedSuggestions: () => get<Suggestion[]>("/suggestions/declined", () => declinedMock),
  why: (patternId: string) => get<WhyResponse>(`/suggestions/${patternId}/why`, () => (patternId === "pat_uc2" ? whyUc2Mock : whyMock)),
  acceptSuggestion: (patternId: string) =>
    post<{ ok: boolean; job_id?: string }>(`/suggestions/${patternId}/accept`, undefined, () => ({ ok: true, job_id: "job_mock_forge" })),
  declineSuggestion: (patternId: string, reason: string, neverForScope?: string) =>
    post<{ ok: boolean }>(`/suggestions/${patternId}/decline`, { reason, never_for_scope: neverForScope }, () => {
      mockState.hiddenPatterns.add(patternId);
      return { ok: true };
    }),
  snoozeSuggestion: (patternId: string) =>
    post<{ ok: boolean }>(`/suggestions/${patternId}/snooze`, undefined, () => {
      mockState.hiddenPatterns.add(patternId);
      return { ok: true };
    }),

  // Candidates (P2)
  candidate: (id: string) => get<Candidate>(`/candidates/${id}`, () => (id === "candidate_uc2" ? candidateUc2Mock : candidateMock)),
  approveCandidate: (id: string) =>
    post<{ tool_id: string }>(`/candidates/${id}/approve`, undefined, () => {
      if (id !== "candidate_uc2") return { tool_id: "tool_uc1" };
      mockState.promoted.add("tool_invoice");
      mockState.deletedTools.delete("tool_invoice");
      mockState.hiddenPatterns.add("pat_uc2");
      return { tool_id: "tool_invoice" };
    }),
  rejectCandidate: (id: string) => post<{ ok: boolean }>(`/candidates/${id}/reject`, undefined, () => ({ ok: true })),
  devForge: (pattern: unknown = patternMock) =>
    post<{ candidate_id: string }>("/dev/forge", { pattern }, () => ({ candidate_id: "candidate_fixture" })),

  // Tools (P1)
  tools: () =>
    get<ToolSummary[]>("/tools", () => {
      const invoice = mockState.promoted.has("tool_invoice") && !mockState.deletedTools.has("tool_invoice");
      const runs = mockState.runs.filter((r) => r.tool_id === "tool_invoice").length;
      const base = (toolsMock as ToolSummary[]).filter((t) => !mockState.deletedTools.has(t.tool_id));
      return invoice ? [{ ...(toolInvoiceMock as unknown as ToolSummary), runs }, ...base] : base;
    }),
  tool: (id: string) =>
    get<ToolDetail>(`/tools/${id}`, () => {
      if (id === "tool_invoice") return { ...toolInvoiceMock, runs: mockState.runs.filter((r) => r.tool_id === id).length };
      const summary = (toolsMock as ToolSummary[]).find((t) => t.tool_id === id);
      return { ...toolMock, ...summary, tool_id: id };
    }),
  lineage: (id: string) =>
    get<LineageTree>(`/tools/${id}/lineage`, () => ({ calls: [], merged_from: [], merged_into: null, dependents: [] })),
  versions: (id: string) =>
    get<ToolVersion[]>(`/tools/${id}/versions`, () => [id === "tool_invoice" ? toolInvoiceMock.version : toolMock.version]),
  rollback: (id: string, version: number) => post<{ ok: boolean }>(`/tools/${id}/rollback`, { version }, () => ({ ok: true })),
  runTool: (id: string, params: Record<string, unknown>, confirm = false) =>
    post<RunResult>(`/tools/${id}/run`, { params, confirm }, () => {
      if (id === "tool_invoice") return mockInvoiceRun(id, params, confirm);
      const result = {
        ...runResultMock,
        run_id: `run_mock_${mockState.runs.length + 1}`,
        tool_id: id,
        mode: confirm ? ("live" as const) : ("dry_run" as const),
        needs_confirm: !confirm,
        duration_ms: confirm ? 8200 : 640,
        tokens: 500,
        output: confirm ? { summary: "Dashboard written to outputs/dashboard.html", rows: 214 } : runResultMock.output,
      };
      if (confirm) {
        mockState.runs.unshift({
          tool_id: id,
          run_id: result.run_id,
          started_at: new Date().toISOString(),
          mode: "live",
          outcome: "success",
          status: "done",
          duration_ms: result.duration_ms,
          actions: [
            { kind: "file.write", payload: { path: "dashboard.html" }, description: "Wrote dashboard.html", receipt: { id: "dashboard.html" } },
            { kind: "slack.post", payload: { channel: "#sales" }, description: "Posted the dashboard link in #sales", receipt: { id: "msg1" } },
          ],
        });
      }
      return result;
    }),
  runByIntent: (intent: string, inputs: Record<string, unknown>) =>
    post<RunResult>("/run", { intent, inputs }, () => runResultMock),
  feedback: (id: string, body: { run_id?: string; verdict: "good" | "bad" | "edited"; note?: string }) =>
    post<{ ok: boolean }>(`/tools/${id}/feedback`, body, () => ({ ok: true })),

  // Race (P2)
  race: (intent: string, inputs: Record<string, unknown>) =>
    post<{ race_id: string }>("/race", { intent, inputs }, () => ({ race_id: "race_fixture" })),

  // Policy, jobs, metrics (P1)
  policy: () => get<PolicyDoc>("/policy", () => policyMock),
  approvePolicyChange: (id: string) => post<{ ok: boolean }>(`/policy/changes/${id}/approve`, undefined, () => ({ ok: true })),
  consolidate: () => post<{ job_id: string }>("/consolidate", undefined, () => ({ job_id: "job_mock_consolidate" })),
  prune: () => post<{ job_id: string }>("/prune", undefined, () => ({ job_id: "job_mock_prune" })),
  metrics: () => get<Metrics>("/metrics", () => metricsMock),

  // Concierge + ideas (P3)
  chat: async (message: string, conversationId?: string | null) => {
    const reply = await post<ChatReply>("/chat", { message, conversation_id: conversationId ?? null }, () =>
      /idea|automate|alert|every (day|morning|week)/i.test(message)
        ? {
            conversation_id: "conv_mock",
            reply: "No tool covers that yet. Here is a spec I could forge; say yes (or press Build) and I'll start.",
            tool_calls: [{ name: "analyze_idea", arguments: { text: message } }],
            cards: [{ kind: "idea", idea: { ...ideaNewMock, idea_id: "idea_mock_new" } }],
          }
        : chatReplyMock,
    );
    return { ...reply, cards: (reply.cards ?? []).map(normalizeCard).filter((c): c is ChatCard => c !== null) };
  },
  analyzeIdea: (text: string, confirm = false, ideaId?: string) =>
    post<IdeaAnalysis>("/ideas", { text, confirm, idea_id: ideaId }, () =>
      /dashboard|sales|weekly/i.test(text)
        ? { ...ideaCoveredMock, idea_id: "idea_mock_covered" }
        : { ...ideaNewMock, idea_id: "idea_mock_new", candidate_id: confirm ? "candidate_fixture" : undefined },
    ),

  // Approval-first automation (P3 connectors + plan; P1 approvals, run undo, tool delete)
  automationPlan: (signature: string[], estMinutesSavedWeek?: number) =>
    post<AutomationPlan>("/automation/plan", { signature, est_minutes_saved_week: estMinutesSavedWeek }, () =>
      mockPlan(signature, estMinutesSavedWeek ?? 0),
    ),
  connectors: () =>
    get<Connector[]>("/connectors", () =>
      MOCK_CONNECTORS.map(([app, name, scopes]) => ({
        app,
        name,
        available_scopes: scopes,
        status: mockState.connected.has(app) ? "connected" : "not_connected",
        scopes: mockState.connected.has(app) ? scopes : [],
        connected_at: mockState.connected.has(app) ? new Date().toISOString() : null,
      })),
    ),
  connect: (app: string, scopes?: string[]) =>
    post<{ consent_url: string }>(`/connectors/${app}/connect`, { scopes }, () => {
      // mock: the real consent page on the mock site, redirecting back to this app's /connectors
      const query = new URLSearchParams({
        app,
        scopes: (scopes ?? []).join(","),
        state: `mock_${app}`,
        redirect_uri: `${window.location.origin}/connectors`,
      });
      return { consent_url: `${MOCKSITE_PUBLIC}/oauth/authorize?${query}` };
    }),
  revokeConnector: (app: string) =>
    post<{ app: string; status: string }>(`/connectors/${app}/revoke`, undefined, () => {
      mockState.connected.delete(app);
      return { app, status: "revoked" };
    }),
  approvals: () => get<Approval[]>("/approvals", () => mockState.approvals),
  decideApproval: (runId: string, decision: "approve" | "reject", note?: string) =>
    post<{ ok: boolean; executed?: number }>(`/approvals/${runId}`, { decision, note }, () => {
      mockState.approvals = mockState.approvals.filter((a) => a.run_id !== runId);
      const run = mockState.runs.find((r) => r.run_id === runId);
      let executed = 0;
      for (const item of run?.actions ?? []) {
        if (item.status !== "pending") continue;
        if (decision === "approve") {
          Object.assign(item, { status: "done", receipt: { id: `${item.kind}_${runId}` } });
          executed += 1;
        } else item.status = "rejected";
      }
      if (run) run.status = decision === "approve" ? "done" : "rejected";
      return { ok: true, executed };
    }),
  toolRuns: (toolId: string) => get<RunSummary[]>(`/tools/${toolId}/runs`, () => mockState.runs.filter((r) => r.tool_id === toolId)),
  revertRun: (runId: string) =>
    post<{ ok: boolean; undone: number }>(`/runs/${runId}/revert`, undefined, () => {
      const run = mockState.runs.find((r) => r.run_id === runId);
      let undone = 0;
      for (const item of run?.actions ?? []) {
        if (item.status === "done") {
          item.status = "undone";
          undone += 1;
        } else if (item.status === "pending") item.status = "cancelled";
      }
      mockState.approvals = mockState.approvals.filter((a) => a.run_id !== runId);
      if (run) run.status = "reverted";
      return { ok: true, undone };
    }),
  deleteTool: (toolId: string, neverSuggestAgain = false) =>
    post<{ ok: boolean; blocked_reason?: string }>(`/tools/${toolId}/delete`, { never_suggest_again: neverSuggestAgain }, () => {
      const waiting = mockState.approvals.filter((a) => a.tool_id === toolId).length;
      if (waiting) return { ok: false, blocked_reason: `${waiting} run(s) are waiting for approval` };
      mockState.deletedTools.add(toolId);
      mockState.promoted.delete(toolId);
      mockState.deletedAt = new Date().toISOString();
      if (toolId === "tool_invoice") {
        if (neverSuggestAgain) mockState.hiddenPatterns.add("pat_uc2");
        else mockState.hiddenPatterns.delete("pat_uc2"); // it's still repeating: suggest again
      }
      return { ok: true };
    }),
  closeCaptureSession: () =>
    post<{ ok: boolean; sessions_closed: number }>("/capture/sessions/close", undefined, () => ({ ok: true, sessions_closed: 1 })),

  // Demo controls (P3)
  loadDemoHistory: () => post<{ ok: boolean; log?: string }>("/demo/history", undefined, () => ({ ok: true })),
  mocksiteState: () => get<{ active: "v1" | "v2" }>("/demo/mocksite", () => ({ active: mockState.mocksite })),
  switchMocksite: (layout: "v1" | "v2") =>
    post<{ active: "v1" | "v2" }>(`/demo/mocksite/${layout}`, undefined, () => ((mockState.mocksite = layout), { active: layout })),
};

export type Api = typeof api;

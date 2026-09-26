// Typed client for every endpoint in task board §3.4.
// Mock mode (NEXT_PUBLIC_USE_MOCKS=true, or the sidebar switch which overrides it per browser)
// serves web/mocks/*.json and records each call in `mockLog`, so pages can be built without a backend.
import type {
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
import chatReplyMock from "@/mocks/chat_reply.json";
import declinedMock from "@/mocks/declined.json";
import ideaCoveredMock from "@/mocks/idea_covered.json";
import ideaNewMock from "@/mocks/idea_new.json";
import metricsMock from "@/mocks/metrics.json";
import patternMock from "@/mocks/pattern_uc1.json";
import policyMock from "@/mocks/policy.json";
import runResultMock from "@/mocks/run_result.json";
import suggestionsMock from "@/mocks/suggestions.json";
import toolMock from "@/mocks/tool_uc1.json";
import toolsMock from "@/mocks/tools.json";
import whyMock from "@/mocks/why_uc1.json";

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
    return clone<T>(mock());
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
  approvals: [
    {
      run_id: "run_inv_2202",
      tool_id: "tool_invoice",
      tool_title: "Invoice check and notify",
      created_at: "2026-09-26T15:58:00Z",
      summary: "INV-2202 · Acme Packaging · qty over PO on AC-14 (165 vs 150)",
      actions: [
        {
          kind: "slack.post",
          payload: { channel: "#warehouse", text: "INV-2202: AC-14 billed 165, PO-4102 ordered 150" },
          description: "Post in #warehouse: INV-2202: AC-14 billed 165, PO-4102 ordered 150",
          needs_approval: true,
        },
        {
          kind: "jira.create",
          payload: { summary: "INV-2202 quantity mismatch (AC-14)" },
          description: "Open Jira ticket: INV-2202 quantity mismatch (AC-14)",
          needs_approval: true,
        },
      ],
    },
  ] as Approval[],
  runs: [] as RunSummary[],
  deletedTools: new Set<string>(),
};

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
  if (isMockMode()) return "/mock-frame.webp";
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
  suggestions: () => get<Suggestion[]>("/suggestions", () => suggestionsMock),
  declinedSuggestions: () => get<Suggestion[]>("/suggestions/declined", () => declinedMock),
  why: (patternId: string) => get<WhyResponse>(`/suggestions/${patternId}/why`, () => whyMock),
  acceptSuggestion: (patternId: string) =>
    post<{ ok: boolean; job_id?: string }>(`/suggestions/${patternId}/accept`, undefined, () => ({ ok: true, job_id: "job_mock_forge" })),
  declineSuggestion: (patternId: string, reason: string, neverForScope?: string) =>
    post<{ ok: boolean }>(`/suggestions/${patternId}/decline`, { reason, never_for_scope: neverForScope }, () => ({ ok: true })),
  snoozeSuggestion: (patternId: string) => post<{ ok: boolean }>(`/suggestions/${patternId}/snooze`, undefined, () => ({ ok: true })),

  // Candidates (P2)
  candidate: (id: string) => get<Candidate>(`/candidates/${id}`, () => candidateMock),
  approveCandidate: (id: string) => post<{ tool_id: string }>(`/candidates/${id}/approve`, undefined, () => ({ tool_id: "tool_uc1" })),
  rejectCandidate: (id: string) => post<{ ok: boolean }>(`/candidates/${id}/reject`, undefined, () => ({ ok: true })),
  devForge: (pattern: unknown = patternMock) =>
    post<{ candidate_id: string }>("/dev/forge", { pattern }, () => ({ candidate_id: "candidate_fixture" })),

  // Tools (P1)
  tools: () => get<ToolSummary[]>("/tools", () => toolsMock),
  tool: (id: string) =>
    get<ToolDetail>(`/tools/${id}`, () => {
      const summary = (toolsMock as ToolSummary[]).find((t) => t.tool_id === id);
      return { ...toolMock, ...summary, tool_id: id };
    }),
  lineage: (id: string) =>
    get<LineageTree>(`/tools/${id}/lineage`, () => ({ calls: [], merged_from: [], merged_into: null, dependents: [] })),
  versions: (id: string) => get<ToolVersion[]>(`/tools/${id}/versions`, () => [toolMock.version]),
  rollback: (id: string, version: number) => post<{ ok: boolean }>(`/tools/${id}/rollback`, { version }, () => ({ ok: true })),
  runTool: (id: string, params: Record<string, unknown>, confirm = false) =>
    post<RunResult>(`/tools/${id}/run`, { params, confirm }, () => {
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
      mockState.connected.add(app); // mock: consent is granted at once
      return { consent_url: "" };
    }),
  revokeConnector: (app: string) =>
    post<{ app: string; status: string }>(`/connectors/${app}/revoke`, undefined, () => {
      mockState.connected.delete(app);
      return { app, status: "revoked" };
    }),
  approvals: () => get<Approval[]>("/approvals", () => mockState.approvals),
  decideApproval: (runId: string, decision: "approve" | "reject", note?: string) =>
    post<{ ok: boolean; executed?: number }>(`/approvals/${runId}`, { decision, note }, () => {
      const item = mockState.approvals.find((a) => a.run_id === runId);
      mockState.approvals = mockState.approvals.filter((a) => a.run_id !== runId);
      return { ok: true, executed: decision === "approve" ? (item?.actions.length ?? 0) : 0 };
    }),
  toolRuns: (toolId: string) => get<RunSummary[]>(`/tools/${toolId}/runs`, () => mockState.runs),
  revertRun: (runId: string) =>
    post<{ ok: boolean; undone: number }>(`/runs/${runId}/revert`, undefined, () => {
      const run = mockState.runs.find((r) => r.run_id === runId);
      if (run) run.status = "reverted";
      return { ok: true, undone: run?.actions.length ?? 0 };
    }),
  deleteTool: (toolId: string, neverSuggestAgain = false) =>
    post<{ ok: boolean; blocked_reason?: string }>(`/tools/${toolId}/delete`, { never_suggest_again: neverSuggestAgain }, () => {
      mockState.deletedTools.add(toolId);
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

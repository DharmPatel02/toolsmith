// Typed client for every endpoint in task board §3.4.
// Mock mode (NEXT_PUBLIC_USE_MOCKS=true, or the sidebar switch which overrides it per browser)
// serves web/mocks/*.json and records each call in `mockLog`, so pages can be built without a backend.
import type {
  CaptureSession,
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

// Mock-only state so the demo flow (accept → forge → approve, pause, layout switch) behaves plausibly.
const mockState = { paused: false, mocksite: "v1" as "v1" | "v2" };

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
    post<RunResult>(`/tools/${id}/run`, { params, confirm }, () => ({
      ...runResultMock,
      tool_id: id,
      mode: confirm ? "live" : "dry_run",
      needs_confirm: !confirm,
      duration_ms: confirm ? 8200 : 640,
      tokens: 500,
      output: confirm ? { summary: "Dashboard written to outputs/dashboard.html", rows: 214 } : runResultMock.output,
    })),
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

  // Demo controls (P3)
  mocksiteState: () => get<{ active: "v1" | "v2" }>("/demo/mocksite", () => ({ active: mockState.mocksite })),
  switchMocksite: (layout: "v1" | "v2") =>
    post<{ active: "v1" | "v2" }>(`/demo/mocksite/${layout}`, undefined, () => ((mockState.mocksite = layout), { active: layout })),
};

export type Api = typeof api;

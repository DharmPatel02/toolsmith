// Wire types mirroring backend/app/contracts.py (task board §3). Keep in sync with P1's contracts.

export type Trust = "dry_run" | "supervised" | "autonomous";
export type Tier = "T0" | "T1" | "T2";
export type ExecutionPath = "api" | "browser" | "cli" | "assisted";

export interface Derivation {
  observed_tier: Tier;
  execution_path: ExecutionPath;
}

export interface Requires {
  scopes: string[];
  deps: string[];
  tools: string[];
}

export interface JsonSchemaProp {
  type?: string;
  description?: string;
  enum?: string[];
  default?: unknown;
  format?: string;
}

export interface ParamsSchema {
  type: "object";
  properties: Record<string, JsonSchemaProp>;
  required?: string[];
}

export interface ToolSpec {
  name: string;
  purpose: string;
  params_schema: ParamsSchema;
  outputs: Record<string, unknown>;
  requires: Requires;
  keywords: string[];
  derivation: Derivation;
  not_automatable: Record<string, string> | null;
}

export interface ToolSummary {
  tool_id: string;
  name: string;
  title: string;
  status: string;
  trust: Trust;
  runs: number;
  success_rate: number;
  p50_ms: number;
  minutes_saved: number;
}

export interface Lineage {
  calls: string[];
  parents: string[];
  merged_from: string[];
  merged_into: string | null;
}

export interface ToolVersion {
  tool_id: string;
  version: number;
  code: string;
  params_schema: ParamsSchema;
  tests: string;
  fixtures_ref: string[];
  tutorial_md: string;
  requires: Requires;
  derivation: Derivation;
  created_from: Record<string, string>;
  approved_at: string | null;
}

export interface ToolDetail extends ToolSummary {
  baseline_minutes?: number; // minutes the task took by hand, when known
  race_intent?: string; // when a baseline-vs-tool race is available
  user_id: string;
  tier: "lean" | "heavy";
  active_version: number;
  lineage: Lineage;
  version: ToolVersion;
}

export interface LineageTree {
  calls: { tool_id: string; name: string; depth: number }[];
  merged_from: string[];
  merged_into: string | null;
  dependents: string[];
}

export interface DynamicParam {
  name: string;
  type: string;
}

export interface Suggestion {
  pattern_id: string;
  title: string;
  reason: string;
  support: number;
  distinct_days: number;
  est_minutes_saved_week: number;
  value: number;
  signature: string[];
  dynamic_params: DynamicParam[];
  declined_reason?: string;
  deleted_at?: string | null; // set when the user deleted the tool built from this pattern
  deleted_tool_id?: string | null;
}

export interface EpisodeHit {
  session_id: string;
  date: string;
  intent_summary: string;
  minutes: number;
  tokens: number;
  score: number;
}

export interface FrameEvidence {
  frame_id: string;
  ts: string;
  thumb_url: string;
  verb: string;
}

export interface WhyResponse {
  episodes: EpisodeHit[];
  frames: FrameEvidence[];
}

export interface Verdict {
  _id: string;
  tool_id: string | null;
  candidate_version: number;
  checks: Record<string, boolean>;
  decision: "passed" | "failed";
  reason: string;
}

export interface Candidate {
  _id: string;
  user_id: string;
  pattern_id: string | null;
  idea_id: string | null;
  spec: ToolSpec;
  code: string;
  tests: string;
  tutorial_md: string;
  params_schema: ParamsSchema;
  requires: Requires;
  derivation: Derivation;
  verdict_id: string | null;
  verdict: Verdict | null;
  status: "gating" | "passed" | "failed" | "approved" | "rejected";
  created_at: string;
}

export interface Write {
  path: string;
  kind: string; // file extension, or "action:<app>.<verb>"
  bytes?: number | null;
  payload?: Record<string, unknown> | null;
}

export interface RunResult {
  run_id: string;
  mode: "dry_run" | "live";
  output: Record<string, unknown>;
  intended_writes: Write[];
  needs_confirm: boolean;
  duration_ms: number;
  tokens: number;
  route?: "found" | "related" | "not_found" | null;
  tool_id?: string | null;
  score?: number | null;
  status?: "preview" | "done" | "awaiting_approval" | "failed" | null;
  actions?: ActionItem[];
}

export interface PolicyChange {
  id: string;
  field: string;
  from: unknown;
  to: unknown;
  direction: "tighten" | "loosen";
  because: string;
  origin_feedback_ids?: string[];
  status: "applied" | "pending";
}

export interface PolicyDoc {
  _id: string;
  version: number;
  thresholds: Record<string, unknown>;
  rules: Record<string, unknown>[];
  changes: PolicyChange[];
}

export interface Metrics {
  minutes_saved_week: number;
  tokens: Record<string, number>;
  break_even_runs: number | null;
  replay_pass_rate: number;
  time_to_heal_seconds: number | null;
  decoy_false_positive_rate: number;
  toolbox_count: number;
  ablation: Record<string, Record<string, number>>;
  capture_quality: Record<string, number>;
  cost_to_observe_usd_day: number;
  race: Record<string, Record<string, number>>;
  detection?: Record<string, number>; // precision, recall, f1
  repair_loops?: number;
  toolbox_size_over_time?: Record<string, string | number>[]; // e.g. {date, size}
}

export type ChatCard =
  | { kind: "tool"; tool: ToolSummary }
  | { kind: "suggestion"; suggestion: Suggestion }
  | { kind: "episodes"; episodes: EpisodeHit[] }
  | { kind: "run"; run: RunResult }
  | { kind: "idea"; idea: IdeaAnalysis }
  | { kind: "tool_hits"; hits: { tool_id: string; name: string; score: number }[] }
  | { kind: "feedback"; feedback: { tool_id?: string; pattern_id?: string; decision: string; reason?: string } }
  | { kind: "policy"; change: { id: string; field?: string; value?: unknown } };

export interface ChatReply {
  conversation_id: string;
  reply: string;
  tool_calls: Record<string, unknown>[];
  cards: ChatCard[];
}

export interface IdeaAnalysis {
  covered_by_tool_id: string | null;
  feasible: boolean;
  scopes: string[];
  deps: string[];
  est_minutes_saved_week: number;
  spec: ToolSpec | null;
  // P3 additions from POST /ideas
  idea_id?: string;
  candidate_id?: string;
  related_tool_id?: string;
  reason?: string;
  title?: string;
}

export interface CaptureState {
  paused: boolean;
  allowed_origins: string[];
}

export interface CaptureSession {
  _id?: string;
  started_at: string;
  ended_at: string | null;
  sources: string[];
  apps_seen: string[];
  frames_kept: number;
  frames_dropped_by_rule: Record<string, number>;
  paused: boolean;
}

export const EVENT_TYPES = [
  "suggestion_new",
  "forge_started",
  "forged",
  "gate_passed",
  "gate_failed",
  "promoted",
  "run_completed",
  "trust_changed",
  "drift_detected",
  "healed",
  "pruned",
  "policy_changed",
  "frame_labeled",
  "capture_paused",
  "race_step",
] as const;

export type EventType = (typeof EVENT_TYPES)[number];

export interface ToolsmithEvent<T = Record<string, unknown>> {
  type: EventType;
  ts: string;
  data: T;
}

export interface RaceStep {
  race_id: string;
  side: "baseline" | "tool";
  step: number;
  label: string;
  tokens: number;
  elapsed_ms: number;
  done: boolean;
}

// ---- Approval-first automation (plan: connectors, intended actions, approvals, undo) ----

export type Automation = "auto" | "approval" | "manual";

export interface PlanStep {
  step: string;
  label: string;
  automation: Automation;
  connector: string | null;
}

export interface PlanPermission {
  connector: string;
  scopes: string[];
  granted: boolean;
}

export interface AutomationPlan {
  steps: PlanStep[];
  permissions: PlanPermission[];
  counts: Record<Automation, number>;
  est_minutes_saved_week: number;
}

export interface Connector {
  app: string;
  name: string;
  available_scopes: string[];
  status: "connected" | "revoked" | "not_connected";
  scopes: string[];
  connected_at: string | null;
}

export interface ActionItem {
  kind: string;
  payload: Record<string, unknown>;
  description?: string;
  needs_approval?: boolean;
  status?: "pending" | "done" | "failed" | "rejected" | "undone" | "cancelled";
  receipt?: Record<string, unknown> | null;
  error?: string | null;
}

export interface Approval {
  run_id: string;
  tool_id: string;
  tool_title?: string;
  created_at: string;
  summary?: string;
  actions: ActionItem[];
}

export interface RunSummary {
  run_id: string;
  started_at: string;
  mode: "dry_run" | "live";
  outcome: string;
  status?: "done" | "awaiting_approval" | "reverted" | "rejected";
  duration_ms: number;
  actions: ActionItem[];
}

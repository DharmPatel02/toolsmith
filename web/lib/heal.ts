// Heal timeline reducer (P3.3.3): drift -> patch forged -> gated -> promoted, per tool.
import type { ToolsmithEvent } from "./types";

export const HEAL_STAGES = ["drift", "patch", "gate", "promoted"] as const;
export type Stage = (typeof HEAL_STAGES)[number];

export interface Heal {
  toolId: string;
  name: string;
  candidateId?: string;
  stages: Partial<Record<Stage, { ts: string; ok: boolean; note?: string }>>;
  timeToHealMs?: number;
  failed?: string;
}

/** Folds heal-related events into one timeline per tool. Pure, so it's easy to reason about. */
export function healReducer(heals: Heal[], e: ToolsmithEvent): Heal[] {
  const d = e.data as Record<string, unknown>;
  const toolId = d.tool_id as string | undefined;
  const byCandidate = heals.find((h) => h.candidateId && h.candidateId === d.candidate_id);
  const current = byCandidate ?? heals.find((h) => h.toolId === toolId && !h.stages.promoted && !h.failed);
  const set = (h: Heal, stage: Stage, ok: boolean, note?: string): Heal => ({
    ...h,
    stages: { ...h.stages, [stage]: { ts: e.ts, ok, note } },
  });
  const replace = (h: Heal) => (current ? heals.map((x) => (x === current ? h : x)) : [h, ...heals]);

  switch (e.type) {
    case "drift_detected":
      if (!toolId) return heals;
      return [set({ toolId, name: (d.name as string) ?? toolId, stages: {} }, "drift", false, (d.reason as string) ?? "outputs stopped matching"), ...heals];
    case "forged":
      if (d.kind !== "heal" || !current) return heals;
      return replace(set({ ...current, candidateId: d.candidate_id as string }, "patch", true, d.diagnosis as string));
    case "gate_passed":
    case "gate_failed":
      if (!byCandidate) return heals;
      return replace(set(byCandidate, "gate", e.type === "gate_passed", d.reason as string));
    case "healed":
      if (!current) return heals;
      return replace({ ...set(current, "promoted", true, `v${d.version} at ${d.trust ?? "dry_run"}`), timeToHealMs: d.time_to_heal_ms as number });
    default:
      return heals;
  }
}


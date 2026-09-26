"use client";
// Live forge stepper (P3.2.1): spec → code → tests → replay → tutorial, driven by SSE.
// Events: forge_started, forged (may repeat per stage), gate_passed / gate_failed. If an event carries
// `data.stage`, the stepper jumps to it; otherwise each event advances one step.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Check, Loader2, X } from "lucide-react";
import { toast } from "sonner";

import { Button, buttonVariants } from "@/components/ui/button";
import { api, isMockMode } from "@/lib/api";
import type { ToolsmithEvent } from "@/lib/types";
import { replayMock, useEvents } from "@/lib/useEvents";
import { cn } from "@/lib/utils";

export const FORGE_STEPS = ["spec", "code", "tests", "replay", "tutorial"] as const;

export type ForgeStatus = "running" | "passed" | "failed";

export interface ForgeState {
  step: number; // index of the step in progress; FORGE_STEPS.length when all done
  status: ForgeStatus;
  candidateId: string | null;
  reason?: string;
}

/** Pure reducer so the stepper logic is testable without a browser. */
export function forgeReducer(state: ForgeState, event: ToolsmithEvent): ForgeState {
  const data = event.data as { candidate_id?: string; stage?: string; reason?: string };
  const candidateId = data.candidate_id ?? state.candidateId;
  const stageIndex = data.stage ? FORGE_STEPS.indexOf(data.stage as (typeof FORGE_STEPS)[number]) : -1;
  switch (event.type) {
    case "forge_started":
      return { step: Math.max(stageIndex, 0), status: "running", candidateId };
    case "forged":
      // P2 publishes `forged` with status "failed" when the forge itself fails (no gate follows).
      if ((event.data as { status?: string }).status === "failed")
        return { ...state, candidateId, status: "failed", reason: "forge failed before the gate" };
      return { ...state, candidateId, step: stageIndex >= 0 ? stageIndex + 1 : Math.min(state.step + 1, 3) };
    case "gate_passed":
      return { step: FORGE_STEPS.length, status: "passed", candidateId };
    case "gate_failed":
      return { ...state, step: Math.max(state.step, 3), status: "failed", candidateId, reason: data.reason };
    default:
      return state;
  }
}

export function ForgeProgress({ patternId, onDone }: { patternId: string; onDone?: () => void }) {
  const [state, setState] = useState<ForgeState>({ step: 0, status: "running", candidateId: null });
  const [busy, setBusy] = useState(false);
  const router = useRouter();

  useEvents(
    (event) => {
      const data = event.data as { pattern_id?: string; candidate_id?: string };
      // Follow events for this pattern, or for the candidate we already know about.
      const mine = data.pattern_id === patternId || (!!state.candidateId && data.candidate_id === state.candidateId) || (!data.pattern_id && !state.candidateId);
      if (mine) setState((s) => forgeReducer(s, event));
    },
    ["forge_started", "forged", "gate_passed", "gate_failed"],
  );

  useEffect(() => {
    if (!isMockMode()) return;
    const cid = patternId === "pat_uc2" ? "candidate_uc2" : "candidate_fixture";
    return replayMock(
      [
        { type: "forge_started", ts: "", data: { pattern_id: patternId, candidate_id: cid, stage: "spec" } },
        { type: "forged", ts: "", data: { candidate_id: cid, stage: "code" } },
        { type: "forged", ts: "", data: { candidate_id: cid, stage: "tests" } },
        { type: "forged", ts: "", data: { candidate_id: cid, stage: "replay" } },
        { type: "gate_passed", ts: "", data: { candidate_id: cid } },
      ],
      900,
    );
  }, [patternId]);

  const decide = async (approve: boolean) => {
    if (!state.candidateId) return;
    setBusy(true);
    try {
      if (approve) {
        const { tool_id } = await api.approveCandidate(state.candidateId);
        toast.success("Tool created: it starts in dry-run mode", { description: "Opening its one-page tutorial…" });
        router.push(`/tools/${tool_id}`);
      } else {
        await api.rejectCandidate(state.candidateId);
        toast("Candidate rejected");
      }
      onDone?.();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-lg border bg-muted/30 p-3">
      <ol className="flex items-center gap-1 text-xs">
        {FORGE_STEPS.map((name, i) => {
          const done = i < state.step || state.status === "passed";
          const active = i === state.step && state.status === "running";
          const failed = state.status === "failed" && i === state.step;
          return (
            <li key={name} className="flex flex-1 items-center gap-1">
              <span
                className={cn(
                  "flex size-5 shrink-0 items-center justify-center rounded-full border text-[10px]",
                  done && "border-emerald-500 bg-emerald-500 text-white",
                  active && "border-primary",
                  failed && "border-red-500 bg-red-500 text-white",
                )}
              >
                {done ? <Check className="size-3" /> : failed ? <X className="size-3" /> : active ? <Loader2 className="size-3 animate-spin" /> : i + 1}
              </span>
              <span className={cn("truncate", (done || active) && "text-foreground", !done && !active && "text-muted-foreground")}>{name}</span>
              {i < FORGE_STEPS.length - 1 && <span className="mx-1 h-px flex-1 bg-border" />}
            </li>
          );
        })}
      </ol>
      <div className="mt-3 flex items-center justify-between gap-2 text-sm">
        <span className="text-muted-foreground">
          {state.status === "running" && "Forging and gating in the sandbox…"}
          {state.status === "passed" && "Gate passed: unit, replay, side-effect and dedupe checks are green."}
          {state.status === "failed" && `Gate failed${state.reason ? `: ${state.reason}` : ""}`}
        </span>
        {state.candidateId && (
          <div className="flex shrink-0 gap-2">
            <Link href={`/candidates/${state.candidateId}`} className={buttonVariants({ variant: "outline", size: "sm" })}>
              Review
            </Link>
            {state.status === "passed" && (
              <>
                <Button size="sm" variant="ghost" disabled={busy} onClick={() => decide(false)}>
                  Reject
                </Button>
                <Button size="sm" disabled={busy} onClick={() => decide(true)}>
                  Approve
                </Button>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

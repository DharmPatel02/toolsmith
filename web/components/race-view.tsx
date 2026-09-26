"use client";
// Split-screen race (P3.3.7): same request, baseline agent solving from scratch (left) vs the forged
// tool (right: FOUND -> working_memory -> result). Both sides stream `race_step` over SSE and the
// view freezes on the final steps / seconds / tokens once both report done.
import { useEffect, useRef, useState } from "react";
import { Bot, Flag, Loader2, Wrench } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { api, isMockMode } from "@/lib/api";
import { fmtMs, fmtTokens } from "@/lib/format";
import type { RaceStep } from "@/lib/types";
import { replayMock, useEvents } from "@/lib/useEvents";
import { cn } from "@/lib/utils";

type Side = "baseline" | "tool";
type Lane = { steps: RaceStep[]; done: boolean };
const EMPTY: Record<Side, Lane> = { baseline: { steps: [], done: false }, tool: { steps: [], done: false } };

export function raceReducer(lanes: Record<Side, Lane>, step: RaceStep): Record<Side, Lane> {
  const lane = lanes[step.side];
  if (!lane || lane.done) return lanes;
  const steps = [...lane.steps.filter((s) => s.step !== step.step), step].sort((a, b) => a.step - b.step);
  return { ...lanes, [step.side]: { steps, done: step.done } };
}

export function RaceView({ intent, inputs }: { intent: string; inputs: Record<string, unknown> }) {
  const [raceId, setRaceId] = useState<string | null>(null);
  const [lanes, setLanes] = useState(EMPTY);
  const [starting, setStarting] = useState(false);
  const cancelReplay = useRef<(() => void) | null>(null);

  useEvents(
    (e) => {
      const step = e.data as unknown as RaceStep;
      if (raceId && step.race_id === raceId) setLanes((l) => raceReducer(l, step));
    },
    ["race_step"],
  );

  useEffect(() => () => cancelReplay.current?.(), []);

  const start = async () => {
    setStarting(true);
    setLanes(EMPTY);
    cancelReplay.current?.();
    try {
      const { race_id } = await api.race(intent, inputs);
      setRaceId(race_id);
      if (isMockMode()) cancelReplay.current = replayMock("race", 500);
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setStarting(false);
    }
  };

  const finished = lanes.baseline.done && lanes.tool.done;
  const running = !!raceId && !finished;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={start} disabled={starting || running} variant="outline">
          {running ? <Loader2 className="animate-spin" /> : <Flag />}
          {running ? "Racing…" : raceId ? "Race again" : "Race: agent from scratch vs this tool"}
        </Button>
        <span className="text-xs text-muted-foreground">
          Same request: “{intent}” on {Object.values(inputs).join(", ")}
        </span>
      </div>
      {raceId && (
        <div className="grid gap-3 md:grid-cols-2">
          <LaneView title="Baseline agent" subtitle="solving from scratch" icon={<Bot className="size-4" />} lane={lanes.baseline} />
          <LaneView title="ToolSmith" subtitle="hybrid search → working memory → tool" icon={<Wrench className="size-4" />} lane={lanes.tool} accent />
        </div>
      )}
      {finished && <Verdict baseline={lanes.baseline} tool={lanes.tool} />}
    </div>
  );
}

function totals(lane: Lane) {
  const last = lane.steps.at(-1);
  return { steps: lane.steps.length, ms: last?.elapsed_ms ?? 0, tokens: last?.tokens ?? 0 };
}

function LaneView({ title, subtitle, icon, lane, accent }: { title: string; subtitle: string; icon: React.ReactNode; lane: Lane; accent?: boolean }) {
  const t = totals(lane);
  const list = useRef<HTMLOListElement>(null);
  useEffect(() => {
    list.current?.lastElementChild?.scrollIntoView({ block: "nearest" });
  }, [lane.steps.length]);
  return (
    <div className={cn("flex flex-col rounded-lg border", accent && "border-[color:var(--series-1)]")}>
      <div className="flex items-center gap-2 border-b px-3 py-2">
        {icon}
        <div className="flex-1">
          <div className="text-sm font-medium">{title}</div>
          <div className="text-xs text-muted-foreground">{subtitle}</div>
        </div>
        {!lane.done && <Loader2 className="size-3.5 animate-spin text-muted-foreground" />}
      </div>
      <div className="grid grid-cols-3 border-b text-center">
        <Counter label="steps" value={t.steps} />
        <Counter label="time" value={fmtMs(t.ms)} />
        <Counter label="tokens" value={fmtTokens(t.tokens)} />
      </div>
      <ol ref={list} className="h-44 overflow-y-auto px-3 py-2 font-mono text-xs">
        {lane.steps.map((s) => (
          <li key={s.step} className="flex gap-2 py-0.5">
            <span className="w-5 shrink-0 text-right text-muted-foreground">{s.step}</span>
            <span className={cn("flex-1", s.done && "font-semibold")}>{s.label}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

function Counter({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="px-2 py-2">
      <div className="text-lg font-semibold tabular-nums">{value}</div>
      <div className="text-[11px] text-muted-foreground">{label}</div>
    </div>
  );
}

function Verdict({ baseline, tool }: { baseline: Lane; tool: Lane }) {
  const b = totals(baseline);
  const t = totals(tool);
  const x = (a: number, c: number) => (c > 0 ? `${Math.round(a / c)}×` : "—");
  return (
    <div className="rounded-lg border bg-muted/40 px-4 py-3 text-sm">
      <span className="font-medium">Final:</span> {b.steps} → {t.steps} steps · {fmtMs(b.ms)} → {fmtMs(t.ms)} ({x(b.ms, t.ms)} faster) ·{" "}
      {fmtTokens(b.tokens)} → {fmtTokens(t.tokens)} tokens ({x(b.tokens, t.tokens)} fewer)
    </div>
  );
}

"use client";
// Demo controls (P3.3.3): mock-site layout switch, consolidation, prune, and the heal timeline
// (drift -> patch forged -> gated -> promoted, with time-to-heal) built from SSE.
import { useEffect, useRef, useState } from "react";
import { Check, Circle, Loader2, X } from "lucide-react";
import { toast } from "sonner";

import { ErrorState, PageHeader } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api, isMockMode, resetMockState } from "@/lib/api";
import { fmtMs, fmtTime } from "@/lib/format";
import type { ToolsmithEvent } from "@/lib/types";
import { HEAL_STAGES, healReducer, type Heal, type Stage } from "@/lib/heal";
import { replayMock, useEvents } from "@/lib/useEvents";
import { useApi } from "@/lib/useApi";
import { cn } from "@/lib/utils";

const MOCK_HEAL: ToolsmithEvent[] = [
  { type: "drift_detected", ts: "", data: { tool_id: "tool_uc3", name: "competitor_price_sweep", reason: "3 failed runs: no products found on the page" } },
  { type: "forge_started", ts: "", data: { tool_id: "tool_uc3", kind: "heal" } },
  { type: "forged", ts: "", data: { tool_id: "tool_uc3", kind: "heal", candidate_id: "cand_heal", diagnosis: "selectors changed: li.product → article.item-card, .price → .item-price" } },
  { type: "gate_passed", ts: "", data: { candidate_id: "cand_heal", reason: "old v1 fixture and new v2 page both pass" } },
  { type: "healed", ts: "", data: { tool_id: "tool_uc3", name: "competitor_price_sweep", version: 2, trust: "dry_run", time_to_heal_ms: 38200 } },
];

export default function DemoPage() {
  const site = useApi(() => api.mocksiteState());
  const [busy, setBusy] = useState<string | null>(null);
  const [heals, setHeals] = useState<Heal[]>([]);
  const cancel = useRef<(() => void) | null>(null);

  useEvents((e) => setHeals((h) => healReducer(h, e)), ["drift_detected", "forged", "gate_passed", "gate_failed", "healed"]);
  useEffect(() => () => cancel.current?.(), []);

  const act = async (key: string, fn: () => Promise<unknown>, ok: string) => {
    setBusy(key);
    try {
      await fn();
      toast.success(ok);
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const switchSite = (layout: "v1" | "v2") =>
    act(
      `site-${layout}`,
      async () => {
        await api.switchMocksite(layout);
        site.reload();
        if (layout === "v2" && isMockMode()) cancel.current = replayMock(MOCK_HEAL, 1200);
      },
      `Mock site is now ${layout}${layout === "v2" ? ": the scraper will drift on its next run" : ""}`,
    );

  return (
    <>
      <PageHeader
        title="Demo controls"
        description="Levers for the live demo. Every action here is a real API call."
        actions={
          isMockMode() && (
            <Button
              variant="outline"
              onClick={() => {
                resetMockState();
                // full reload on purpose: it re-creates the in-memory demo state
                // eslint-disable-next-line @next/next/no-location-assign-relative-destination
                window.location.href = "/onboarding";
              }}
            >
              Restart demo story
            </Button>
          )
        }
      />
      <div className="grid gap-6 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Mock site layout</CardTitle>
            <CardDescription>PriceWatch on :8081. v2 renames classes and moves the price.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {site.error ? <ErrorState error={site.error} onRetry={site.reload} /> : (
              <div className="text-sm">
                Active: <Badge variant="secondary">{site.data?.active ?? "…"}</Badge>
              </div>
            )}
            <div className="flex gap-2">
              <Button variant="outline" disabled={!!busy || site.data?.active === "v1"} onClick={() => switchSite("v1")}>
                Switch to v1
              </Button>
              <Button disabled={!!busy || site.data?.active === "v2"} onClick={() => switchSite("v2")}>
                Switch to v2
              </Button>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Consolidation</CardTitle>
            <CardDescription>Summarize closed sessions, promote repeated facts to the profile, re-mine the window.</CardDescription>
          </CardHeader>
          <CardContent>
            <Button variant="outline" disabled={!!busy} onClick={() => act("consolidate", api.consolidate, "Consolidation queued")}>
              {busy === "consolidate" && <Loader2 className="animate-spin" />} Run consolidation
            </Button>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Prune</CardTitle>
            <CardDescription>Retire idle or failing tools; keeps any tool another tool depends on.</CardDescription>
          </CardHeader>
          <CardContent>
            <Button variant="outline" disabled={!!busy} onClick={() => act("prune", api.prune, "Prune ran: see the policy strip")}>
              {busy === "prune" && <Loader2 className="animate-spin" />} Run prune
            </Button>
          </CardContent>
        </Card>
      </div>

      <h2 className="mt-10 mb-3 text-lg font-semibold">Heal timeline</h2>
      {heals.length === 0 && (
        <p className="rounded-lg border border-dashed p-6 text-sm text-muted-foreground">
          Switch the mock site to v2 and run the price tool: drift, the patch, the gate and the promotion show up here live.
        </p>
      )}
      <div className="flex flex-col gap-3">
        {heals.map((h, i) => (
          <HealRow key={`${h.toolId}-${i}`} heal={h} />
        ))}
      </div>
    </>
  );
}

function HealRow({ heal }: { heal: Heal }) {
  const labels: Record<Stage, string> = { drift: "Drift detected", patch: "Patch forged", gate: "Gated (old + new)", promoted: "Promoted" };
  return (
    <Card>
      <CardContent className="flex flex-col gap-3 pt-4">
        <div className="flex items-center gap-2 text-sm">
          <span className="font-mono">{heal.name}</span>
          {heal.timeToHealMs != null && <Badge>time to heal {fmtMs(heal.timeToHealMs)}</Badge>}
        </div>
        <ol className="grid gap-2 sm:grid-cols-4">
          {HEAL_STAGES.map((stage) => {
            const s = heal.stages[stage];
            const isDrift = stage === "drift";
            return (
              <li key={stage} className={cn("rounded-lg border p-2 text-xs", s && !isDrift && s.ok && "border-emerald-500/40 bg-emerald-500/5", s && (isDrift || !s.ok) && "border-amber-500/40 bg-amber-500/5")}>
                <div className="flex items-center gap-1.5 font-medium">
                  {!s ? <Circle className="size-3.5 text-muted-foreground" /> : isDrift || !s.ok ? <X className="size-3.5 text-amber-600" /> : <Check className="size-3.5 text-emerald-600" />}
                  {labels[stage]}
                </div>
                {s && <div className="mt-1 text-muted-foreground">{s.ts ? fmtTime(s.ts) : ""} {s.note}</div>}
              </li>
            );
          })}
        </ol>
      </CardContent>
    </Card>
  );
}

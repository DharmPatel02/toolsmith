"use client";
import Link from "next/link";
import { Circle, Clock, Wrench } from "lucide-react";

import { ErrorState, Loading, PageHeader, Stat, TrustBadge } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { fmtMs, fmtPct } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import { useEvents } from "@/lib/useEvents";
import { cn } from "@/lib/utils";

export default function ToolShopPage() {
  const tools = useApi(() => api.tools());
  const metrics = useApi(() => api.metrics());
  const capture = useApi(() => api.captureState());

  // Toolbox changes arrive over SSE; refetch so counts stay live during the demo.
  useEvents(() => {
    tools.reload();
    metrics.reload();
  }, ["promoted", "pruned", "healed", "trust_changed", "run_completed"]);
  useEvents(() => capture.reload(), ["capture_paused"]);

  const list = tools.data ?? [];
  const minutesSaved = metrics.data?.minutes_saved_week ?? list.reduce((sum, t) => sum + t.minutes_saved, 0);

  return (
    <>
      <PageHeader
        title="Tool shop"
        description="Every tool here was written by ToolSmith from work it watched you repeat."
        actions={<RecorderBadge paused={capture.data?.paused} unavailable={!!capture.error} />}
      />

      <div className="mb-8 grid gap-4 sm:grid-cols-3">
        <Stat
          className="sm:col-span-2"
          label="Minutes saved this week"
          value={<span className="text-5xl">{Math.round(minutesSaved)}</span>}
          hint="Across all tool runs, measured against how long you took by hand."
        />
        <Stat label="Toolbox" value={list.length} hint={`${list.filter((t) => t.trust === "autonomous").length} autonomous`} />
      </div>

      {tools.loading && !tools.data && <Loading label="Loading tools" />}
      {tools.error && <ErrorState error={tools.error} onRetry={tools.reload} />}
      {tools.data && list.length === 0 && (
        <p className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
          No tools yet. Accept a suggestion to forge the first one.
        </p>
      )}

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {list.map((tool) => (
          <Link key={tool.tool_id} href={`/tools/${tool.tool_id}`} className="group">
            <Card className="h-full transition-shadow group-hover:shadow-md">
              <CardHeader>
                <div className="flex items-start justify-between gap-2">
                  <CardTitle className="leading-snug">{tool.title}</CardTitle>
                  <TrustBadge trust={tool.trust} />
                </div>
                <CardDescription className="font-mono text-xs">{tool.name}()</CardDescription>
              </CardHeader>
              <CardContent className="grid grid-cols-3 gap-2 text-sm">
                <Metric icon={<Wrench className="size-3.5" />} label="runs" value={tool.runs} />
                <Metric label="success" value={tool.runs ? fmtPct(tool.success_rate) : "—"} />
                <Metric icon={<Clock className="size-3.5" />} label="saved" value={`${Math.round(tool.minutes_saved)} min`} />
                {tool.p50_ms > 0 && (
                  <div className="col-span-3 text-xs text-muted-foreground">p50 {fmtMs(tool.p50_ms)} per run</div>
                )}
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </>
  );
}

function Metric({ label, value, icon }: { label: string; value: React.ReactNode; icon?: React.ReactNode }) {
  return (
    <div>
      <div className="flex items-center gap-1 text-xs text-muted-foreground">
        {icon}
        {label}
      </div>
      <div className="font-medium tabular-nums">{value}</div>
    </div>
  );
}

function RecorderBadge({ paused, unavailable }: { paused?: boolean; unavailable: boolean }) {
  const label = unavailable ? "Recorder status unknown" : paused ? "Recorder paused" : "Recorder on";
  return (
    <Badge variant="outline" className="gap-1.5 py-1">
      <Circle
        className={cn(
          "size-2.5",
          !unavailable && !paused && "animate-pulse fill-red-500 text-red-500",
          (paused || unavailable) && "fill-muted-foreground text-muted-foreground",
        )}
      />
      {label}
    </Badge>
  );
}

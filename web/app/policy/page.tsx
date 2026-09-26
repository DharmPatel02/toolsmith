"use client";
import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import { toast } from "sonner";

import { ErrorState, Loading, PageHeader } from "@/components/common";
import { MetricsDashboard } from "@/components/metrics-charts";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { fmtValue } from "@/lib/format";
import type { PolicyChange } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { useEvents } from "@/lib/useEvents";

function flatten(obj: Record<string, unknown>, prefix = ""): [string, unknown][] {
  return Object.entries(obj).flatMap(([k, v]) =>
    v && typeof v === "object" && !Array.isArray(v) ? flatten(v as Record<string, unknown>, `${prefix}${k}.`) : [[prefix + k, v] as [string, unknown]],
  );
}

export default function PolicyPage() {
  const policy = useApi(() => api.policy());
  const metrics = useApi(() => api.metrics());
  useEvents(() => policy.reload(), ["policy_changed"]);
  useEvents(() => metrics.reload(), ["promoted", "pruned", "healed", "run_completed"]);

  const approve = async (change: PolicyChange) => {
    try {
      await api.approvePolicyChange(change.id);
      toast.success(`Approved: ${change.field} → ${fmtValue(change.to)}`);
      policy.reload();
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  const changes = [...(policy.data?.changes ?? [])].reverse();

  return (
    <>
      <PageHeader title="Policy & metrics" description="The guardrails ToolSmith runs under, how they changed, and what it has saved you. Loosening always waits for your approval." />

      <section className="mb-10 grid gap-6 lg:grid-cols-[1fr_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>Guardrail changes</CardTitle>
          </CardHeader>
          <CardContent>
            {policy.error && <ErrorState error={policy.error} onRetry={policy.reload} />}
            {changes.length === 0 && !policy.error && <p className="text-sm text-muted-foreground">No changes yet. The policy learner proposes them from your feedback and from pruned tools.</p>}
            <ul className="flex flex-col gap-3">
              {changes.map((c) => (
                <li key={c.id} className="flex items-start gap-3 text-sm">
                  {c.direction === "tighten" ? (
                    <ArrowUpRight className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-label="tighten" />
                  ) : (
                    <ArrowDownRight className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-label="loosen" />
                  )}
                  <div className="flex-1">
                    <div>
                      <span className="font-mono text-xs">{c.field}</span> {fmtValue(c.from)} → <span className="font-medium">{fmtValue(c.to)}</span>
                    </div>
                    <div className="text-xs text-muted-foreground">because {c.because}</div>
                  </div>
                  {c.status === "pending" ? (
                    <Button size="xs" onClick={() => approve(c)}>
                      Approve
                    </Button>
                  ) : (
                    <Badge variant="outline">{c.status}</Badge>
                  )}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Thresholds {policy.data && <span className="font-normal text-muted-foreground">· v{policy.data.version}</span>}</CardTitle>
          </CardHeader>
          <CardContent>
            {policy.loading && !policy.data && <Loading label="Loading policy" />}
            {policy.data && (
              <>
                <dl className="grid grid-cols-1 gap-x-8 gap-y-1 text-sm sm:grid-cols-2">
                  {flatten(policy.data.thresholds).map(([k, v]) => (
                    <div key={k} className="flex justify-between gap-2 border-b py-1">
                      <dt className="font-mono text-xs text-muted-foreground">{k}</dt>
                      <dd className="font-medium tabular-nums">{fmtValue(v)}</dd>
                    </div>
                  ))}
                </dl>
                {policy.data.rules.length > 0 && (
                  <div className="mt-4">
                    <div className="mb-1 text-sm font-medium">Rules</div>
                    <ul className="flex flex-col gap-1 font-mono text-xs">
                      {policy.data.rules.map((r, i) => (
                        <li key={i}>{JSON.stringify(r)}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            )}
          </CardContent>
        </Card>
      </section>

      <h2 className="mb-4 text-lg font-semibold">Metrics</h2>
      {metrics.loading && !metrics.data && <Loading label="Computing metrics" />}
      {metrics.error && <ErrorState error={metrics.error} onRetry={metrics.reload} />}
      {metrics.data && <MetricsDashboard m={metrics.data} />}
    </>
  );
}

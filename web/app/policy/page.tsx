"use client";
import { ErrorState, Loading, PageHeader } from "@/components/common";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { fmtValue } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import { useEvents } from "@/lib/useEvents";

function flatten(obj: Record<string, unknown>, prefix = ""): [string, unknown][] {
  return Object.entries(obj).flatMap(([k, v]) =>
    v && typeof v === "object" && !Array.isArray(v) ? flatten(v as Record<string, unknown>, `${prefix}${k}.`) : [[prefix + k, v] as [string, unknown]],
  );
}

export default function PolicyPage() {
  const policy = useApi(() => api.policy());
  useEvents(() => policy.reload(), ["policy_changed"]);

  return (
    <>
      <PageHeader title="Policy & metrics" description="The guardrails ToolSmith runs under. It proposes changes to them; loosening always waits for you." />
      {policy.loading && !policy.data && <Loading label="Loading policy" />}
      {policy.error && <ErrorState error={policy.error} onRetry={policy.reload} />}
      {policy.data && (
        <Card>
          <CardHeader>
            <CardTitle>Thresholds · v{policy.data.version}</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-2 gap-x-8 gap-y-1.5 text-sm md:grid-cols-3">
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
          </CardContent>
        </Card>
      )}
    </>
  );
}

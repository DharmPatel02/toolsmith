"use client";
import { useParams } from "next/navigation";
import { toast } from "sonner";

import { ErrorState, ExecutionPathBadge, Loading, PageHeader, Stat, TrustBadge } from "@/components/common";
import { RaceView } from "@/components/race-view";
import { ARTIFACT_FILES, RunPanel } from "@/components/run-panel";
import { CodeViewer, Markdown, ParamsTable, RequiresList } from "@/components/tool-doc";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { fmtDate, fmtMs, fmtPct } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import { useEvents } from "@/lib/useEvents";

export default function ToolPage() {
  const { id } = useParams<{ id: string }>();
  const tool = useApi(() => api.tool(id), [id]);
  const versions = useApi(() => api.versions(id), [id]);
  const lineage = useApi(() => api.lineage(id), [id]);
  const metrics = useApi(() => api.metrics());

  useEvents(
    (e) => {
      if ((e.data as { tool_id?: string }).tool_id === id) {
        tool.reload();
        versions.reload();
      }
    },
    ["trust_changed", "healed", "run_completed", "drift_detected", "promoted"],
  );

  if (tool.loading && !tool.data) return <Loading label="Loading tool" />;
  if (tool.error) return <ErrorState error={tool.error} onRetry={tool.reload} />;
  const t = tool.data!;
  const v = t.version;

  const rollback = async (version: number) => {
    try {
      await api.rollback(id, version);
      toast.success(`Rolled back to v${version}`);
      tool.reload();
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  const tokensBefore = metrics.data?.tokens?.before || 18000;

  return (
    <>
      <PageHeader
        title={t.title}
        description={
          <span className="flex flex-wrap items-center gap-2">
            <span className="font-mono">{t.name}()</span>
            <TrustBadge trust={t.trust} />
            <ExecutionPathBadge tier={v.derivation.observed_tier} path={v.derivation.execution_path} />
            <Badge variant="outline">{t.tier} tier</Badge>
            <Badge variant="outline">v{t.active_version}</Badge>
          </span>
        }
      />

      <div className="mb-6 grid gap-4 sm:grid-cols-4">
        <Stat label="Runs" value={t.runs} />
        <Stat label="Success rate" value={t.runs ? fmtPct(t.success_rate) : "—"} />
        <Stat label="p50 duration" value={t.p50_ms ? fmtMs(t.p50_ms) : "—"} />
        <Stat label="Minutes saved" value={Math.round(t.minutes_saved)} />
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Run</CardTitle>
            </CardHeader>
            <CardContent>
              <RunPanel toolId={id} schema={v.params_schema} baseline={{ minutes: 9, tokens: tokensBefore }} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Race</CardTitle>
            </CardHeader>
            <CardContent>
              <RaceView intent={`make this week's ${t.title.toLowerCase()}`} inputs={{ file: ARTIFACT_FILES.at(-1) }} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Tutorial</CardTitle>
            </CardHeader>
            <CardContent>
              <Markdown>{v.tutorial_md}</Markdown>
            </CardContent>
          </Card>
          <CodeViewer code={v.code} />
        </div>

        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Parameters</CardTitle>
            </CardHeader>
            <CardContent>
              <ParamsTable schema={v.params_schema} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Needs</CardTitle>
            </CardHeader>
            <CardContent>
              <RequiresList requires={v.requires} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Versions</CardTitle>
            </CardHeader>
            <CardContent>
              {versions.error && <ErrorState error={versions.error} />}
              <ul className="flex flex-col gap-2 text-sm">
                {versions.data?.map((ver) => (
                  <li key={ver.version} className="flex items-center gap-2">
                    <span className="font-medium">v{ver.version}</span>
                    <span className="text-xs text-muted-foreground">
                      {ver.approved_at ? `approved ${fmtDate(ver.approved_at)}` : "not approved"} · from{" "}
                      {Object.entries(ver.created_from).map(([k, val]) => `${k.replace("_id", "")} ${val}`).join(", ")}
                    </span>
                    {ver.version === t.active_version ? (
                      <Badge className="ml-auto">active</Badge>
                    ) : (
                      <Button size="xs" variant="outline" className="ml-auto" onClick={() => rollback(ver.version)}>
                        Roll back
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
          {lineage.data && (lineage.data.calls.length > 0 || lineage.data.dependents.length > 0) && (
            <Card>
              <CardHeader>
                <CardTitle>Lineage</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-2 text-sm">
                {lineage.data.calls.map((dep) => (
                  <div key={dep.tool_id} style={{ paddingLeft: dep.depth * 16 }} className="font-mono text-xs">
                    └ calls {dep.name}
                  </div>
                ))}
                {lineage.data.dependents.length > 0 && (
                  <div className="text-xs text-muted-foreground">Used by: {lineage.data.dependents.join(", ")}</div>
                )}
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </>
  );
}

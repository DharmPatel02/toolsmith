"use client";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { ErrorState, ExecutionPathBadge, Loading, PageHeader } from "@/components/common";
import { CodeViewer, Markdown, ParamsTable, RequiresList, VerdictChecks } from "@/components/tool-doc";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { useEvents } from "@/lib/useEvents";

export default function CandidatePage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const candidate = useApi(() => api.candidate(id), [id]);
  const [busy, setBusy] = useState(false);

  useEvents(
    (e) => {
      if ((e.data as { candidate_id?: string }).candidate_id === id) candidate.reload();
    },
    ["forged", "gate_passed", "gate_failed", "promoted"],
  );

  if (candidate.loading && !candidate.data) return <Loading label="Loading candidate" />;
  if (candidate.error) return <ErrorState error={candidate.error} onRetry={candidate.reload} />;
  const c = candidate.data!;

  const decide = async (approve: boolean) => {
    setBusy(true);
    try {
      if (approve) {
        const { tool_id } = await api.approveCandidate(c._id);
        toast.success("Promoted at dry_run");
        router.push(`/tools/${tool_id}`);
      } else {
        await api.rejectCandidate(c._id);
        toast("Rejected");
        candidate.reload();
      }
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader
        title={c.spec.purpose || c.spec.name}
        description={
          <span className="flex flex-wrap items-center gap-2">
            <span className="font-mono">{c.spec.name}()</span>
            <Badge variant="outline">candidate · {c.status}</Badge>
            <ExecutionPathBadge tier={c.derivation.observed_tier} path={c.derivation.execution_path} />
          </span>
        }
        actions={
          c.status === "passed" && (
            <>
              <Button variant="outline" disabled={busy} onClick={() => decide(false)}>
                Reject
              </Button>
              <Button disabled={busy} onClick={() => decide(true)}>
                Approve & promote
              </Button>
            </>
          )
        }
      />

      {c.spec.not_automatable && (
        <div className="mb-6 rounded-lg border border-amber-500/40 bg-amber-500/10 p-4 text-sm">
          Not automatable: {Object.values(c.spec.not_automatable).join(" ")}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Gate</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              <VerdictChecks checks={c.verdict?.checks ?? {}} />
              {c.verdict?.reason && <p className="text-sm text-muted-foreground">{c.verdict.reason}</p>}
              {!c.verdict && <p className="text-sm text-muted-foreground">Gate has not reported yet.</p>}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Tutorial</CardTitle>
            </CardHeader>
            <CardContent>
              <Markdown>{c.tutorial_md}</Markdown>
            </CardContent>
          </Card>
          <CodeViewer code={c.code} />
          {c.tests && <CodeViewer code={c.tests} label="Tests" />}
        </div>
        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Parameters</CardTitle>
            </CardHeader>
            <CardContent>
              <ParamsTable schema={c.params_schema} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Needs</CardTitle>
            </CardHeader>
            <CardContent>
              <RequiresList requires={c.requires} />
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
}

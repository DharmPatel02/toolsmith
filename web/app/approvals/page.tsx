"use client";
// Approvals inbox (e.g. the warehouse manager): actions a tool prepared that need a person first.
// Approve -> the runtime executes them through the granted connectors. Reject -> the note becomes
// feedback for the tool's next version.
import { useState } from "react";
import { Check, Inbox, Loader2, X } from "lucide-react";
import { toast } from "sonner";

import { ErrorState, Loading, PageHeader } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { fmtDate, fmtTime } from "@/lib/format";
import type { Approval } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { useEvents } from "@/lib/useEvents";

export default function ApprovalsPage() {
  const items = useApi(() => api.approvals());
  useEvents(() => items.reload(), ["run_completed"]);

  return (
    <>
      <PageHeader title="Approvals" description="Actions your tools prepared that need a person before they happen. Nothing here has been sent yet." />
      {items.loading && !items.data && <Loading />}
      {items.error && <ErrorState error={items.error} onRetry={items.reload} />}
      {items.data?.length === 0 && (
        <p className="flex items-center justify-center gap-2 rounded-lg border border-dashed p-8 text-sm text-muted-foreground">
          <Inbox className="size-4" /> Nothing waiting for approval.
        </p>
      )}
      <div className="flex flex-col gap-4">
        {items.data?.map((a) => (
          <ApprovalCard key={a.run_id} item={a} onDone={() => items.setData((l) => l?.filter((x) => x.run_id !== a.run_id) ?? null)} />
        ))}
      </div>
    </>
  );
}

function ApprovalCard({ item, onDone }: { item: Approval; onDone: () => void }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const decide = async (decision: "approve" | "reject") => {
    if (decision === "reject" && !note.trim()) {
      toast("Add a short reason", { description: "It becomes feedback for the next version of the tool." });
      return;
    }
    setBusy(decision);
    try {
      const res = await api.decideApproval(item.run_id, decision, note.trim() || undefined);
      toast.success(decision === "approve" ? `Approved: ${res.executed ?? item.actions.length} action(s) done` : "Rejected: feedback recorded");
      onDone();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(null);
    }
  };
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{item.summary ?? item.tool_title ?? item.tool_id}</CardTitle>
        <CardDescription>
          {item.tool_title ?? item.tool_id} · prepared {fmtDate(item.created_at)} {fmtTime(item.created_at)}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <ul className="flex flex-col gap-1.5 text-sm">
          {item.actions.map((action, i) => (
            <li key={i} className="flex items-start gap-2">
              <span className="mt-0.5 rounded bg-muted px-1.5 font-mono text-[11px]">{action.kind}</span>
              <span>{action.description ?? JSON.stringify(action.payload)}</span>
            </li>
          ))}
        </ul>
        <div className="flex flex-wrap items-center gap-2">
          <Input className="max-w-sm" placeholder="Reason (required to reject)" value={note} onChange={(e) => setNote(e.target.value)} aria-label="Reason" />
          <Button disabled={!!busy} onClick={() => decide("approve")}>
            {busy === "approve" ? <Loader2 className="animate-spin" /> : <Check />} Approve
          </Button>
          <Button variant="outline" disabled={!!busy} onClick={() => decide("reject")}>
            {busy === "reject" ? <Loader2 className="animate-spin" /> : <X />} Reject
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

"use client";
// Revert, cancel, repeat (plan §1.4): run history with per-run Undo, Delete tool (soft, blocked while
// in use or depended on; may be suggested again unless "don't suggest again"), and Rebuild.
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Loader2, RotateCcw, Trash2, Wrench } from "lucide-react";
import { toast } from "sonner";

import { ErrorState } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { fmtDate, fmtMs, fmtTime } from "@/lib/format";
import type { RunSummary } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { useEvents } from "@/lib/useEvents";

export function RunHistory({ toolId }: { toolId: string }) {
  const runs = useApi(() => api.toolRuns(toolId), [toolId]);
  const [busy, setBusy] = useState<string | null>(null);
  useEvents(
    (e) => {
      if ((e.data as { tool_id?: string }).tool_id === toolId) runs.reload();
    },
    ["run_completed"],
  );

  const undo = async (run: RunSummary) => {
    setBusy(run.run_id);
    try {
      const res = await api.revertRun(run.run_id);
      toast.success(`Undone: ${res.undone} action(s) reverted`);
      runs.reload();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(null);
    }
  };

  if (runs.error) return <ErrorState error={runs.error} onRetry={runs.reload} />;
  const list = runs.data ?? [];
  if (!list.length) return <p className="text-sm text-muted-foreground">No runs yet. Confirmed runs appear here and can be undone.</p>;
  return (
    <ul className="flex flex-col divide-y rounded-lg border" aria-label="Run history">
      {list.map((run) => {
        const undoable = run.mode === "live" && run.status !== "reverted" && run.actions.some((a) => a.receipt);
        return (
          <li key={run.run_id} className="flex flex-col gap-1 px-3 py-2 text-sm">
            <div className="flex items-center gap-2">
              <span className="font-medium">
                {fmtDate(run.started_at)} {fmtTime(run.started_at)}
              </span>
              <Badge variant="outline">{run.status ?? run.outcome}</Badge>
              <span className="text-xs text-muted-foreground">{fmtMs(run.duration_ms)}</span>
              {undoable && (
                <Button size="xs" variant="outline" className="ml-auto" disabled={!!busy} onClick={() => undo(run)}>
                  {busy === run.run_id ? <Loader2 className="animate-spin" /> : <RotateCcw />} Undo
                </Button>
              )}
            </div>
            {run.actions.length > 0 && (
              <ul className="pl-1 text-xs text-muted-foreground">
                {run.actions.map((a, i) => (
                  <li key={i} className={run.status === "reverted" ? "line-through" : undefined}>
                    {a.description ?? a.kind}
                  </li>
                ))}
              </ul>
            )}
          </li>
        );
      })}
    </ul>
  );
}

export function ToolLifecycle({ toolId, title, patternId }: { toolId: string; title: string; patternId?: string }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [never, setNever] = useState(false);
  const [busy, setBusy] = useState<"delete" | "rebuild" | null>(null);
  const [blocked, setBlocked] = useState<string | null>(null);

  const remove = async () => {
    setBusy("delete");
    try {
      const res = await api.deleteTool(toolId, never);
      if (!res.ok) {
        setBlocked(res.blocked_reason ?? "The tool is in use right now.");
        return;
      }
      toast.success(`Deleted ${title}`, {
        description: never ? "It won't be suggested again." : "If you keep doing this by hand, ToolSmith may suggest it again later.",
      });
      router.push("/");
    } catch (err) {
      setBlocked((err as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const rebuild = async () => {
    if (!patternId) return;
    setBusy("rebuild");
    try {
      await api.acceptSuggestion(patternId);
      toast.success("Rebuilding", { description: "A new version is being forged and gated; the current one keeps working." });
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="flex flex-wrap gap-2">
      {patternId && (
        <Button variant="outline" size="sm" disabled={!!busy} onClick={rebuild}>
          {busy === "rebuild" ? <Loader2 className="animate-spin" /> : <Wrench />} Rebuild
        </Button>
      )}
      <Button
        variant="destructive"
        size="sm"
        onClick={() => {
          setBlocked(null);
          setOpen(true);
        }}
      >
        <Trash2 /> Delete tool
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete “{title}”?</DialogTitle>
            <DialogDescription>
              The tool stops running and leaves your tool shop. Its versions and run history are kept for the audit trail. Past runs are not undone; use Undo on a run for that.
            </DialogDescription>
          </DialogHeader>
          <label className="flex items-center justify-between gap-4 text-sm">
            <span>Don&apos;t suggest this workflow again</span>
            <Switch checked={never} onCheckedChange={setNever} aria-label="Don't suggest again" />
          </label>
          {blocked && <p className="rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-sm">Can&apos;t delete yet: {blocked}</p>}
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Keep it
            </Button>
            <Button variant="destructive" disabled={busy === "delete"} onClick={remove}>
              {busy === "delete" && <Loader2 className="animate-spin" />} Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

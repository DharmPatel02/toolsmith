"use client";
// One suggestion: why, what will be automated, what permissions it needs, and the approval flow
// (grant permissions -> accept -> live forge -> approve). Also "previously deleted" + "Don't ask again".
import { useState } from "react";
import { Clock, HelpCircle, History, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { APP_NAMES, PermissionList, PlanView } from "@/components/automation";
import { Signature } from "@/components/common";
import { ForgeProgress } from "@/components/forge-progress";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import type { Suggestion } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export function neverScope(s: Suggestion): string {
  return `pattern:${s.signature.join(">")}`;
}

export function SuggestionCard({
  s,
  onWhy,
  onDecline,
  onGone,
}: {
  s: Suggestion;
  onWhy: () => void;
  onDecline: () => void;
  onGone: () => void;
}) {
  const plan = useApi(() => api.automationPlan(s.signature, s.est_minutes_saved_week), [s.pattern_id]);
  const [asking, setAsking] = useState(false);
  const [forging, setForging] = useState(false);
  const [busy, setBusy] = useState(false);
  const missing = plan.data?.permissions.filter((p) => !p.granted) ?? [];

  const startForge = async () => {
    setBusy(true);
    try {
      const res = await api.acceptSuggestion(s.pattern_id);
      setAsking(false);
      setForging(true);
      toast.success("Approved: building the tool", { description: res.job_id ? `job ${res.job_id}` : undefined });
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const neverAgain = async () => {
    try {
      await api.declineSuggestion(s.pattern_id, "don't ask again", neverScope(s));
      toast("Won't suggest this again", { description: "Added as a rule to your policy." });
      onGone();
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  const snooze = async () => {
    try {
      await api.snoozeSuggestion(s.pattern_id);
      toast("Snoozed", { description: "It will come back after the cooldown." });
      onGone();
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <CardTitle>{s.title}</CardTitle>
          {s.deleted_at && (
            <Badge variant="outline" className="gap-1">
              <History className="size-3" /> You deleted this tool on {fmtDate(s.deleted_at)}
            </Badge>
          )}
        </div>
        <CardDescription>
          {s.reason}
          {s.deleted_at && " It's still repeating, so ToolSmith is asking once more."}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-wrap gap-6 text-sm">
          <Fact label="Seen" value={`${s.support}×`} />
          <Fact label="Distinct days" value={s.distinct_days} />
          <Fact label="Est. saving" value={`${s.est_minutes_saved_week} min/week`} />
          {s.dynamic_params.length > 0 && <Fact label="Changes each time" value={s.dynamic_params.map((p) => p.name).join(", ")} />}
        </div>
        <Signature steps={s.signature} />
        <section className="rounded-lg border bg-muted/30 p-3">
          <h3 className="mb-2 text-sm font-medium">What will be automated</h3>
          {plan.loading && !plan.data && <Loader2 className="size-4 animate-spin text-muted-foreground" />}
          {plan.data && <PlanView plan={plan.data} />}
          {plan.data && plan.data.permissions.length > 0 && (
            <p className="mt-3 text-xs text-muted-foreground">
              Needs access to {plan.data.permissions.map((p) => APP_NAMES[p.connector] ?? p.connector).join(", ")}. You grant each one before anything is built.
            </p>
          )}
        </section>
        {forging && <ForgeProgress patternId={s.pattern_id} onDone={onGone} />}
      </CardContent>
      <CardFooter className="flex-wrap gap-2">
        <Button onClick={() => setAsking(true)} disabled={forging || !plan.data}>
          Review &amp; approve
        </Button>
        <Button variant="outline" onClick={onDecline}>
          Decline
        </Button>
        <Button variant="ghost" onClick={snooze}>
          <Clock /> Snooze
        </Button>
        {s.deleted_at && (
          <Button variant="ghost" onClick={neverAgain}>
            Don&apos;t ask again
          </Button>
        )}
        <Button variant="link" className="ml-auto" onClick={onWhy}>
          <HelpCircle /> Why?
        </Button>
      </CardFooter>

      <Dialog open={asking} onOpenChange={setAsking}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Build “{s.title}”?</DialogTitle>
            <DialogDescription>
              ToolSmith will write the tool, test it on your past runs, and write a one-page tutorial. It starts in dry-run mode: nothing is sent or changed until you confirm.
            </DialogDescription>
          </DialogHeader>
          {plan.data && (
            <div className="flex flex-col gap-4">
              <PlanView plan={plan.data} />
              <div>
                <h3 className="mb-2 text-sm font-medium">Permissions</h3>
                <PermissionList permissions={plan.data.permissions} onChange={plan.reload} />
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setAsking(false)}>
              Not now
            </Button>
            <Button onClick={startForge} disabled={busy || missing.length > 0}>
              {busy && <Loader2 className="animate-spin" />}
              {missing.length > 0 ? `Grant ${missing.length} permission${missing.length > 1 ? "s" : ""} first` : "Approve and build"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

function Fact({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="font-medium tabular-nums">{value}</div>
    </div>
  );
}

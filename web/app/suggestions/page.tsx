"use client";
import { useState } from "react";
import { Ban } from "lucide-react";
import { toast } from "sonner";

import { ErrorState, Loading, PageHeader } from "@/components/common";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { SuggestionCard } from "@/components/suggestion-card";
import { WhyDrawer } from "@/components/why-drawer";
import { api } from "@/lib/api";
import type { Suggestion } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { useEvents } from "@/lib/useEvents";

export default function SuggestionsPage() {
  const suggestions = useApi(() => api.suggestions());
  const declined = useApi(() => api.declinedSuggestions());
  const [why, setWhy] = useState<Suggestion | null>(null);
  const [declining, setDeclining] = useState<Suggestion | null>(null);
  useEvents(() => suggestions.reload(), ["suggestion_new"]);

  return (
    <>
      <PageHeader title="Suggestions" description="Workflows you repeat that ToolSmith could turn into a tool. Nothing is built without your approval." />

      {suggestions.loading && !suggestions.data && <Loading label="Loading suggestions" />}
      {suggestions.error && <ErrorState error={suggestions.error} onRetry={suggestions.reload} />}
      {suggestions.data?.length === 0 && (
        <p className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">No suggestions right now.</p>
      )}

      <div className="flex flex-col gap-4">
        {suggestions.data?.map((s) => (
          <SuggestionCard
            key={s.pattern_id}
            s={s}
            onWhy={() => setWhy(s)}
            onDecline={() => setDeclining(s)}
            onGone={() => suggestions.setData((list) => list?.filter((x) => x.pattern_id !== s.pattern_id) ?? null)}
          />
        ))}
      </div>

      <section className="mt-10">
        <h2 className="mb-1 text-lg font-semibold">Declined by ToolSmith</h2>
        <p className="mb-4 text-sm text-muted-foreground">Repeats it noticed but chose not to suggest, and why.</p>
        {declined.error && <ErrorState error={declined.error} onRetry={declined.reload} />}
        <div className="grid gap-3 md:grid-cols-2">
          {declined.data?.map((s) => (
            <div key={s.pattern_id} className="rounded-lg border border-dashed p-4">
              <div className="flex items-start gap-2">
                <Ban className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                <div>
                  <div className="font-medium">{s.title}</div>
                  <div className="text-sm text-muted-foreground">{s.declined_reason ?? s.reason}</div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    seen {s.support}× on {s.distinct_days} day{s.distinct_days === 1 ? "" : "s"}
                  </div>
                </div>
              </div>
            </div>
          ))}
          {declined.data?.length === 0 && <p className="text-sm text-muted-foreground">Nothing declined yet.</p>}
        </div>
      </section>

      <WhyDrawer suggestion={why} onOpenChange={(open) => !open && setWhy(null)} />
      <DeclineDialog
        suggestion={declining}
        onClose={() => setDeclining(null)}
        onDeclined={(id) => suggestions.setData((list) => list?.filter((x) => x.pattern_id !== id) ?? null)}
      />
    </>
  );
}

function DeclineDialog({
  suggestion,
  onClose,
  onDeclined,
}: {
  suggestion: Suggestion | null;
  onClose: () => void;
  onDeclined: (patternId: string) => void;
}) {
  const [reason, setReason] = useState("");
  const [never, setNever] = useState(false);
  const [scope, setScope] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!suggestion) return;
    setBusy(true);
    try {
      await api.declineSuggestion(suggestion.pattern_id, reason || "not useful", never ? scope || suggestion.title : undefined);
      toast(never ? `Declined, and never for ${scope || "this"}` : "Declined", {
        description: never ? "A new rule was added to your policy." : undefined,
      });
      onDeclined(suggestion.pattern_id);
      setReason("");
      setNever(false);
      setScope("");
      onClose();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={!!suggestion} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Decline “{suggestion?.title}”</DialogTitle>
          <DialogDescription>Your reason feeds back into what ToolSmith mines next.</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="decline-reason">Reason</Label>
            <Input id="decline-reason" placeholder="e.g. I only do this at month end" value={reason} onChange={(e) => setReason(e.target.value)} />
          </div>
          <label className="flex items-center justify-between gap-4 text-sm">
            <span>Never suggest this kind of thing again</span>
            <Switch checked={never} onCheckedChange={setNever} aria-label="Never for this" />
          </label>
          {never && (
            <div className="flex flex-col gap-2">
              <Label htmlFor="decline-scope">Scope (folder, app or site)</Label>
              <Input id="decline-scope" placeholder="/finance" value={scope} onChange={(e) => setScope(e.target.value)} />
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={busy}>
            Decline
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

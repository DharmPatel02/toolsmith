"use client";
// Placeholder for P3.3.1 (policy strip). Shows the latest policy event so the slot is live from Phase 1.
import { ShieldCheck } from "lucide-react";

import { fmtValue } from "@/lib/format";
import { useEventLog } from "@/lib/useEvents";

export function PolicyStrip() {
  const [latest] = useEventLog(["policy_changed"], 1);
  const change = latest?.data as { field?: string; from?: unknown; to?: unknown; because?: string } | undefined;
  return (
    <div className="flex h-10 shrink-0 items-center gap-3 border-t bg-muted/40 px-4 text-xs text-muted-foreground">
      <ShieldCheck className="size-3.5" />
      <span className="font-medium text-foreground">Policy</span>
      {change ? (
        <span>
          {change.field} {fmtValue(change.from)} → {fmtValue(change.to)} · because {change.because}
        </span>
      ) : (
        <span>No guardrail changes yet</span>
      )}
    </div>
  );
}

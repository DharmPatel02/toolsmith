"use client";
// "Why?" drawer: dated episodes from vector recall + the evidence strip (P3.3.5):
// dated screenshots from the user's own sessions with the detected step list under them.
import { CalendarDays } from "lucide-react";

import { ErrorState, Loading, Signature } from "@/components/common";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { api, assetUrl } from "@/lib/api";
import { fmtDate, fmtTokens } from "@/lib/format";
import type { FrameEvidence, Suggestion } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export function WhyDrawer({ suggestion, onOpenChange }: { suggestion: Suggestion | null; onOpenChange: (open: boolean) => void }) {
  return (
    <Sheet open={!!suggestion} onOpenChange={onOpenChange}>
      <SheetContent className="w-full overflow-y-auto data-[side=right]:w-full data-[side=right]:sm:max-w-2xl">
        {suggestion && <WhyBody suggestion={suggestion} />}
      </SheetContent>
    </Sheet>
  );
}

function WhyBody({ suggestion }: { suggestion: Suggestion }) {
  const why = useApi(() => api.why(suggestion.pattern_id), [suggestion.pattern_id]);
  return (
    <>
      <SheetHeader>
        <SheetTitle>Why this suggestion?</SheetTitle>
        <SheetDescription>{suggestion.reason}</SheetDescription>
      </SheetHeader>
      <div className="flex flex-col gap-6 px-4 pb-6">
        {why.loading && <Loading label="Recalling episodes" />}
        {why.error && <ErrorState error={why.error} onRetry={why.reload} />}
        {why.data && (
          <>
            <EvidenceStrip frames={why.data.frames} signature={suggestion.signature} />
            <section>
              <h3 className="mb-2 text-sm font-medium">Matching episodes (vector recall)</h3>
              <ul className="divide-y rounded-lg border">
                {why.data.episodes.map((ep) => (
                  <li key={ep.session_id} className="flex items-center gap-3 px-3 py-2 text-sm">
                    <CalendarDays className="size-4 text-muted-foreground" />
                    <span className="w-28 shrink-0 font-medium">{fmtDate(ep.date)}</span>
                    <span className="flex-1 truncate">{ep.intent_summary}</span>
                    <span className="text-xs text-muted-foreground tabular-nums">
                      {ep.minutes} min · {fmtTokens(ep.tokens)} tok · {ep.score.toFixed(2)}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          </>
        )}
      </div>
    </>
  );
}

export function EvidenceStrip({ frames, signature }: { frames: FrameEvidence[]; signature: string[] }) {
  if (!frames.length) {
    return <p className="text-sm text-muted-foreground">No screen evidence for this pattern (found from logs only).</p>;
  }
  return (
    <section>
      <h3 className="mb-2 text-sm font-medium">What it saw on your screen</h3>
      <div className="grid grid-cols-3 gap-3">
        {frames.slice(0, 3).map((frame) => (
          <figure key={frame.frame_id} className="overflow-hidden rounded-lg border bg-muted">
            {/* eslint-disable-next-line @next/next/no-img-element -- thumbs come from the API, not the Next image pipeline */}
            <img src={assetUrl(frame.thumb_url)} alt={`Screen on ${fmtDate(frame.ts)}: ${frame.verb}`} className="aspect-video w-full object-cover" />
            <figcaption className="flex flex-col gap-0.5 px-2 py-1.5 text-xs">
              <span className="font-medium">{fmtDate(frame.ts)}</span>
              <span className="truncate font-mono text-muted-foreground">{frame.verb}</span>
            </figcaption>
          </figure>
        ))}
      </div>
      <div className="mt-3">
        <Signature steps={signature} />
      </div>
    </section>
  );
}

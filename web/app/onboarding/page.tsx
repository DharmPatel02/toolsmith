"use client";
// Getting started: ask for screen-activity access (consent), start the recorder extension, confirm
// capture is live, then (demo) load synthetic history so ToolSmith has weeks of patterns to find.
import Link from "next/link";
import { useEffect, useState, useSyncExternalStore } from "react";
import { Check, Circle, Loader2, ShieldCheck } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/common";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { useEvents } from "@/lib/useEvents";
import { cn } from "@/lib/utils";

const CONSENT_KEY = "toolsmith.screenConsent";
const noopSubscribe = () => () => {};
function storedConsent(): boolean {
  try {
    return window.localStorage.getItem(CONSENT_KEY) === "yes";
  } catch {
    return false; // storage blocked: ask again
  }
}

export default function OnboardingPage() {
  const stored = useSyncExternalStore(noopSubscribe, storedConsent, () => false);
  const [choice, setChoice] = useState<boolean | null>(null);
  const consented = choice ?? stored;
  const [live, setLive] = useState<"unknown" | "live" | "paused">("unknown");
  const [loading, setLoading] = useState(false);
  const [historyLoaded, setHistoryLoaded] = useState(false);

  // capture is "live" once the extension's batches are being accepted and nothing is paused
  useEffect(() => {
    if (!consented) return;
    let stop = false;
    const poll = async () => {
      try {
        const [state, sessions] = await Promise.all([api.captureState(), api.captureSessions()]);
        if (!stop) setLive(state.paused ? "paused" : sessions.length ? "live" : "unknown");
      } catch {
        /* API down: keep polling */
      }
    };
    poll();
    const id = setInterval(poll, 3000);
    return () => {
      stop = true;
      clearInterval(id);
    };
  }, [consented]);
  useEvents(() => setLive("live"), ["frame_labeled"]);

  const consent = (yes: boolean) => {
    try {
      window.localStorage.setItem(CONSENT_KEY, yes ? "yes" : "no");
    } catch {
      /* ignore */
    }
    setChoice(yes);
    if (!yes) toast("No problem", { description: "Nothing is recorded. You can still try ToolSmith with demo history." });
  };

  const loadHistory = async () => {
    setLoading(true);
    try {
      await api.loadDemoHistory();
      setHistoryLoaded(true);
      toast.success("Demo history loaded", { description: "Three weeks of synthetic activity; suggestions appear as patterns are mined." });
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <PageHeader title="Get started" description="ToolSmith learns from how you already work. Three steps, and you stay in control of each." />
      <div className="flex max-w-3xl flex-col gap-4">
        <StepCard n={1} done={consented} title="Allow screen activity">
          <ul className="mb-4 flex flex-col gap-1.5 text-sm">
            {[
              "Only on sites you allow-list (the demo sites on :8081). Nothing else is ever seen.",
              "Clicks, page changes and screenshots of those sites. Typed text is never read, only its length.",
              "Password and card fields are never captured.",
              "Pause any time, delete the last 5 minutes, and everything expires after 7 days.",
            ].map((t) => (
              <li key={t} className="flex gap-2">
                <ShieldCheck className="mt-0.5 size-4 shrink-0 text-muted-foreground" /> {t}
              </li>
            ))}
          </ul>
          {consented ? (
            <p className="text-sm text-emerald-700 dark:text-emerald-400">You allowed screen activity. Change it any time in Capture &amp; privacy.</p>
          ) : (
            <div className="flex gap-2">
              <Button onClick={() => consent(true)}>Allow screen activity</Button>
              <Button variant="outline" onClick={() => consent(false)}>
                Not now
              </Button>
            </div>
          )}
        </StepCard>

        <StepCard n={2} done={live === "live"} title="Start the recorder">
          <ol className="mb-3 list-decimal pl-5 text-sm">
            <li>
              Open <span className="font-mono">chrome://extensions</span>, turn on Developer mode, Load unpacked → <span className="font-mono">toolsmith/extension</span>.
            </li>
            <li>
              Open{" "}
              <a className="underline" href="http://localhost:8081" target="_blank" rel="noreferrer">
                the demo site
              </a>
              , click the ToolSmith icon, then <b>Start recording</b>. Chrome asks for access to this tab: that&apos;s the screen permission.
            </li>
          </ol>
          <p className="flex items-center gap-2 text-sm">
            {live === "live" ? <Check className="size-4 text-emerald-600" /> : <Loader2 className="size-4 animate-spin text-muted-foreground" />}
            {live === "live" ? "Capture is live." : live === "paused" ? "Recorder is paused." : consented ? "Waiting for the recorder…" : "Allow screen activity first."}
          </p>
        </StepCard>

        <StepCard n={3} done={historyLoaded} title="Load demo history (synthetic)">
          <p className="mb-3 text-sm text-muted-foreground">
            For the demo, ToolSmith loads three weeks of synthetic activity: competitor price checks and invoice handling, plus a few one-off tasks it should ignore.
          </p>
          <div className="flex gap-2">
            <Button onClick={loadHistory} disabled={loading || historyLoaded}>
              {loading && <Loader2 className="animate-spin" />} {historyLoaded ? "Loaded" : "Load demo history"}
            </Button>
            {historyLoaded && (
              <Link href="/suggestions" className={buttonVariants({ variant: "outline" })}>
                See suggestions
              </Link>
            )}
          </div>
        </StepCard>
      </div>
    </>
  );
}

function StepCard({ n, title, done, children }: { n: number; title: string; done: boolean; children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <span className={cn("flex size-6 items-center justify-center rounded-full border text-xs", done && "border-emerald-500 bg-emerald-500 text-white")}>
            {done ? <Check className="size-3.5" /> : n}
          </span>
          {title}
          {!done && <Circle className="ml-auto size-3 text-muted-foreground" />}
        </CardTitle>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

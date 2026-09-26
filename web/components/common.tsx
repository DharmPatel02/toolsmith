"use client";
import { AlertTriangle, Loader2 } from "lucide-react";
import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { ExecutionPath, Tier, Trust } from "@/lib/types";
import { cn } from "@/lib/utils";

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

const TRUST_STYLE: Record<Trust, string> = {
  dry_run: "bg-slate-500/15 text-slate-700 dark:text-slate-300",
  supervised: "bg-amber-500/15 text-amber-700 dark:text-amber-300",
  autonomous: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
};

export function TrustBadge({ trust }: { trust: Trust }) {
  return (
    <Badge variant="outline" className={cn("border-transparent font-medium", TRUST_STYLE[trust])}>
      {trust.replace("_", " ")}
    </Badge>
  );
}

const TIER_APP: Record<Tier, string> = { T0: "logs", T1: "the browser", T2: "Excel (screen)" };
const PATH_RUNTIME: Record<ExecutionPath, string> = {
  api: "pandas",
  browser: "a browser",
  cli: "the command line",
  assisted: "assisted steps",
};

/** "seen in Excel · runs on pandas" */
export function ExecutionPathBadge({ tier, path }: { tier: Tier; path: ExecutionPath }) {
  return (
    <Badge variant="secondary" className="gap-1 font-normal" title={`observed at ${tier}, executes via ${path}`}>
      seen in {TIER_APP[tier]} <span className="text-muted-foreground">·</span> runs on {PATH_RUNTIME[path]}
    </Badge>
  );
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
      <Loader2 className="size-4 animate-spin" /> {label}…
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm">
      <AlertTriangle className="size-4 shrink-0 text-destructive" />
      <span className="flex-1">{error.message}</span>
      {onRetry && (
        <Button size="sm" variant="outline" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}

export function Stat({ label, value, hint, className }: { label: string; value: ReactNode; hint?: ReactNode; className?: string }) {
  return (
    <div className={cn("rounded-xl border bg-card p-4", className)}>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
      {hint && <div className="mt-1 text-xs text-muted-foreground">{hint}</div>}
    </div>
  );
}

export function Signature({ steps }: { steps: string[] }) {
  return (
    <div className="flex flex-wrap items-center gap-1 font-mono text-xs">
      {steps.map((step, i) => (
        <span key={i} className="flex items-center gap-1">
          {i > 0 && <span className="text-muted-foreground">→</span>}
          <span className="rounded bg-muted px-1.5 py-0.5">{step}</span>
        </span>
      ))}
    </div>
  );
}

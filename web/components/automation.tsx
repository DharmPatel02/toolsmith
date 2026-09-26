"use client";
// Shared pieces of the approval-first flow: the automation plan (what ToolSmith will do, what waits
// for a person, what stays manual) and permission grants (OAuth-style consent in a popup).
import { useState } from "react";
import { Check, Hand, KeyRound, Loader2, UserCheck, Zap } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api, isMockMode, markMockConnected } from "@/lib/api";
import type { AutomationPlan, PlanPermission } from "@/lib/types";
import { cn } from "@/lib/utils";

export const APP_NAMES: Record<string, string> = {
  slack: "Slack",
  jira: "Jira",
  tracker: "Shipment tracker",
  email: "Email inbox",
  web: "Allow-listed websites",
};

const AUTOMATION = {
  auto: { icon: Zap, label: "Automated", className: "text-emerald-600" },
  approval: { icon: UserCheck, label: "Needs your approval", className: "text-amber-600" },
  manual: { icon: Hand, label: "Stays with you", className: "text-muted-foreground" },
} as const;

export function PlanView({ plan, compact = false }: { plan: AutomationPlan; compact?: boolean }) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-3 text-xs">
        {(Object.keys(AUTOMATION) as (keyof typeof AUTOMATION)[]).map((k) => {
          const { icon: Icon, label, className } = AUTOMATION[k];
          return (
            <span key={k} className="flex items-center gap-1">
              <Icon className={cn("size-3.5", className)} /> {plan.counts[k]} {label.toLowerCase()}
            </span>
          );
        })}
      </div>
      {!compact && (
        <ol className="flex flex-col gap-1 text-sm" aria-label="What will be automated">
          {plan.steps.map((s, i) => {
            const { icon: Icon, label, className } = AUTOMATION[s.automation];
            return (
              <li key={i} className="flex items-center gap-2">
                <Icon className={cn("size-4 shrink-0", className)} aria-label={label} />
                <span className="flex-1">{s.label}</span>
                {s.connector && s.connector !== "web" && (
                  <Badge variant="outline" className="text-[10px]">
                    {APP_NAMES[s.connector] ?? s.connector}
                  </Badge>
                )}
                {s.automation === "approval" && <span className="text-xs text-amber-700 dark:text-amber-400">you approve first</span>}
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}

/** Opens the app's consent page and resolves once the grant shows up (or the popup is closed). */
export async function connectApp(app: string, scopes?: string[]): Promise<boolean> {
  const { consent_url } = await api.connect(app, scopes);
  if (!consent_url) return true;
  const popup = window.open(consent_url, `connect-${app}`, "width=560,height=680");
  if (isMockMode()) {
    // demo mode: the real consent page on the mock site redirects to /connectors in the popup,
    // which posts the user's answer back here
    return new Promise((resolve) => {
      const onMessage = (e: MessageEvent) => {
        if (e.origin !== window.location.origin || e.data?.type !== "toolsmith-consent" || e.data.app !== app) return;
        window.removeEventListener("message", onMessage);
        clearInterval(closed);
        if (e.data.ok) markMockConnected(app);
        resolve(!!e.data.ok);
      };
      const closed = setInterval(() => {
        if (popup && popup.closed) {
          clearInterval(closed);
          window.removeEventListener("message", onMessage);
          resolve(false);
        }
      }, 500);
      window.addEventListener("message", onMessage);
    });
  }
  if (!popup) {
    window.location.href = consent_url; // popup blocked: full-page consent, returns to /connectors
    return false;
  }
  const deadline = Date.now() + 3 * 60_000;
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 1200));
    const list = await api.connectors().catch(() => []);
    if (list.some((c) => c.app === app && c.status === "connected")) {
      popup.close();
      return true;
    }
    if (popup.closed) return false;
  }
  return false;
}

export function PermissionList({ permissions, onChange }: { permissions: PlanPermission[]; onChange?: () => void }) {
  const [busy, setBusy] = useState<string | null>(null);
  if (!permissions.length) return <p className="text-sm text-muted-foreground">No extra permissions needed.</p>;
  const connect = async (p: PlanPermission) => {
    setBusy(p.connector);
    try {
      const ok = await connectApp(p.connector, p.scopes);
      if (ok) toast.success(`${APP_NAMES[p.connector] ?? p.connector} connected`);
      else toast("Not connected", { description: "The consent window was closed or denied." });
      onChange?.();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(null);
    }
  };
  return (
    <ul className="flex flex-col gap-2" aria-label="Permissions needed">
      {permissions.map((p) => (
        <li key={p.connector} className="flex items-center gap-2 text-sm">
          <KeyRound className="size-4 shrink-0 text-muted-foreground" />
          <span className="flex-1">
            {APP_NAMES[p.connector] ?? p.connector} <span className="font-mono text-xs text-muted-foreground">{p.scopes.join(", ")}</span>
          </span>
          {p.granted ? (
            <span className="flex items-center gap-1 text-xs text-emerald-600">
              <Check className="size-3.5" /> granted
            </span>
          ) : (
            <Button size="xs" variant="outline" disabled={!!busy} onClick={() => connect(p)}>
              {busy === p.connector && <Loader2 className="animate-spin" />} Connect
            </Button>
          )}
        </li>
      ))}
    </ul>
  );
}

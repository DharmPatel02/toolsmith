"use client";
// Policy strip (P3.3.1), always visible: the guardrails rewriting themselves, live.
// Seeds from GET /policy changes, then follows SSE `policy_changed` and `pruned` (kept-because notes).
// Pending (loosening) changes carry an Approve button; nothing loosens without it.
import { useEffect, useState } from "react";
import { ChevronUp, ShieldCheck } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { fmtTime, fmtValue } from "@/lib/format";
import type { PolicyChange } from "@/lib/types";
import { useEvents } from "@/lib/useEvents";
import { cn } from "@/lib/utils";

export interface StripItem {
  key: string;
  ts: string;
  kind: "change" | "kept" | "pruned";
  text: string;
  because?: string;
  change?: PolicyChange;
}

type PrunedData = {
  pruned?: { tool_id: string; name?: string; reason?: string }[];
  kept?: { tool_id: string; name?: string; kept_because?: string }[];
  toolbox_count?: number;
};

export function changeItem(c: PolicyChange, ts = ""): StripItem {
  return {
    key: `chg:${c.id}`,
    ts,
    kind: "change",
    text: `${c.field.replace(/^thresholds\./, "")} ${fmtValue(c.from)} → ${fmtValue(c.to)}`,
    because: c.because,
    change: c,
  };
}

export function prunedItems(data: PrunedData, ts: string): StripItem[] {
  const items: StripItem[] = (data.kept ?? []).map((k) => ({
    key: `kept:${k.tool_id}:${ts}`,
    ts,
    kind: "kept",
    text: `${k.name ?? k.tool_id} not pruned`,
    because: k.kept_because,
  }));
  if (data.pruned?.length) {
    items.push({
      key: `pruned:${ts}`,
      ts,
      kind: "pruned",
      text: `pruned ${data.pruned.map((p) => p.name ?? p.tool_id).join(", ")}`,
      because: data.toolbox_count != null ? `toolbox now ${data.toolbox_count}` : data.pruned[0].reason,
    });
  }
  return items;
}

/** Newest first, one entry per change id (a later status replaces the earlier one). */
export function mergeItems(prev: StripItem[], next: StripItem[]): StripItem[] {
  const byKey = new Map(prev.map((i) => [i.key, i]));
  for (const item of next) byKey.set(item.key, { ...byKey.get(item.key), ...item });
  const fresh = next.map((i) => i.key);
  const rest = prev.filter((i) => !fresh.includes(i.key));
  return [...next.map((i) => byKey.get(i.key)!), ...rest].slice(0, 30);
}

export function PolicyStrip() {
  const [items, setItems] = useState<StripItem[]>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .policy()
      .then((p) => !cancelled && setItems((prev) => mergeItems(prev, [...p.changes].reverse().map((c) => changeItem(c)))))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  useEvents(
    (e) => {
      if (e.type === "policy_changed") {
        const d = e.data as Partial<PolicyChange> & { new?: unknown; _id?: string; change_id?: string };
        // P1's approve publishes only {change_id, field}: mark the known change applied.
        if (d.change_id && d.to === undefined && d.new === undefined) {
          setItems((prev) =>
            prev.map((i) => (i.change && i.change.id === d.change_id ? changeItem({ ...i.change, status: "applied" }, i.ts) : i)),
          );
          return;
        }
        const change = { ...d, id: d.id ?? d._id ?? `${d.field}:${e.ts}`, to: d.to ?? d.new } as PolicyChange;
        setItems((prev) => mergeItems(prev, [changeItem(change, e.ts)]));
      } else if (e.type === "pruned") {
        setItems((prev) => mergeItems(prev, prunedItems(e.data as PrunedData, e.ts)));
      }
    },
    ["policy_changed", "pruned"],
  );

  const approve = async (c: PolicyChange) => {
    try {
      await api.approvePolicyChange(c.id);
      setItems((prev) => mergeItems(prev, [changeItem({ ...c, status: "applied" })]));
      toast.success("Change approved");
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  const pending = items.filter((i) => i.change?.status === "pending");
  const latest = items[0];

  return (
    <div className="relative shrink-0 border-t bg-muted/40 text-xs">
      {open && items.length > 0 && (
        <ul className="max-h-64 overflow-y-auto border-b px-4 py-2" aria-label="Policy history">
          {items.map((i) => (
            <Row key={i.key} item={i} onApprove={approve} />
          ))}
        </ul>
      )}
      <div className="flex h-10 items-center gap-3 px-4">
        <ShieldCheck className="size-3.5 shrink-0 text-muted-foreground" />
        <span className="font-medium">Policy</span>
        <div className="min-w-0 flex-1 truncate text-muted-foreground" aria-live="polite">
          {latest ? <RowText item={latest} /> : "No guardrail changes yet"}
        </div>
        {pending.length > 0 && !open && (
          <Button size="xs" onClick={() => approve(pending[0].change!)}>
            Approve {pending[0].text}
          </Button>
        )}
        {items.length > 1 && (
          <button type="button" className="flex items-center gap-1 text-muted-foreground hover:text-foreground" onClick={() => setOpen(!open)}>
            {items.length} changes <ChevronUp className={cn("size-3.5 transition-transform", !open && "rotate-180")} />
          </button>
        )}
      </div>
    </div>
  );
}

function RowText({ item }: { item: StripItem }) {
  return (
    <>
      <span className={cn("font-mono", item.kind === "kept" && "text-foreground")}>{item.text}</span>
      {item.because && <span> · because {item.because.replace(/^kept: /, "")}</span>}
      {item.change && <span> · {item.change.status === "pending" ? "pending your approval" : item.change.status}</span>}
    </>
  );
}

function Row({ item, onApprove }: { item: StripItem; onApprove: (c: PolicyChange) => void }) {
  return (
    <li className="flex items-center gap-3 py-1">
      <span className="w-16 shrink-0 text-muted-foreground tabular-nums">{item.ts ? fmtTime(item.ts) : ""}</span>
      <Badge variant="outline" className="w-16 justify-center text-[10px]">
        {item.kind === "change" ? item.change?.direction ?? "change" : item.kind}
      </Badge>
      <span className="min-w-0 flex-1 truncate">
        <RowText item={item} />
      </span>
      {item.change?.status === "pending" && (
        <Button size="xs" onClick={() => onApprove(item.change!)}>
          Approve
        </Button>
      )}
    </li>
  );
}

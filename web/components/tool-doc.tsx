"use client";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Check, ChevronDown, ChevronRight, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { ParamsSchema, Requires } from "@/lib/types";
import { cn } from "@/lib/utils";

export function Markdown({ children }: { children: string }) {
  return (
    <div
      className={cn(
        "text-sm leading-relaxed",
        "[&_h1]:mb-2 [&_h1]:text-lg [&_h1]:font-semibold [&_h2]:mt-4 [&_h2]:mb-1 [&_h2]:font-semibold [&_h3]:mt-3 [&_h3]:font-medium",
        "[&_p]:my-1.5 [&_ul]:my-1.5 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5",
        "[&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:font-mono [&_code]:text-xs",
        "[&_pre]:my-2 [&_pre]:overflow-x-auto [&_pre]:rounded-lg [&_pre]:bg-muted [&_pre]:p-3 [&_pre_code]:bg-transparent [&_pre_code]:p-0",
        "[&_table]:my-2 [&_td]:border [&_td]:px-2 [&_td]:py-1 [&_th]:border [&_th]:px-2 [&_th]:py-1",
      )}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children}</ReactMarkdown>
    </div>
  );
}

export function ParamsTable({ schema }: { schema: ParamsSchema }) {
  const required = new Set(schema.required ?? []);
  const entries = Object.entries(schema.properties ?? {});
  if (!entries.length) return <p className="text-sm text-muted-foreground">No parameters.</p>;
  return (
    <table className="w-full text-sm">
      <thead className="text-left text-xs text-muted-foreground">
        <tr>
          <th className="pb-1 font-normal">Name</th>
          <th className="pb-1 font-normal">Type</th>
          <th className="pb-1 font-normal">Notes</th>
        </tr>
      </thead>
      <tbody>
        {entries.map(([name, prop]) => (
          <tr key={name} className="border-t">
            <td className="py-1.5 font-mono text-xs">
              {name}
              {required.has(name) && <span className="text-red-500">*</span>}
            </td>
            <td className="py-1.5 text-xs">{prop.enum ? prop.enum.join(" | ") : prop.type ?? "any"}</td>
            <td className="py-1.5 text-xs text-muted-foreground">{prop.description ?? ""}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function RequiresList({ requires }: { requires: Requires }) {
  const items = [
    ...requires.scopes.map((s) => ({ kind: "scope", value: s })),
    ...requires.deps.map((d) => ({ kind: "dep", value: d })),
    ...requires.tools.map((t) => ({ kind: "tool", value: t })),
  ];
  if (!items.length) return <span className="text-sm text-muted-foreground">No extra permissions.</span>;
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((item) => (
        <Badge key={item.kind + item.value} variant={item.kind === "scope" ? "default" : "outline"} className="font-mono text-[11px]">
          {item.kind === "scope" ? "🔑 " : ""}
          {item.value}
        </Badge>
      ))}
    </div>
  );
}

export function CodeViewer({ code, label = "Generated code" }: { code: string; label?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-lg border">
      <button type="button" className="flex w-full items-center gap-2 px-3 py-2 text-sm font-medium" onClick={() => setOpen(!open)}>
        {open ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
        {label}
        <span className="ml-auto text-xs font-normal text-muted-foreground">{code.split("\n").length} lines</span>
      </button>
      {open && (
        <pre className="max-h-[480px] overflow-auto border-t bg-muted/50 p-3 font-mono text-xs leading-relaxed">
          <code>{code}</code>
        </pre>
      )}
    </div>
  );
}

const CHECK_LABELS: Record<string, string> = {
  unit: "Unit tests",
  replay: "Replay on past runs",
  side_effects: "Side effects (dry run)",
  dedupe: "Not a duplicate",
};

export function VerdictChecks({ checks }: { checks: Record<string, boolean> }) {
  const names = Object.keys(checks).length ? Object.keys(checks) : Object.keys(CHECK_LABELS);
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      {names.map((name) => {
        const known = name in checks;
        const ok = checks[name];
        return (
          <div
            key={name}
            className={cn(
              "flex items-center gap-2 rounded-lg border px-3 py-2 text-sm",
              known && ok && "border-emerald-500/40 bg-emerald-500/10",
              known && !ok && "border-red-500/40 bg-red-500/10",
            )}
          >
            {known ? ok ? <Check className="size-4 text-emerald-600" /> : <X className="size-4 text-red-600" /> : <span className="size-4 rounded-full border" />}
            {CHECK_LABELS[name] ?? name}
          </div>
        );
      })}
    </div>
  );
}

"use client";
// Run panel (P3.2.2): form generated from params_schema → dry run preview (intended writes) → Confirm.
import { useState } from "react";
import Link from "next/link";
import { FileText, Play, Send, UserCheck } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import { fmtMs, fmtTokens } from "@/lib/format";
import type { ParamsSchema, RunResult } from "@/lib/types";

// data/artifacts files the demo runs against (P2 owns the folder; no listing endpoint in §3.4).
export const ARTIFACT_FILES = (process.env.NEXT_PUBLIC_ARTIFACT_FILES ?? "week1.xlsx,week2.xlsx,week3.xlsx,week4.xlsx").split(",");

const INVOICE_FILES = ["inv-2201.pdf", "inv-2202.pdf", "inv-2203.pdf", "inv-2204.pdf", "inv-2205.pdf", "inv-2206.pdf", "inv-2207.pdf"];

const isFileParam = (name: string, type?: string, format?: string) =>
  type === "file" || format === "file" || /(^|_)(file|path|xlsx|csv|invoice|po)$/.test(name);

/** Which demo artifacts a file parameter can take (data/artifacts). */
function fileOptions(name: string): string[] {
  if (/invoice/.test(name)) return INVOICE_FILES;
  if (/(^|_)po$/.test(name)) return ["po.xlsx"];
  return ARTIFACT_FILES;
}

function defaultFile(name: string): string {
  const options = fileOptions(name);
  return options.includes("inv-2202.pdf") ? "inv-2202.pdf" : options.at(-1)!;
}

export interface Baseline {
  minutes: number;
  tokens?: number; // only when an agent-from-scratch token count is meaningful
}

export function RunPanel({
  toolId,
  schema,
  baseline,
  onConfirmed,
}: {
  toolId: string;
  schema: ParamsSchema;
  baseline?: Baseline;
  onConfirmed?: () => void;
}) {
  const props = Object.entries(schema.properties ?? {});
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      props.map(([name, p]) => [name, p.default != null ? String(p.default) : isFileParam(name, p.type, p.format) ? defaultFile(name) : name === "week" ? "4" : ""]),
    ),
  );
  const [preview, setPreview] = useState<RunResult | null>(null);
  const [result, setResult] = useState<RunResult | null>(null);
  const [busy, setBusy] = useState(false);

  const params = () =>
    Object.fromEntries(
      props.map(([name, p]) => [name, p.type === "number" || p.type === "integer" ? Number(values[name]) : values[name]]),
    );

  const run = async (confirm: boolean) => {
    setBusy(true);
    try {
      const res = await api.runTool(toolId, params(), confirm);
      if (confirm || !res.needs_confirm) {
        setResult(res);
        setPreview(null);
        toast.success("Run complete");
        onConfirmed?.();
      } else {
        setPreview(res);
        setResult(null);
      }
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <form
        className="grid gap-3 sm:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          run(false);
        }}
      >
        {props.map(([name, p]) => (
          <div key={name} className="flex flex-col gap-1.5">
            <Label htmlFor={`param-${name}`}>
              {name}
              {schema.required?.includes(name) && <span className="text-red-500">*</span>}
            </Label>
            {isFileParam(name, p.type, p.format) || p.enum ? (
              <select
                id={`param-${name}`}
                className="h-8 rounded-lg border bg-background px-2 text-sm"
                value={values[name]}
                onChange={(e) => setValues({ ...values, [name]: e.target.value })}
              >
                {(p.enum ?? fileOptions(name)).map((opt) => (
                  <option key={opt}>{opt}</option>
                ))}
              </select>
            ) : (
              <Input
                id={`param-${name}`}
                type={p.type === "number" || p.type === "integer" ? "number" : "text"}
                value={values[name]}
                onChange={(e) => setValues({ ...values, [name]: e.target.value })}
              />
            )}
          </div>
        ))}
        <div className="sm:col-span-2">
          <Button type="submit" disabled={busy}>
            <Play /> Dry run
          </Button>
        </div>
      </form>

      {preview && (
        <div className="rounded-lg border border-amber-500/40 bg-amber-500/5 p-4">
          <div className="mb-2 text-sm font-medium">Dry run preview: nothing has been written yet</div>
          {preview.intended_writes.length ? (
            <ul className="mb-3 flex flex-col gap-1 text-sm">
              {preview.intended_writes
                .filter((w) => !w.kind.startsWith("action:"))
                .map((w) => (
                  <li key={w.path} className="flex items-center gap-2 font-mono text-xs">
                    <FileText className="size-3.5" /> would write {w.path} <span className="text-muted-foreground">({w.kind})</span>
                  </li>
                ))}
              {(preview.actions ?? []).map((a, i) => (
                <li key={`a${i}`} className="flex items-center gap-2 text-xs">
                  {a.needs_approval ? <UserCheck className="size-3.5 text-amber-600" /> : <Send className="size-3.5" />}
                  {a.description ?? a.kind}
                  {a.needs_approval ? (
                    <span className="text-amber-700 dark:text-amber-400">(waits for approval)</span>
                  ) : (
                    <span className="text-muted-foreground">(on confirm)</span>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mb-3 text-sm text-muted-foreground">No writes.</p>
          )}
          <OutputView output={preview.output} />
          <div className="mt-3 flex gap-2">
            <Button size="sm" disabled={busy} onClick={() => run(true)}>
              Confirm and run
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setPreview(null)}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      {result && (
        <div className="rounded-lg border border-emerald-500/40 bg-emerald-500/5 p-4">
          <div className="mb-2 flex flex-wrap items-center gap-x-6 gap-y-1 text-sm">
            <span className="font-medium">
              {result.status === "awaiting_approval" ? "Ran; waiting for approval" : result.status === "failed" ? "Ran with errors" : "Done"} in{" "}
              {fmtMs(result.duration_ms)}
            </span>
            {result.tokens > 0 && <span>{fmtTokens(result.tokens)} tokens</span>}
            {baseline && (
              <span className="text-muted-foreground">
                by hand: {baseline.minutes} min → {fmtMs(result.duration_ms)}
                {baseline.tokens ? ` · ${fmtTokens(baseline.tokens)} → ${fmtTokens(result.tokens)} tokens` : ""}
              </span>
            )}
          </div>
          <OutputView output={result.output} />
          {(result.actions ?? []).length > 0 && (
            <ul className="mt-2 flex flex-col gap-1 text-xs">
              {(result.actions ?? []).map((a, i) => (
                <li key={i}>
                  <span className="font-mono">{a.status}</span> · {a.description ?? a.kind}
                  {a.error && <span className="text-destructive"> ({a.error})</span>}
                </li>
              ))}
            </ul>
          )}
          {result.status === "awaiting_approval" && (
            <p className="mt-2 text-sm">
              Some steps wait for approval:{" "}
              <Link href="/approvals" className="underline">
                open Approvals
              </Link>
              .
            </p>
          )}
          {result.status === "failed" && (
            <p className="mt-2 text-sm text-destructive">
              Some steps failed. If an app isn&apos;t connected,{" "}
              <Link href="/connectors" className="underline">
                connect it
              </Link>{" "}
              and run again.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function OutputView({ output }: { output: Record<string, unknown> }) {
  const summary = typeof output.summary === "string" ? output.summary : null;
  const rest = Object.fromEntries(Object.entries(output).filter(([k]) => k !== "summary"));
  return (
    <div className="text-sm">
      {summary && <p>{summary}</p>}
      {Object.keys(rest).length > 0 && (
        <pre className="mt-2 max-h-64 overflow-auto rounded bg-muted p-2 font-mono text-xs">{JSON.stringify(rest, null, 2)}</pre>
      )}
    </div>
  );
}

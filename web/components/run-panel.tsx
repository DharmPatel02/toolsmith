"use client";
// Run panel (P3.2.2): form generated from params_schema → dry run preview (intended writes) → Confirm.
import { useState } from "react";
import { FileText, Play } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import { fmtMs, fmtTokens } from "@/lib/format";
import type { ParamsSchema, RunResult } from "@/lib/types";

// data/artifacts files the demo runs against (P2 owns the folder; no listing endpoint in §3.4).
export const ARTIFACT_FILES = (process.env.NEXT_PUBLIC_ARTIFACT_FILES ?? "week1.xlsx,week2.xlsx,week3.xlsx,week4.xlsx").split(",");

const isFileParam = (name: string, type?: string) => type === "file" || /(^|_)(file|path|xlsx|csv)$/.test(name);

export interface Baseline {
  minutes: number;
  tokens: number;
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
      props.map(([name, p]) => [name, p.default != null ? String(p.default) : isFileParam(name, p.type) ? ARTIFACT_FILES.at(-1)! : name === "week" ? "4" : ""]),
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
            {isFileParam(name, p.type) || p.enum ? (
              <select
                id={`param-${name}`}
                className="h-8 rounded-lg border bg-background px-2 text-sm"
                value={values[name]}
                onChange={(e) => setValues({ ...values, [name]: e.target.value })}
              >
                {(p.enum ?? ARTIFACT_FILES).map((opt) => (
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
              {preview.intended_writes.map((w) => (
                <li key={w.path} className="flex items-center gap-2 font-mono text-xs">
                  <FileText className="size-3.5" /> would write {w.path} <span className="text-muted-foreground">({w.kind})</span>
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
            <span className="font-medium">Done in {fmtMs(result.duration_ms)}</span>
            <span>{fmtTokens(result.tokens)} tokens</span>
            {baseline && (
              <span className="text-muted-foreground">
                by hand: {baseline.minutes} min → {fmtMs(result.duration_ms)} · {fmtTokens(baseline.tokens)} → {fmtTokens(result.tokens)} tokens
              </span>
            )}
          </div>
          <OutputView output={result.output} />
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

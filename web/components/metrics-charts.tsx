"use client";
// Metrics page charts (P3.3.2). Colors come from CSS roles (--series-*, --viz-*) validated for
// light and dark; single numbers are stat tiles, not charts; one measure per chart (no dual axes).
import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Stat } from "@/components/common";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { fmtDate, fmtPct, fmtTokens } from "@/lib/format";
import type { Metrics } from "@/lib/types";

const S1 = "var(--series-1)";
const S2 = "var(--series-2)";
const MUTED = "var(--series-muted)";
const axis = { stroke: "var(--viz-axis)", fontSize: 11, tickLine: false, axisLine: false } as const;
const grid = { stroke: "var(--viz-grid)", strokeDasharray: "0", vertical: false } as const;

function TooltipBox({ active, payload, label, format }: {
  active?: boolean;
  payload?: { name?: string; value?: number; color?: string; payload?: Record<string, unknown> }[];
  label?: string;
  format?: (v: number) => string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border bg-popover px-3 py-2 text-xs text-popover-foreground shadow-md">
      {label && <div className="mb-1 font-medium">{label}</div>}
      {payload.map((p, i) => (
        <div key={i} className="flex items-center gap-2">
          <span className="size-2 rounded-full" style={{ background: p.color }} />
          <span className="text-muted-foreground">{p.name}</span>
          <span className="ml-auto font-medium tabular-nums">{format ? format(p.value ?? 0) : p.value}</span>
        </div>
      ))}
    </div>
  );
}

function ChartCard({ title, description, children, table }: {
  title: string;
  description?: string;
  children: React.ReactNode;
  table: { head: string[]; rows: (string | number)[][] };
}) {
  const [showTable, setShowTable] = useState(false);
  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-2">
          <div>
            <CardTitle className="text-sm">{title}</CardTitle>
            {description && <CardDescription className="text-xs">{description}</CardDescription>}
          </div>
          <button type="button" className="text-xs text-muted-foreground underline-offset-2 hover:underline" onClick={() => setShowTable(!showTable)}>
            {showTable ? "Chart" : "Table"}
          </button>
        </div>
      </CardHeader>
      <CardContent>
        {showTable ? (
          <table className="w-full text-xs">
            <thead className="text-left text-muted-foreground">
              <tr>{table.head.map((h) => <th key={h} className="pb-1 font-normal">{h}</th>)}</tr>
            </thead>
            <tbody>
              {table.rows.map((r, i) => (
                <tr key={i} className="border-t">{r.map((c, j) => <td key={j} className="py-1 tabular-nums">{c}</td>)}</tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="h-48">{children}</div>
        )}
      </CardContent>
    </Card>
  );
}

export function MetricsDashboard({ m }: { m: Metrics }) {
  const tokens = [
    { name: "By hand / agent", value: m.tokens.before ?? 0, fill: MUTED },
    { name: "With the tool", value: m.tokens.after ?? 0, fill: S1 },
  ];
  const ablation = [
    { name: "Workflows found", logs: m.ablation.logs_only?.workflows ?? 0, screen: m.ablation.logs_plus_screen?.workflows ?? 0 },
    { name: "False suggestions", logs: m.ablation.logs_only?.false_suggestions ?? 0, screen: m.ablation.logs_plus_screen?.false_suggestions ?? 0 },
  ];
  const detection = [
    { name: "Precision", value: m.detection?.precision ?? 0 },
    { name: "Recall", value: m.detection?.recall ?? 0 },
    { name: "Decoy false-positive rate", value: m.decoy_false_positive_rate ?? 0 },
  ];
  const toolbox = (m.toolbox_size_over_time ?? []).map((p) => ({
    date: String(p.date ?? p.day ?? p.ts ?? ""),
    size: Number(p.size ?? p.count ?? p.value ?? 0),
  }));
  const race = m.race ?? {};

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Minutes saved / week" value={Math.round(m.minutes_saved_week)} />
        <Stat label="Break-even runs" value={m.break_even_runs == null ? "—" : m.break_even_runs.toFixed(1)} hint="runs until the forge cost is paid back" />
        <Stat label="Replay pass rate" value={fmtPct(m.replay_pass_rate)} hint={<Meter value={m.replay_pass_rate} />} />
        <Stat label="Time to heal" value={m.time_to_heal_seconds == null ? "—" : `${Math.round(m.time_to_heal_seconds)} s`} hint={`${m.repair_loops ?? 0} repair loops`} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard
          title="Logs only vs logs + screen"
          description="What the screen layer adds (ablation)"
          table={{ head: ["", "Logs only", "Logs + screen"], rows: ablation.map((a) => [a.name, a.logs, a.screen]) }}
        >
          <ResponsiveContainer>
            <BarChart data={ablation} barGap={2} margin={{ top: 16, right: 8, left: -16, bottom: 0 }}>
              <CartesianGrid {...grid} />
              <XAxis dataKey="name" {...axis} />
              <YAxis allowDecimals={false} {...axis} />
              <Tooltip cursor={{ fill: "var(--viz-grid)", opacity: 0.4 }} content={<TooltipBox />} />
              <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="logs" name="Logs only" fill={S2} radius={[4, 4, 0, 0]} maxBarSize={36}>
                <LabelList dataKey="logs" position="top" fontSize={11} fill="var(--viz-axis)" />
              </Bar>
              <Bar dataKey="screen" name="Logs + screen" fill={S1} radius={[4, 4, 0, 0]} maxBarSize={36}>
                <LabelList dataKey="screen" position="top" fontSize={11} fill="var(--viz-axis)" />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title="Tokens per run"
          description="Solving from scratch vs running the tool"
          table={{ head: ["", "Tokens"], rows: tokens.map((t) => [t.name, t.value]) }}
        >
          <ResponsiveContainer>
            <BarChart data={tokens} layout="vertical" margin={{ top: 0, right: 48, left: 8, bottom: 0 }}>
              <XAxis type="number" hide />
              <YAxis type="category" dataKey="name" width={110} {...axis} />
              <Tooltip cursor={{ fill: "var(--viz-grid)", opacity: 0.4 }} content={<TooltipBox format={fmtTokens} />} />
              <Bar dataKey="value" name="Tokens" radius={[0, 4, 4, 0]} maxBarSize={28}>
                {tokens.map((t) => <Cell key={t.name} fill={t.fill} />)}
                <LabelList dataKey="value" position="right" fontSize={11} fill="var(--viz-axis)" formatter={(v) => fmtTokens(Number(v))} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title="Detection quality"
          description="Suggested workflows vs ground truth; decoys it wrongly suggested"
          table={{ head: ["Measure", "Value"], rows: detection.map((d) => [d.name, fmtPct(d.value)]) }}
        >
          <ResponsiveContainer>
            <BarChart data={detection} layout="vertical" margin={{ top: 0, right: 48, left: 8, bottom: 0 }}>
              <XAxis type="number" domain={[0, 1]} hide />
              <YAxis type="category" dataKey="name" width={150} {...axis} />
              <Tooltip cursor={{ fill: "var(--viz-grid)", opacity: 0.4 }} content={<TooltipBox format={fmtPct} />} />
              <Bar dataKey="value" name="Value" fill={S1} radius={[0, 4, 4, 0]} maxBarSize={24}>
                <LabelList dataKey="value" position="right" fontSize={11} fill="var(--viz-axis)" formatter={(v) => fmtPct(Number(v))} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title="Toolbox size over time"
          description="Tools forged minus tools pruned"
          table={{ head: ["Date", "Tools"], rows: toolbox.map((t) => [t.date, t.size]) }}
        >
          {toolbox.length ? (
            <ResponsiveContainer>
              <LineChart data={toolbox} margin={{ top: 16, right: 16, left: -16, bottom: 0 }}>
                <CartesianGrid {...grid} />
                <XAxis dataKey="date" {...axis} tickFormatter={(d) => (d ? fmtDate(d) : "")} />
                <YAxis allowDecimals={false} {...axis} />
                <Tooltip content={<TooltipBox />} labelFormatter={(d) => (d ? fmtDate(String(d)) : "")} cursor={{ stroke: "var(--viz-axis)", strokeDasharray: "3 3" }} />
                <Line type="monotone" dataKey="size" name="Tools" stroke={S1} strokeWidth={2} dot={{ r: 4, strokeWidth: 2, stroke: "var(--card)" }} activeDot={{ r: 5 }} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <p className="py-16 text-center text-sm text-muted-foreground">No history yet.</p>
          )}
        </ChartCard>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Race: steps" value={`${race.baseline?.steps ?? "—"} → ${race.tool?.steps ?? "—"}`} hint="baseline agent → tool" />
        <Stat label="Race: seconds" value={`${race.baseline?.seconds ?? "—"} → ${race.tool?.seconds ?? "—"}`} />
        <Stat label="Race: tokens" value={`${fmtTokens(race.baseline?.tokens ?? 0)} → ${fmtTokens(race.tool?.tokens ?? 0)}`} />
        <Stat label="Cost to observe" value={`$${(m.cost_to_observe_usd_day ?? 0).toFixed(2)}`} hint="per user per day (capture + labeling)" />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Capture quality</CardTitle>
          <CardDescription className="text-xs">Screen-derived steps vs the hand-labeled ground truth</CardDescription>
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          {Object.entries(m.capture_quality ?? {}).map(([k, v]) => (
            <div key={k}>
              <div className="text-xs text-muted-foreground">{k.replace(/_/g, " ")}</div>
              <div className="font-medium tabular-nums">{fmtPct(v)}</div>
              <Meter value={k === "noise" ? 1 - v : v} />
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

function Meter({ value }: { value: number }) {
  return (
    <span className="mt-1.5 block h-1.5 w-full overflow-hidden rounded-full bg-muted">
      <span className="block h-full rounded-full" style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%`, background: S1 }} />
    </span>
  );
}

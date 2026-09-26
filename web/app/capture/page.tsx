"use client";
// Capture panel (P3.3.6): pause/resume (shared with the extension, which polls /capture/state every
// 2 s), the allow-list, delete-last-5-minutes, and the audit list of capture sessions.
import { useState } from "react";
import { Globe, Pause, Play, ShieldCheck, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { ErrorState, Loading, PageHeader } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { fmtDate, fmtTime } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import { useEvents } from "@/lib/useEvents";

export default function CapturePage() {
  const state = useApi(() => api.captureState());
  const sessions = useApi(() => api.captureSessions());
  const [busy, setBusy] = useState(false);

  useEvents(() => {
    state.reload();
    sessions.reload();
  }, ["capture_paused"]);

  const toggle = async () => {
    setBusy(true);
    try {
      if (state.data?.paused) await api.captureResume();
      else await api.capturePause();
      toast(state.data?.paused ? "Recording resumed" : "Recording paused: the extension stops within 2 s");
      state.reload();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const deleteLast = async () => {
    if (!window.confirm("Delete everything captured in the last 5 minutes? This can't be undone.")) return;
    setBusy(true);
    try {
      const res = await api.captureDeleteLast(5);
      toast.success(`Deleted ${res.deleted_frames} frames and ${res.deleted_events} events`);
      sessions.reload();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const paused = state.data?.paused;

  return (
    <>
      <PageHeader
        title="Capture & privacy"
        description="What ToolSmith records, from where, and how to stop it. Frames expire after 7 days by TTL."
      />
      <div className="grid gap-6 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Recorder</CardTitle>
            <CardDescription>Applies to the browser extension and every capture source.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {state.loading && !state.data && <Loading />}
            {state.error && <ErrorState error={state.error} onRetry={state.reload} />}
            {state.data && (
              <div className="flex items-center gap-2 text-sm">
                <span className={paused ? "size-2.5 rounded-full bg-muted-foreground" : "size-2.5 animate-pulse rounded-full bg-red-500"} />
                {paused ? "Paused" : "Recording"}
              </div>
            )}
            <div className="flex flex-wrap gap-2">
              <Button onClick={toggle} disabled={busy || !state.data} variant={paused ? "default" : "outline"}>
                {paused ? <Play /> : <Pause />} {paused ? "Resume" : "Pause"}
              </Button>
              <Button onClick={deleteLast} disabled={busy} variant="destructive">
                <Trash2 /> Delete last 5 min
              </Button>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Allow-list</CardTitle>
            <CardDescription>The only sites the extension can see. Everything else is never captured.</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col gap-1.5 text-sm">
              {state.data?.allowed_origins.map((o) => (
                <li key={o} className="flex items-center gap-2 font-mono text-xs">
                  <Globe className="size-3.5 text-muted-foreground" /> {o}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Dropped on your machine</CardTitle>
            <CardDescription>Before anything is uploaded.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-1.5 text-sm">
            {["Password and card fields (no frame, no event)", "Typed text: only its length is kept", "Query strings and ids in URLs", "Frames beyond 1 per second / 300 per 30 min"].map((t) => (
              <div key={t} className="flex items-start gap-2">
                <ShieldCheck className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" /> {t}
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <h2 className="mt-10 mb-3 text-lg font-semibold">Capture audit</h2>
      {sessions.error && <ErrorState error={sessions.error} onRetry={sessions.reload} />}
      {sessions.data?.length === 0 && <p className="text-sm text-muted-foreground">No capture sessions recorded yet.</p>}
      {!!sessions.data?.length && (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-normal">Started</th>
                <th className="px-3 py-2 font-normal">Ended</th>
                <th className="px-3 py-2 font-normal">Sources</th>
                <th className="px-3 py-2 font-normal">Apps</th>
                <th className="px-3 py-2 text-right font-normal">Frames kept</th>
                <th className="px-3 py-2 font-normal">Dropped by rule</th>
              </tr>
            </thead>
            <tbody>
              {sessions.data.map((s, i) => (
                <tr key={s._id ?? i} className="border-t">
                  <td className="px-3 py-2">{fmtDate(s.started_at)} {fmtTime(s.started_at)}</td>
                  <td className="px-3 py-2">{s.ended_at ? fmtTime(s.ended_at) : <Badge variant="outline">open</Badge>}</td>
                  <td className="px-3 py-2">{s.sources.join(", ")}</td>
                  <td className="px-3 py-2">{s.apps_seen.join(", ")}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{s.frames_kept}</td>
                  <td className="px-3 py-2 text-xs text-muted-foreground">
                    {Object.entries(s.frames_dropped_by_rule).map(([k, v]) => `${k.replace(/_/g, " ")} ${v}`).join(" · ") || "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

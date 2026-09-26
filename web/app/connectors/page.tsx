"use client";
// Connected apps: what ToolSmith may use on your behalf, with what scopes. Also the landing page of
// the OAuth-style consent redirect (?app=&status= or ?error=); inside the consent popup it closes itself.
import { useEffect, useState } from "react";
import { KeyRound, Loader2, Unplug } from "lucide-react";
import { toast } from "sonner";

import { connectApp } from "@/components/automation";
import { ErrorState, Loading, PageHeader } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import type { Connector } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export default function ConnectorsPage() {
  const list = useApi(() => api.connectors());
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const status = q.get("status");
    const error = q.get("error");
    const code = q.get("code"); // demo mode: the consent page redirected straight here
    if (!status && !error && !code) return;
    if (window.opener && window.opener !== window) {
      if (code || error) {
        window.opener.postMessage({ type: "toolsmith-consent", app: q.get("app"), ok: !!code }, window.location.origin);
      }
      window.close(); // the page that opened the consent popup is polling for the grant
      return;
    }
    if (status === "connected") toast.success(`${q.get("app")} connected`);
    else if (status === "denied") toast("Access denied", { description: "Nothing was connected." });
    else if (error) toast.error(`Connection failed: ${error}`);
    window.history.replaceState(null, "", "/connectors");
  }, []);

  const connect = async (c: Connector) => {
    setBusy(c.app);
    try {
      if (await connectApp(c.app, c.available_scopes)) toast.success(`${c.name} connected`);
      list.reload();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const revoke = async (c: Connector) => {
    setBusy(c.app);
    try {
      await api.revokeConnector(c.app);
      toast(`${c.name} disconnected`, { description: "Tools that need it will ask again before running." });
      list.reload();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      <PageHeader
        title="Connected apps"
        description="Apps ToolSmith may use for tools you approved. Each one asks for your consent, shows its scopes, and can be revoked at any time."
      />
      {list.loading && !list.data && <Loading />}
      {list.error && <ErrorState error={list.error} onRetry={list.reload} />}
      <div className="grid gap-4 md:grid-cols-2">
        {list.data?.map((c) => (
          <Card key={c.app}>
            <CardHeader>
              <div className="flex items-center justify-between gap-2">
                <CardTitle className="flex items-center gap-2">
                  <KeyRound className="size-4 text-muted-foreground" /> {c.name}
                </CardTitle>
                <Badge variant={c.status === "connected" ? "default" : "outline"}>{c.status.replace("_", " ")}</Badge>
              </div>
              <CardDescription>
                {c.status === "connected"
                  ? `Granted ${c.scopes.join(", ")}${c.connected_at ? ` on ${fmtDate(c.connected_at)}` : ""}`
                  : `Would ask for ${c.available_scopes.join(", ")}`}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {c.status === "connected" ? (
                <Button variant="outline" size="sm" disabled={!!busy} onClick={() => revoke(c)}>
                  {busy === c.app ? <Loader2 className="animate-spin" /> : <Unplug />} Revoke
                </Button>
              ) : (
                <Button size="sm" disabled={!!busy} onClick={() => connect(c)}>
                  {busy === c.app && <Loader2 className="animate-spin" />} Connect
                </Button>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </>
  );
}

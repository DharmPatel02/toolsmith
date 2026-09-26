"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { CalendarDays, Lightbulb, Send, Wrench } from "lucide-react";

import { PageHeader, Signature, TrustBadge } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { fmtDate, fmtMs, fmtTokens } from "@/lib/format";
import type { ChatCard } from "@/lib/types";
import { cn } from "@/lib/utils";

interface Message {
  role: "user" | "assistant";
  text: string;
  cards?: ChatCard[];
  error?: boolean;
}

const EXAMPLES = [
  "Why did you suggest the dashboard tool?",
  "Run it on week4.xlsx",
  "I have an idea: alert me when a product drops below 5 in stock",
];

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = async (text: string) => {
    if (!text.trim() || busy) return;
    setMessages((m) => [...m, { role: "user", text }]);
    setInput("");
    setBusy(true);
    try {
      const reply = await api.chat(text, conversationId);
      setConversationId(reply.conversation_id);
      setMessages((m) => [...m, { role: "assistant", text: reply.reply, cards: reply.cards }]);
    } catch (err) {
      setMessages((m) => [...m, { role: "assistant", text: (err as Error).message, error: true }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex h-[calc(100vh-8.5rem)] flex-col">
      <PageHeader title="Chat" description="Ask ToolSmith why it suggested something, run a tool, or pitch an idea for a new one." />
      <div className="flex-1 overflow-y-auto rounded-xl border bg-muted/20 p-4">
        {messages.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-sm text-muted-foreground">
            Try one of these:
            {EXAMPLES.map((ex) => (
              <button key={ex} type="button" className="rounded-full border bg-background px-3 py-1.5 hover:bg-muted" onClick={() => send(ex)}>
                {ex}
              </button>
            ))}
          </div>
        )}
        <div className="flex flex-col gap-4">
          {messages.map((m, i) => (
            <div key={i} className={cn("flex flex-col gap-2", m.role === "user" ? "items-end" : "items-start")}>
              <div
                className={cn(
                  "max-w-[75%] rounded-2xl px-4 py-2 text-sm whitespace-pre-wrap",
                  m.role === "user" ? "bg-primary text-primary-foreground" : "border bg-background",
                  m.error && "border-destructive/40 text-destructive",
                )}
              >
                {m.text}
              </div>
              {m.cards?.map((card, j) => <CardView key={j} card={card} />)}
            </div>
          ))}
          {busy && <div className="text-sm text-muted-foreground">Thinking…</div>}
          <div ref={bottom} />
        </div>
      </div>
      <form
        className="mt-3 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
      >
        <Textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send(input);
            }
          }}
          placeholder="Message ToolSmith…"
          rows={1}
          className="min-h-10 resize-none"
          aria-label="Message"
        />
        <Button type="submit" disabled={busy || !input.trim()} size="lg" aria-label="Send">
          <Send />
        </Button>
      </form>
    </div>
  );
}

function CardView({ card }: { card: ChatCard }) {
  const shell = "w-full max-w-[75%] rounded-xl border bg-card p-3 text-sm";
  switch (card.kind) {
    case "tool":
      return (
        <Link href={`/tools/${card.tool.tool_id}`} className={cn(shell, "flex items-center gap-3 hover:bg-muted/50")}>
          <Wrench className="size-4 text-muted-foreground" />
          <span className="flex-1">
            <span className="font-medium">{card.tool.title}</span>{" "}
            <span className="font-mono text-xs text-muted-foreground">{card.tool.name}()</span>
          </span>
          <TrustBadge trust={card.tool.trust} />
        </Link>
      );
    case "suggestion":
      return (
        <Link href="/suggestions" className={cn(shell, "flex flex-col gap-2 hover:bg-muted/50")}>
          <span className="flex items-center gap-2 font-medium">
            <Lightbulb className="size-4 text-amber-500" /> {card.suggestion.title}
          </span>
          <Signature steps={card.suggestion.signature} />
        </Link>
      );
    case "episodes":
      return (
        <div className={shell}>
          <div className="mb-1 text-xs text-muted-foreground">Recalled episodes</div>
          <ul className="flex flex-col gap-1">
            {card.episodes.map((ep) => (
              <li key={ep.session_id} className="flex items-center gap-2">
                <CalendarDays className="size-3.5 text-muted-foreground" />
                <span className="w-24 font-medium">{fmtDate(ep.date)}</span>
                <span className="flex-1 truncate">{ep.intent_summary}</span>
                <span className="text-xs text-muted-foreground">
                  {ep.minutes} min · {fmtTokens(ep.tokens)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      );
    case "run":
      return (
        <div className={shell}>
          <div className="mb-1 text-xs text-muted-foreground">
            {card.run.mode === "dry_run" ? "Dry run preview" : "Run result"} · {fmtMs(card.run.duration_ms)}
            {card.run.route && ` · route ${card.run.route}`}
          </div>
          {typeof card.run.output.summary === "string" && <p>{card.run.output.summary}</p>}
          {card.run.intended_writes.map((w) => (
            <div key={w.path} className="font-mono text-xs">
              would write {w.path}
            </div>
          ))}
          {card.run.needs_confirm && card.run.tool_id && (
            <Link href={`/tools/${card.run.tool_id}`} className="mt-2 inline-block text-xs underline">
              Open the tool to confirm
            </Link>
          )}
        </div>
      );
    case "tool_hits":
      return (
        <div className={shell}>
          <div className="mb-1 text-xs text-muted-foreground">Matching tools (hybrid search)</div>
          <ul className="flex flex-col gap-1">
            {card.hits.map((hit) => (
              <li key={hit.tool_id}>
                <Link href={`/tools/${hit.tool_id}`} className="flex items-center gap-2 hover:underline">
                  <Wrench className="size-3.5 text-muted-foreground" />
                  <span className="flex-1 font-mono text-xs">{hit.name}()</span>
                  <span className="text-xs text-muted-foreground tabular-nums">{hit.score.toFixed(2)}</span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      );
    case "idea":
      return (
        <div className={shell}>
          {card.idea.covered_by_tool_id ? (
            <p>
              Already covered by{" "}
              <Link className="underline" href={`/tools/${card.idea.covered_by_tool_id}`}>
                {card.idea.covered_by_tool_id}
              </Link>
              .
            </p>
          ) : card.idea.spec ? (
            <div className="flex flex-col gap-1">
              <span className="font-medium">
                Proposed tool: <span className="font-mono">{card.idea.spec.name}()</span>
              </span>
              <span className="text-muted-foreground">{card.idea.spec.purpose}</span>
              <span className="text-xs text-muted-foreground">
                needs {card.idea.scopes.join(", ") || "no scopes"} · saves ~{card.idea.est_minutes_saved_week} min/week
              </span>
            </div>
          ) : (
            <p>Not feasible as a tool.</p>
          )}
        </div>
      );
  }
}

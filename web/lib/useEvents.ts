"use client";
// One shared SSE connection to GET /events for the whole app. P1's stream uses named events
// (`event: <type>`), so we attach a listener per type instead of relying on onmessage.
// Mock mode: nothing connects; `replayMock` plays fixture sequences (events.jsonl / race.jsonl) on a timer.
import { useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore } from "react";

import { API_BASE, isMockMode } from "./api";
import { EVENT_TYPES, type EventType, type ToolsmithEvent } from "./types";

import demoEventsMock from "@/mocks/demo_events.json";
import eventsMock from "@/mocks/events.json";
import raceMock from "@/mocks/race.json";

type Listener = (event: ToolsmithEvent) => void;
export type ConnectionState = "mock" | "connecting" | "open" | "error";

const listeners = new Set<Listener>();
const stateListeners = new Set<(s: ConnectionState) => void>();
let source: EventSource | null = null;
let connection: ConnectionState = "connecting";

function setConnection(s: ConnectionState) {
  connection = s;
  stateListeners.forEach((fn) => fn(s));
}

function dispatch(event: ToolsmithEvent) {
  listeners.forEach((fn) => fn(event));
}

function ensureConnected() {
  if (typeof window === "undefined" || source) return;
  if (isMockMode()) {
    setConnection("mock");
    return;
  }
  setConnection("connecting");
  source = new EventSource(`${API_BASE}/events`);
  source.onopen = () => setConnection("open");
  source.onerror = () => setConnection("error"); // EventSource retries on its own
  for (const type of EVENT_TYPES) {
    source.addEventListener(type, (e) => {
      try {
        dispatch(JSON.parse((e as MessageEvent).data));
      } catch {
        /* malformed frame */
      }
    });
  }
}

/** Mock mode only: plays a fixture sequence, spacing events `stepMs` apart. Returns a cancel function. */
export function replayMock(sequence: "demo" | "events" | "race" | ToolsmithEvent[], stepMs = 700): () => void {
  const events = (
    Array.isArray(sequence) ? sequence : { demo: demoEventsMock, events: eventsMock, race: raceMock }[sequence]
  ) as ToolsmithEvent[];
  const timers = events.map((event, i) =>
    setTimeout(() => dispatch({ ...event, ts: new Date().toISOString() }), (i + 1) * stepMs),
  );
  return () => timers.forEach(clearTimeout);
}

/** Calls `onEvent` for every event (optionally filtered by type). Keeps the latest handler without resubscribing. */
export function useEvents(onEvent: Listener, types?: EventType[]) {
  const handler = useRef(onEvent);
  useLayoutEffect(() => {
    handler.current = onEvent;
  });
  const typeKey = types?.join(",") ?? "";
  useEffect(() => {
    ensureConnected();
    const wanted = typeKey ? new Set(typeKey.split(",")) : null;
    const fn: Listener = (e) => {
      if (!wanted || wanted.has(e.type)) handler.current(e);
    };
    listeners.add(fn);
    return () => {
      listeners.delete(fn);
    };
  }, [typeKey]);
}

/** Recent events, newest first. */
export function useEventLog(types?: EventType[], limit = 50): ToolsmithEvent[] {
  const [log, setLog] = useState<ToolsmithEvent[]>([]);
  useEvents((e) => setLog((prev) => [e, ...prev].slice(0, limit)), types);
  return log;
}

function subscribeConnection(onChange: () => void) {
  ensureConnected();
  stateListeners.add(onChange);
  return () => {
    stateListeners.delete(onChange);
  };
}

export function useConnectionState(): ConnectionState {
  return useSyncExternalStore(subscribeConnection, () => connection, () => "connecting");
}

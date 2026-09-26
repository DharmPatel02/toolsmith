// Pure helpers shared by the content script and service worker. No chrome.* or DOM globals here,
// so `node --test` can import this file directly.

// Capture constants (task board §3.5b; mirror backend/app/config.py — do not tune during the demo).
export const MAX_FRAMES_PER_SEC = 1;
export const MAX_FRAMES_PER_SESSION = 300;
export const HEARTBEAT_BUDGET = 240; // past this, heartbeat frames are dropped first
export const FRAME_AFTER_CLICK_MS = 400;
export const BURST_END_IDLE_MS = 800;
export const HEARTBEAT_S = 5;
export const HEARTBEAT_ACTIVE_WINDOW_S = 30;
export const BATCH_POST_S = 5;
export const STATE_POLL_S = 2;
export const FRAME_MAX_WIDTH = 1280;
export const FRAME_WEBP_QUALITY = 0.7;

export const API_BASE = "http://localhost:8000";
export const USER_ID = "u_1";
// Must match manifest host_permissions + content_scripts.matches and CAPTURE_ALLOWED_ORIGINS.
export const ALLOWED_ORIGINS = ["http://localhost:8081"];

export type UIEventKind = "click" | "submit" | "nav" | "burst_end";
export type FrameTrigger = "click" | "nav" | "burst" | "heartbeat" | "flag";

export interface ElementInfo {
  role: string;
  name: string;
  data_attr: Record<string, string>;
}

export interface UIEvent {
  ts: string;
  kind: UIEventKind;
  url_template: string;
  element: ElementInfo;
  value_shape: { len: number; type: string } | null;
  frame_id: string | null;
}

export interface CaptureFrame {
  client_id: string;
  ts: string;
  trigger: FrameTrigger;
  app: string;
  window_title: string;
  url_template: string;
  image_webp_b64: string;
}

export interface CaptureBatch {
  user_id: string;
  capture_session_id: string;
  source: "chrome";
  events: UIEvent[];
  frames: CaptureFrame[];
}

const ID_SEGMENT = /^(\d+|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{16,}|[A-Za-z0-9_-]{24,})$/i;

/** origin + path with id-like segments replaced by `{id}`. Query strings and fragments are dropped. */
export function urlTemplate(href: string): string {
  const url = new URL(href);
  const path = url.pathname
    .split("/")
    .map((seg) => (seg && ID_SEGMENT.test(seg) ? "{id}" : seg))
    .join("/");
  return url.origin + path;
}

export function isAllowedOrigin(href: string | undefined, allowed: string[] = ALLOWED_ORIGINS): boolean {
  if (!href) return false;
  try {
    const origin = new URL(href).origin;
    return allowed.some((a) => a.replace(/\/$/, "") === origin);
  } catch {
    return false;
  }
}

/** Frame rate + per-session budget. Returns a reason string when the frame must be dropped. */
export function frameDropReason(
  trigger: FrameTrigger,
  nowMs: number,
  lastFrameMs: number,
  framesThisSession: number,
): string | null {
  if (framesThisSession >= MAX_FRAMES_PER_SESSION) return "session_cap";
  if (trigger === "heartbeat" && framesThisSession >= HEARTBEAT_BUDGET) return "heartbeat_budget";
  if (nowMs - lastFrameMs < 1000 / MAX_FRAMES_PER_SEC) return "rate_limit";
  return null;
}

/** Shape of a typed value without its content. */
export function valueShape(value: string, inputType: string): { len: number; type: string } {
  return { len: value.length, type: inputType || "text" };
}

export function clip(text: string, max = 80): string {
  const t = text.replace(/\s+/g, " ").trim();
  return t.length > max ? t.slice(0, max - 1) + "…" : t;
}

export function newId(prefix: string): string {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

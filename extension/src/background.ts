// MV3 service worker: owns recording state, takes keyframes, batches everything to POST /capture/batch.
import {
  API_BASE,
  ALLOWED_ORIGINS,
  BATCH_POST_S,
  FRAME_AFTER_CLICK_MS,
  FRAME_MAX_WIDTH,
  FRAME_WEBP_QUALITY,
  USER_ID,
  frameDropReason,
  isAllowedOrigin,
  newId,
  urlTemplate,
  type CaptureBatch,
  type CaptureFrame,
  type FrameTrigger,
  type UIEvent,
} from "./lib";

const SESSION_MAX_MS = 30 * 60 * 1000;
const MAX_QUEUED_FRAMES = 60; // if the API is down, keep the newest frames only

interface State {
  recording: boolean;
  localPaused: boolean;
  serverPaused: boolean;
  sessionId: string | null;
  sessionStartedAt: number;
  framesThisSession: number;
  sent: { events: number; framesKept: number; framesDropped: number };
  droppedLocally: Record<string, number>;
  lastError: string | null;
  lastPostAt: number;
}

const state: State = {
  recording: false,
  localPaused: false,
  serverPaused: false,
  sessionId: null,
  sessionStartedAt: 0,
  framesThisSession: 0,
  sent: { events: 0, framesKept: 0, framesDropped: 0 },
  droppedLocally: {},
  lastError: null,
  lastPostAt: 0,
};

let events: UIEvent[] = [];
let frames: CaptureFrame[] = [];
let pendingCaptures = 0;
let lastFrameAt = 0;
let allowedOrigins = [...ALLOWED_ORIGINS];

const restored = chrome.storage.session.get("state").then(({ state: saved }) => {
  if (saved) Object.assign(state, saved);
  updateBadge();
});

function persist() {
  chrome.storage.session.set({ state }).catch(() => {});
}

const capturing = () => state.recording && !state.localPaused && !state.serverPaused;

function updateBadge() {
  const text = !state.recording ? "" : capturing() ? "REC" : "II";
  chrome.action.setBadgeText({ text });
  chrome.action.setBadgeBackgroundColor({ color: capturing() ? "#dc2626" : "#6b7280" });
}

function startSession() {
  state.sessionId = newId("cap");
  state.sessionStartedAt = Date.now();
  state.framesThisSession = 0;
}

function countDrop(reason: string) {
  state.droppedLocally[reason] = (state.droppedLocally[reason] ?? 0) + 1;
}

async function toWebpBase64(dataUrl: string): Promise<string> {
  const bitmap = await createImageBitmap(await (await fetch(dataUrl)).blob());
  const scale = Math.min(1, FRAME_MAX_WIDTH / bitmap.width);
  const canvas = new OffscreenCanvas(Math.round(bitmap.width * scale), Math.round(bitmap.height * scale));
  canvas.getContext("2d")!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  const bytes = new Uint8Array(await (await canvas.convertToBlob({ type: "image/webp", quality: FRAME_WEBP_QUALITY })).arrayBuffer());
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

/** Takes one keyframe of `tabId` if every privacy and budget check passes. Returns the client id or null. */
async function captureFrame(tabId: number, trigger: FrameTrigger, clientId: string): Promise<string | null> {
  if (!capturing()) return null;
  const drop = frameDropReason(trigger, Date.now(), lastFrameAt, state.framesThisSession);
  if (drop) return countDrop(drop), null;

  const tab = await chrome.tabs.get(tabId).catch(() => null);
  // captureVisibleTab shoots the window's active tab, so the tab must be active and still allow-listed.
  if (!tab?.active || !isAllowedOrigin(tab.url, allowedOrigins)) return countDrop("not_allowed"), null;
  const check = await chrome.tabs.sendMessage(tabId, { type: "can_capture" }).catch(() => null);
  if (!check?.ok) return countDrop("sensitive_focus"), null;

  lastFrameAt = Date.now();
  try {
    const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, { format: "jpeg", quality: 85 });
    frames.push({
      client_id: clientId,
      ts: new Date(lastFrameAt).toISOString(),
      trigger,
      app: "chrome",
      window_title: tab.title ?? "",
      url_template: urlTemplate(tab.url!),
      image_webp_b64: await toWebpBase64(dataUrl),
    });
    if (frames.length > MAX_QUEUED_FRAMES) frames.splice(0, frames.length - MAX_QUEUED_FRAMES);
    state.framesThisSession += 1;
    return clientId;
  } catch (err) {
    // Most common cause: activeTab not granted yet — click the toolbar icon on the mock site tab.
    state.lastError = `capture failed: ${(err as Error).message}`;
    countDrop("capture_error");
    return null;
  }
}

async function onUiEvent(tabId: number, event: UIEvent, trigger: FrameTrigger | null) {
  if (!capturing()) return;
  if (Date.now() - state.sessionStartedAt > SESSION_MAX_MS) startSession();
  events.push(event);
  if (!trigger) return;
  const clientId = newId("f");
  event.frame_id = clientId;
  pendingCaptures += 1;
  const delay = trigger === "burst" ? 0 : FRAME_AFTER_CLICK_MS;
  await new Promise((r) => setTimeout(r, delay));
  try {
    event.frame_id = await captureFrame(tabId, trigger, clientId);
  } finally {
    pendingCaptures -= 1;
  }
}

async function api(path: string, init?: RequestInit): Promise<Response> {
  return fetch(API_BASE + path, { ...init, headers: { "Content-Type": "application/json" } });
}

async function pollState() {
  try {
    const res = await api("/capture/state");
    if (!res.ok) return; // endpoint not live yet: local pause still works
    const body = await res.json();
    state.serverPaused = !!body.paused;
    if (Array.isArray(body.allowed_origins) && body.allowed_origins.length) {
      // Server can narrow the manifest allow-list, never widen it.
      allowedOrigins = ALLOWED_ORIGINS.filter((o) => body.allowed_origins.some((b: string) => b.replace(/\/$/, "") === o));
    }
  } catch {
    /* API unreachable; keep last known state */
  }
}

async function flush(force = false) {
  if (!state.sessionId || pendingCaptures > 0) return;
  if (!events.length && !frames.length) return;
  if (!force && Date.now() - state.lastPostAt < BATCH_POST_S * 1000) return;
  const batch: CaptureBatch = { user_id: USER_ID, capture_session_id: state.sessionId, source: "chrome", events, frames };
  events = [];
  frames = [];
  state.lastPostAt = Date.now();
  try {
    const res = await api("/capture/batch", { method: "POST", body: JSON.stringify(batch) });
    if (!res.ok) throw new Error(`${res.status} ${(await res.text()).slice(0, 200)}`);
    const ack = await res.json();
    state.sent.events += ack.ui_events;
    state.sent.framesKept += ack.frames_kept;
    state.sent.framesDropped += ack.frames_dropped;
    if (ack.paused) state.serverPaused = true;
    state.lastError = null;
  } catch (err) {
    state.lastError = `batch failed: ${(err as Error).message}`;
    // Re-queue so a short API outage doesn't lose data.
    events = batch.events.concat(events);
    frames = batch.frames.concat(frames).slice(-MAX_QUEUED_FRAMES);
  }
}

async function setPaused(paused: boolean) {
  state.localPaused = paused;
  await api(`/capture/${paused ? "pause" : "resume"}`, { method: "POST" }).catch(() => null);
  if (!paused) state.serverPaused = false;
}

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  (async () => {
    await restored;
    const tabId = sender.tab?.id;
    const fromAllowedPage = tabId !== undefined && isAllowedOrigin(sender.url, allowedOrigins);
    switch (msg?.type) {
      case "ui_event":
        if (fromAllowedPage) await onUiEvent(tabId, msg.event, msg.trigger);
        break;
      case "tick":
        if (!fromAllowedPage) break;
        await pollState();
        if (msg.heartbeat && capturing()) await captureFrame(tabId, "heartbeat", newId("f"));
        await flush();
        break;
      case "start":
        state.recording = true;
        state.localPaused = false;
        startSession();
        break;
      case "stop":
        await flush(true);
        state.recording = false;
        break;
      case "pause":
        await setPaused(true);
        break;
      case "resume":
        await setPaused(false);
        break;
      case "status":
        await pollState();
        break;
    }
    updateBadge();
    persist();
    reply({ ...state, capturing: capturing(), queued: { events: events.length, frames: frames.length }, allowedOrigins });
  })();
  return true; // async reply
});

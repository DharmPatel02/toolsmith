// Content script: runs only on allow-listed origins (manifest content_scripts.matches).
// Emits UI events with element role/name and value *shape* only; never reads typed content.
import {
  BURST_END_IDLE_MS,
  HEARTBEAT_ACTIVE_WINDOW_S,
  HEARTBEAT_S,
  STATE_POLL_S,
  clip,
  urlTemplate,
  valueShape,
  type ElementInfo,
  type FrameTrigger,
  type UIEvent,
  type UIEventKind,
} from "./lib";

const IMPLICIT_ROLES: Record<string, string> = {
  A: "link",
  BUTTON: "button",
  SELECT: "combobox",
  TEXTAREA: "textbox",
  FORM: "form",
  SUMMARY: "button",
};

const INTERACTIVE = "a,button,input,select,textarea,summary,label,[role],[data-action],[onclick]";

function roleOf(el: Element): string {
  const explicit = el.getAttribute("role");
  if (explicit) return explicit;
  if (el instanceof HTMLInputElement) {
    if (["button", "submit", "reset", "image"].includes(el.type)) return "button";
    if (el.type === "checkbox") return "checkbox";
    if (el.type === "radio") return "radio";
    return "textbox";
  }
  return IMPLICIT_ROLES[el.tagName] ?? el.tagName.toLowerCase();
}

function isSensitive(el: Element | null): boolean {
  if (!(el instanceof HTMLInputElement)) return false;
  return el.type === "password" || /cc-|card|cvc|password|one-time-code/i.test(el.autocomplete);
}

function nameOf(el: Element): string {
  const aria = el.getAttribute("aria-label");
  if (aria) return clip(aria);
  const labelledBy = el.getAttribute("aria-labelledby");
  if (labelledBy) {
    const text = labelledBy
      .split(/\s+/)
      .map((id) => document.getElementById(id)?.textContent ?? "")
      .join(" ");
    if (text.trim()) return clip(text);
  }
  if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement || el instanceof HTMLSelectElement) {
    // Label text, never the value (except button captions, which are UI, not user data).
    if (el.labels && el.labels.length) return clip(el.labels[0].textContent ?? "");
    if (el instanceof HTMLInputElement && ["button", "submit", "reset"].includes(el.type)) return clip(el.value);
    return clip(el.getAttribute("placeholder") || el.name || el.id || "");
  }
  if (el instanceof HTMLFormElement) {
    const submit = el.querySelector("button[type=submit],input[type=submit],button:not([type])");
    return clip(el.name || el.id || (submit ? nameOf(submit) : ""));
  }
  return clip((el as HTMLElement).innerText || el.getAttribute("title") || "");
}

function dataAttrs(el: Element): Record<string, string> {
  const out: Record<string, string> = {};
  for (const attr of Array.from(el.attributes)) {
    if (attr.name.startsWith("data-") && Object.keys(out).length < 5) out[attr.name] = clip(attr.value, 64);
  }
  return out;
}

function describe(el: Element): ElementInfo {
  return { role: roleOf(el), name: nameOf(el), data_attr: dataAttrs(el) };
}

let lastInputAt = 0;

function send(kind: UIEventKind, el: Element | null, trigger: FrameTrigger | null, shape: UIEvent["value_shape"] = null) {
  const event: UIEvent = {
    ts: new Date().toISOString(),
    kind,
    url_template: urlTemplate(location.href),
    element: el ? describe(el) : { role: "document", name: clip(document.title), data_attr: {} },
    value_shape: shape,
    frame_id: null,
  };
  chrome.runtime.sendMessage({ type: "ui_event", event, trigger, title: document.title }).catch(() => {});
}

// Clicks (capture phase so page handlers that stop propagation don't hide them).
document.addEventListener(
  "click",
  (e) => {
    const target = e.target instanceof Element ? e.target.closest(INTERACTIVE) ?? e.target : null;
    if (!target || isSensitive(target)) return;
    lastInputAt = Date.now();
    send("click", target, "click");
  },
  true,
);

document.addEventListener(
  "submit",
  (e) => {
    const form = e.target as HTMLFormElement;
    let len = 0;
    for (const field of Array.from(form.elements)) {
      if ((field instanceof HTMLInputElement || field instanceof HTMLTextAreaElement) && !isSensitive(field)) {
        if (!["button", "submit", "reset", "hidden", "checkbox", "radio"].includes(field.type)) len += field.value.length;
      }
    }
    lastInputAt = Date.now();
    send("submit", form, "click", { len, type: "form" });
  },
  true,
);

// Typing bursts: one event per field after BURST_END_IDLE_MS of quiet. Password fields are ignored.
const burstTimers = new WeakMap<Element, number>();
document.addEventListener(
  "input",
  (e) => {
    const el = e.target;
    if (!(el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) || isSensitive(el)) return;
    lastInputAt = Date.now();
    clearTimeout(burstTimers.get(el));
    burstTimers.set(
      el,
      window.setTimeout(() => {
        const type = el instanceof HTMLInputElement ? el.type : "textarea";
        send("burst_end", el, "burst", valueShape(el.value, type));
      }, BURST_END_IDLE_MS),
    );
  },
  true,
);

// Navigation: initial load + SPA route changes (isolated world can't patch history, so poll href).
let lastHref = location.href;
send("nav", null, "nav");
setInterval(() => {
  if (location.href !== lastHref) {
    lastHref = location.href;
    send("nav", null, "nav");
  }
}, 250);

// Ticks keep the MV3 service worker awake while an allow-listed page is open; it uses them to
// poll /capture/state, flush batches, and take heartbeat frames.
let lastHeartbeat = Date.now();
setInterval(() => {
  const active = Date.now() - lastInputAt < HEARTBEAT_ACTIVE_WINDOW_S * 1000;
  const heartbeat = active && document.visibilityState === "visible" && Date.now() - lastHeartbeat >= HEARTBEAT_S * 1000;
  if (heartbeat) lastHeartbeat = Date.now();
  chrome.runtime.sendMessage({ type: "tick", heartbeat, title: document.title }).catch(() => {});
}, STATE_POLL_S * 1000);

// The service worker asks right before taking a screenshot, since focus can change in the delay.
chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  if (msg?.type === "can_capture") reply({ ok: !isSensitive(document.activeElement) && document.visibilityState === "visible" });
});

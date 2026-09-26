// Toolbar popup. Opening it on the mock site grants activeTab, which captureVisibleTab needs.
const $ = (id: string) => document.getElementById(id)!;

async function send(type: string) {
  const s = await chrome.runtime.sendMessage({ type });
  render(s);
}

function render(s: any) {
  const label = !s.recording ? "Not recording" : s.capturing ? "Recording" : s.serverPaused ? "Paused (from ToolSmith)" : "Paused";
  $("status").textContent = label;
  $("dot").className = "dot" + (s.capturing ? " rec" : "");
  ($("start") as HTMLButtonElement).disabled = s.recording;
  ($("stop") as HTMLButtonElement).disabled = !s.recording;
  const pause = $("pause") as HTMLButtonElement;
  pause.disabled = !s.recording;
  pause.textContent = s.localPaused || s.serverPaused ? "Resume" : "Pause";
  pause.onclick = () => send(s.localPaused || s.serverPaused ? "resume" : "pause");
  $("origins").textContent = s.allowedOrigins.join(", ");
  $("session").textContent = s.sessionId ? `${s.sessionId} · ${s.framesThisSession} frames` : "—";
  $("sent").textContent = `${s.sent.events} events · ${s.sent.framesKept} frames kept · ${s.sent.framesDropped} dropped`;
  $("queued").textContent = `${s.queued.events} events · ${s.queued.frames} frames`;
  const dropped = Object.entries(s.droppedLocally).map(([k, v]) => `${k}: ${v}`).join(", ");
  $("dropped").textContent = dropped || "none";
  $("error").textContent = s.lastError ?? "";
}

$("start").onclick = () => send("start");
$("stop").onclick = () => send("stop");
send("status");
setInterval(() => send("status"), 1000);

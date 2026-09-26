# ToolSmith — Team Task Board v4 · 3-person split (nothing removed)

> Put this file at `docs/TASKS.md` in the repo. Put `plan_final.md` (v4) at `docs/plan_final.md`.
> This file is the single source of truth for **who builds what, in which phase, and how we integrate**.
>
> **What this file is:** the full 4-person v4 board, redistributed across 3 people. **Every task from your original `TASKS.md` is here with its full original scope** (including the five items plan v4 §19.2 wanted to cut — restored, see §4.1), plus every v4 capture-layer task. 96 tasks in total (one previously unnumbered stretch item now has the ID `P3.3.8`).
> Only three things change: **who owns each task**, **which phase some moved tasks land in**, and the timeline / integration pairing for 3 people.
>
> **Task IDs are unchanged** so everything still matches plan v4 §19. A task with a `P4.` ID now belongs to whoever's section it sits in (see the owner map in §1.1). Where task text mentions "P4" as a person, read it as that task's new owner.

---

## 0. How to use this file (read first — humans and agents)

### 0.1 Agent protocol (paste this to your Claude: "I am Person N, follow docs/TASKS.md")

When a teammate tells their Claude **"I am Person N"** (N = 1, 2 or 3), the agent must:

1. Read this whole file, then `docs/plan_final.md` (v4) for background. Section §3 (Contracts) is binding.
2. Go to **Section 5.N (Person N)**. Work only on the **current phase**, top to bottom, on unticked tasks. **Your section includes tasks with other people's ID prefixes (e.g. `P4.x.x`) — they are yours now.**
3. Only create or edit files inside **your owned paths** (§2). If you need a change in someone else's file or in a contract, do **not** edit it — add a line to §8 "Contract change requests" and tell the owner.
4. If something you depend on isn't ready, **don't wait**: use the stub or fixture from §3 and keep going. Log it in your status file.
5. Every task has a **Test** line. A task is done only when that test passes. Then:
   - tick the box: `- [ ]` → `- [x]`
   - append one line to your status file `docs/status/PN.md`: `HH:MM · task ID · done · short note`
   - commit with message `PN: <task ID> <short description>` and push to your branch.
6. At the end of each phase, open a PR from your branch into `main` (see §6). Don't merge other people's PRs without them.
7. Never commit secrets. Keys go in `.env` (git-ignored); only `.env.example` is committed. Screen recordings are git-ignored too.
8. Keep code simple and readable. This is a one-day build: working > clever.
9. **Work in priority order inside each phase: all P0 first, then P1, then ⭐.** Four people's work is now spread over three, so the P0 items are what must land by each integration; P1 and ⭐ items are done in that order as time allows. Nothing is removed — unfinished items just carry into the next phase.

### 0.2 Timeline at a glance (hackathon day, Sep 26)

| Time | Phase | What happens |
|---|---|---|
| Before the event | **Pre-event (no code)** | Rules, keys, Docker, Excel recordings + ground-truth labels, `action_vocab` seed (§4.0). |
| 10:30–10:50 | **Phase 0 — Setup** | P1 pushes repo skeleton + contracts + stubs. P2 and P3 set up tools and folders. |
| 10:50–12:15 | **Phase 1 — Build (independent)** | P1 memory + miner + generator · P2 LLM, embeddings, sandbox, forge, keyframes · P3 **extension first**, mock site, UI pages. |
| 12:15–12:45 | **Integration I-1** | 12:15–12:25 **all three**: extension → Atlas check. Then **I-1a = P1** (+ P2 for 5 min to merge embeddings/keyframes) and **I-1b = P2 + P3** (forge → UI). |
| 12:45–14:00 | **Phase 2 — Build (independent)** | P1 search, runtime, capture ingest + fusion · P2 gate, promotion, trust, **interpreter** · P3 UI wiring, **concierge**, `analyze_idea`. |
| 14:00–14:30 | **Integration I-2 (all three)** | Full loop. **14:30 go/no-go** (includes a screen-derived UC1 pattern in `/suggestions`). |
| 14:30–15:15 | **Phase 3 — Build (independent)** | P1 policy learner, calibration, metrics, eval · P2 heal, **race baseline**, cache · P3 evidence strip, race view, policy strip, demo reset. |
| 15:15–15:35 | **Integration I-3 (all three)** | Final merge, end-to-end demo run. **Code freeze 15:35.** |
| 15:35–16:40 | Demo prep | Bug triage only, rehearse 3×, README + fallback video (P3). |
| 16:40–17:00 | Submit | Repo public, all members added. |

```
Phase 1:    P1        P2    P3
             \          \  /
I-1:   (ext check: all three) → P1 (I-1a) | P2+P3 (I-1b)
               \        /
Phase 2:    P1   P2   P3
               \  |  /
I-2:        all three (go/no-go)
Phase 3:    P1   P2   P3
I-3:        all three (freeze)
```

**Capture layer at a glance (3-person owners):**

| Time | Owner | Capture work |
|---|---|---|
| 10:30–10:50 | P1 | Capture collections, GridFS, TTLs, contract fields, canonical fixtures, `/capture/batch` stub (P1.0.2) |
| 10:50–11:50 | P3 | Chrome extension (P3.1.0), then mock site + UI |
| Phase 1 | P1 | Canonical signature mapper (P1.1.10) |
| Phase 1 | P2 | Embeddings incl. multimodal (P1.1.4), `derivation` (P2.1.8), VLM prompt (P2.1.9), ffmpeg keyframes (P4.1.5) |
| 12:15–12:25 | all | Extension click-through on the mock site → `ui_events` + `frames` in Atlas |
| Phase 2 | P1 | `/capture/batch` real + fusion + `/why` returns frames (P1.2.8, P1.2.9) |
| Phase 2 | P2 | Interpreter Stages A–D (P4.2.5) |
| 14:30 | all | Go/no-go: screen-derived UC1 pattern in `GET /suggestions` with frames behind it |
| Phase 3 | P3 | Evidence strip (P3.3.5), race view (P3.3.7), capture panel (P3.3.6) |
| Phase 3 | P2 | Race baseline (P4.2.6), NN label copy (P4.3.7), `ctx.call` (P2.3.6) |
| Phase 3 | P1 | Capture eval + ablation (P4.3.6), lineage + prune safety (P1.3.5), app-shift segmentation (P1.3.6) |

### 0.3 Scope rules for the day

- Build the **Lean tier only**. Heavy-tier items (LangGraph, HDBSCAN, rerank, gVisor, E2B, Playwright path) are stretch goals marked ⭐ and only after everything else in your phase is ticked.
- Priority tags: **P0** = must have for the demo · **P1** = should have · ⭐ = stretch.
- **Never cut** (plan §13.3): runtime found/not-found with `working_memory` · replay gate · decoy rejection · heal · policy strip · visible vector search (episodic recall + tool lookup) · **the evidence strip** · **the fusion rule that structured data wins** · **pause + allow-list**.
- **Cut order if behind** (first to go → last): MCP export → desktop watcher → Heavy-tier P2 extras → UC2 → merge → `$graphLookup` composition (keep prune safety if done) → NN label copy → OCR click-target resolution (VLM sees raw frames) → episode-chain composition → "related → adapt" path → app-shift segmentation → mining sophistication (hand-tune thresholds).
- **Freeze `action_vocab` during the demo.** An unstable vocabulary silently destroys support counts.

---

## 1. Roles

| Person | Role | Owns (short) |
|---|---|---|
| **P1** | Backend core, memory, mining, runtime, capture ingest **+ data & metrics** | Atlas setup, ingest, `/capture/batch`, fusion, canonical signatures, sessions, miner, search, suggestions + `/why`, runtime, lineage, worker, events, policy learner · **synthetic generator, seeding, calibration, metrics, capture eval + ablation, memory-mode comparison** |
| **P2** | Forge, gate, sandbox, trust **+ all vision / model pipeline work** | LLM client, **embeddings**, VLM prompt, sandbox + `ctx.call`, forge, gate, promotion, trust ladder, heal, prune, merge · **UC1/UC2 artifacts, video → keyframes, interpreter, NN label copy, race baseline, cached generations** |
| **P3** | Frontend + extension **+ concierge + demo assets** | Chrome extension, all Next.js UI · **mock site v1/v2, concierge `/chat` + `analyze_idea` (backend + UI, one full-stack feature), demo reset, README, fallback video** |

Write your real names here: P1 = ______ · P2 = ______ · P3 = ______

**Why this split:** the old P4 work is spread by skill instead of dumped on one person. Things that feed the miner and the numbers go to P1; everything on the vision / keyframe / model pipeline goes to P2; everything visual, static or demo-facing goes to P3, and the concierge goes to P3 because P3 already builds the chat page, so chat becomes one full-stack feature. `embeddings.py` moves from P1 to P2 to balance P1's load.

**Load notes:** P1 and P2 are the fullest. If P1 is behind at I-1, P3 helps with seeding checks; if P2 is behind at 13:45 on the interpreter, P2 hand-labels the UC1 frames in the §3.3 shape so the evidence strip still has real screenshots (and says so on stage).

### 1.1 Owner map for moved tasks

| Task | 4-person owner | 3-person owner | What it is |
|---|---|---|---|
| P1.1.4 | P1 | **P2** | `embeddings.py` — Voyage text + multimodal |
| P4.1.1 | P4 | **P1** | Synthetic history generator |
| P4.1.2 | P4 | **P2** | Real artifacts (xlsx, expected outputs, papers) |
| P4.1.3 | P4 | **P3** | Mock site v1/v2 + switch |
| P4.1.4 | P4 | **P1** | `scripts/seed.py` |
| P4.1.5 | P4 | **P2** | Excel videos → keyframes → `/capture/batch` |
| P4.2.1 | P4 | **P1** | Threshold calibration (~50 pairs) |
| P4.2.2 | P4 | **P1** | `metrics/service.py` + `GET /metrics` |
| P4.2.3 | P4 | **P3** | Concierge `POST /chat` |
| P4.2.4 | P4 | **P3** | `POST /ideas` `analyze_idea` (minimal) |
| P4.2.5 | P4 | **P2** | Interpreter worker (Stages A–D) |
| P4.2.6 | P4 | **P2** | Race baseline agent + `POST /race` |
| P4.3.1 | P4 | **P3** | `scripts/demo_reset.py` |
| P4.3.2 | P4 | **P2** | Pre-compute cached generations (with P2) |
| P4.3.3 | P4 | **P3** | Fallback demo video |
| P4.3.4 | P4 | **P3** | README |
| P4.3.5 | P4 | **P1** | ⭐ Memory-mode comparison |
| P4.3.6 | P4 | **P1** | Capture eval + logs-only vs logs+screen ablation |
| P4.3.7 | P4 | **P2** | Nearest-neighbour label copy |
| P4.pre, P4.0.1 | P4 | **P2** (P1 hand-labels the ground truth) | Recordings, labels, data folders |

---

## 2. Repo layout and ownership

```
toolsmith/
├─ backend/
│  ├─ app/
│  │  ├─ main.py  config.py  contracts.py  db.py  events.py   P1
│  │  ├─ ingest/  capture/  miner/  search.py  suggestions/  runtime/  policy/   P1
│  │  ├─ metrics/             P1  (was P4)
│  │  ├─ embeddings.py        P2  (was P1)
│  │  ├─ llm.py  prompts/  sandbox/  forge/  gate/  trust/   P2
│  │  ├─ interpreter/         P2  (was P4)
│  │  ├─ baseline/            P2  (was P4)
│  │  ├─ concierge/           P3  (was P4)
│  │  └─ routers/  p1_*.py (P1) · p2_*.py (P2) · p3_*.py (P3: chat, ideas, demo/mocksite — was p4_*)
│  ├─ worker.py               P1
│  ├─ tests/p1|p2|p3/         each owner
│  └─ requirements/  base.txt (P1) · p2.txt (P2, incl. interpreter deps) · p3.txt (P3, concierge)
├─ sandbox/Dockerfile         P2
├─ extension/                 P3
├─ web/                       P3
├─ mocksite/v1  mocksite/v2   P3  (was P4)
├─ data/
│  ├─ generator/  seed/       P1  (was P4)
│  ├─ artifacts/              P2  (was P4)
│  ├─ recordings/             P2  (was P4, git-ignored)
│  ├─ ground_truth/           P1  (was P4)
│  └─ action_vocab_seed.json  P1  (was P4)
├─ scripts/  init_db.py, seed.py, calibrate.py, capture_eval.py (P1) · video_to_frames.py (P2) · demo_reset.py (P3)
├─ fixtures/                  P1 (Phase 0)
├─ docs/TASKS.md  docs/plan_final.md  docs/status/P1..P3.md
├─ README.md                  P3
├─ docker-compose.yml  .env.example   P1
```

**Shared-file rule:** `main.py`, `worker.py`, `contracts.py`, `docker-compose.yml`, `base.txt` belong to P1 and are pre-built: `main.py` auto-includes every `app/routers/p*_*.py`; `worker.py` has `register(job_type, handler)` and P2 registers `forge`, `heal`, `interpret` from `app/*/jobs.py`.

---

## 3. Contracts (binding — build against these)

### 3.1 Environment (`.env.example`)

```
MONGODB_URI=mongodb+srv://...
DB_NAME=toolsmith
DEMO_USER_ID=u_1
VOYAGE_API_KEY=
EMBED_MODEL=voyage-3.5          # 1024 dims — verify on the day, one model per index
VOYAGE_MM_MODEL=                # 🆕 Voyage multimodal model for frames — verify name + dims on the day
OPENAI_API_KEY=
OPENROUTER_API_KEY=             # optional; if set, llm.py routes through OpenRouter
LLM_LEAN_MODEL=openai/<cheap-model>
LLM_HEAVY_MODEL=openai/<strong-model>
LLM_VISION_MODEL=openai/<vision-model>   # 🆕 used for batched frame labeling
LLM_CACHE_DIR=.cache/llm
SANDBOX_IMAGE=toolsmith-sandbox:latest
MOCKSITE_URL=http://localhost:8081
CAPTURE_ALLOWED_ORIGINS=http://localhost:8081   # 🆕 extension host permission + server-side check
API_BASE=http://localhost:8000
NEXT_PUBLIC_API_BASE=http://localhost:8000
NEXT_PUBLIC_USE_MOCKS=true
```

### 3.2 Collections (fields as in plan §9)

`observations` (time-series, TTL 60 d) · `sessions` · `patterns` · `tools` · `tool_versions` · `candidates` · `runs` · `verdicts` · `feedback` · `policy` · `profile` · `working_memory` (TTL 2 h) · `conversations` · `jobs` · `events`

**🆕 v4 capture collections:**
- `frames` — **regular** collection (change stream + vector index live here), TTL 7 d on `expires_at`:
  `{_id, user_id, session_id, ts, source: "chrome|video_replay|desktop", app, window_title, url_template, trigger: "click|nav|burst|heartbeat|flag|video_replay", dhash, gridfs_id, thumb: BinData, display: {id, dpi}, ocr: {text, boxes}, click_target: {role, name, box}, embedding: [..], embedding_model, label: {verb, args_shape, confidence, source: "vlm|nn_copy|dom", needs_review}, redactions: [...], expires_at}`
- `ui_events` — T1 stream, no image: `{user_id, session_id, ts, source: "chrome", kind: "click|submit|nav|burst_end", url_template, element: {role, name, data_attr}, value_shape: {len, type}, frame_id}`
- `action_vocab` — `{_id: "table.pivot", status: "candidate|active", aliases: [...], embedding, seen, first_seen, example_frames}` (small; matched in memory, no Atlas index)
- `capture_sessions` — audit: `{user_id, started_at, ended_at, sources, apps_seen, frames_kept, frames_dropped_by_rule: {...}, paused}`
- GridFS bucket **`keyframes`** — 1280 px WebP q70 keyframes.

**✏️ Changed fields on existing collections:**
- `observations.evidence = {frame_ids: [...], ocr_snippet, tier: "T0|T1|T2", confidence}`
- `observations.meta.source = "chrome|excel|pandas|concierge|..."` — the **app lives here**; `signature` is canonical.
- `tool_versions.derivation = {observed_tier, execution_path: "api|browser|cli|assisted"}`
- `tools.lineage = {calls: [tool_id], parents, merged_from, merged_into}`

Added for the build (unchanged from v3):
- `candidates` — forged-but-not-approved tool versions: `{_id, user_id, pattern_id|idea_id, spec, code, tests, tutorial_md, params_schema, requires, derivation, verdict_id, status: "gating|passed|failed|approved|rejected", created_at}`
- `jobs` — `{_id, type: "mine"|"forge"|"heal"|"prune"|"consolidate"|"interpret", payload, status: "queued|running|done|failed", error, created_at}`
- `events` — `{_id, ts, user_id, type, data}` (the SSE feed tails this)

**Indexes:** TTL on `working_memory.expires_at` and `frames.expires_at`; `{user_id, status, value:-1}` on patterns; `{user_id, name}` unique on tools; `{tool_id, started_at:-1}` on runs; `frames {user_id, session_id, ts}`; `ui_events {user_id, ts:-1}` + `{url_template}`; `tools {"lineage.calls": 1}`.

**Search-index budget (priority order):** 1 `tools_vec` · 2 `sessions_vec` · 3 `tools_text` · 4 `frames_vec` · 5 `patterns_vec`. If the tier caps the count, keep the first three, do NN label copy client-side in numpy over the user's last 7 days of labeled frames, and drop `patterns_vec`.

### 3.3 Python interfaces (function signatures — stubs exist from Phase 0)

**P1 provides** *(3-person: `embeddings.py` is built by P2 — task P1.1.4 moved)*
```python
# app/embeddings.py
async def embed(texts: list[str], input_type: str = "document") -> list[list[float]]
async def embed_multimodal(items: list[dict]) -> list[list[float]]     # 🆕 item = {image_bytes, text}; VOYAGE_MM_MODEL
# app/search.py
async def search_tools(user_id: str, query: str, k: int = 5) -> list[ToolHit]      # ToolHit{tool_id, name, score}
async def recall_episodes(user_id: str, query: str, k: int = 5) -> list[EpisodeHit] # EpisodeHit{session_id, date, intent_summary, minutes, tokens, score}
# app/miner/signatures.py  🆕
def to_signature(verb: str, args_shape: dict) -> str   # canonical "domain.verb:argshape" via action_vocab (aliases resolved)
# app/capture/service.py  🆕
async def ingest_capture_batch(user_id: str, batch: CaptureBatch) -> CaptureAck      # CaptureAck{ui_events, frames_kept, frames_dropped, paused}
async def fuse(user_id: str, session_id: str) -> int    # fusion rule §3.5b; returns observations written
# app/runtime/service.py
async def run_by_intent(user_id: str, intent: str, inputs: dict) -> RunResult      # found / related / not_found
async def run_tool(user_id: str, tool_id: str, params: dict, confirm: bool = False) -> RunResult
# app/runtime/lineage.py  🆕
async def resolve_deps(user_id: str, tool_id: str) -> list[ToolDep]   # $graphLookup; fail closed if a dep is missing
async def dependents(user_id: str, tool_id: str) -> list[str]         # reverse lookup for prune safety
# app/policy/service.py
async def get_policy(user_id: str) -> PolicyDoc
async def record_change(user_id: str, field: str, new, direction: str, because: str, origin_ids: list[str]) -> PolicyChange
# app/events.py
async def publish(user_id: str, type: str, data: dict) -> None
```

**P2 provides**
```python
# app/llm.py
async def complete(tier: Literal["lean","heavy","vision"], messages: list[dict], json_schema: dict | None = None) -> LLMResult
# LLMResult{text, json, tokens_in, tokens_out, usd, model, cached}; "vision" accepts image content parts, uses LLM_VISION_MODEL
# app/prompts/label_frames.py  🆕
LABEL_FRAMES_PROMPT: str; LABEL_FRAMES_SCHEMA: dict   # P2 writes and calls via complete("vision", ...)  (3-person: P2 owns the interpreter)
# app/sandbox/runner.py
async def run_in_sandbox(code: str, entry: str, params: dict, inputs: dict[str, str], mode: Literal["dry_run","live"],
                         scopes: list[str], timeout_s: int = 30, deps: dict[str, str] | None = None) -> SandboxResult
# SandboxResult{ok, output: dict, intended_writes: list[Write], stdout, error, duration_ms}
# deps 🆕 = {tool_name: code} mounted as tools/<name>.py so ctx.call works
# app/forge/service.py
async def forge_from_pattern(pattern_id: str) -> str   # returns candidate_id; publishes forged / gate_passed / gate_failed
async def forge_from_spec(user_id: str, spec: ToolSpec, origin: dict) -> str
# app/gate/service.py
async def run_gate(candidate_id: str) -> Verdict
# app/trust/service.py
async def promote(candidate_id: str, user_id: str) -> str   # returns tool_id, in ONE transaction
async def update_after_run(run: Run) -> None               # trust ladder
async def check_drift(tool_id: str) -> bool                 # True if drift → queues heal job
```

**Formerly "P4 provides"** — 3-person owners: interpreter + baseline → **P2** · metrics → **P1** · concierge + `analyze_idea` → **P3**
```python
# app/interpreter/service.py  🆕
async def interpret_session(user_id: str, session_id: str) -> list[Observation]   # Stages A–D; publishes frame_labeled
# app/baseline/service.py  🆕
async def run_baseline(user_id: str, intent: str, inputs: dict, race_id: str) -> BaselineResult  # not_found path on purpose; publishes race_step
# app/metrics/service.py
async def compute_metrics(user_id: str) -> Metrics
# app/concierge/service.py
async def chat(user_id: str, conversation_id: str | None, message: str) -> ChatReply  # ChatReply{conversation_id, reply, tool_calls, cards}
async def analyze_idea(user_id: str, text: str) -> IdeaAnalysis  # {covered_by_tool_id|None, feasible, scopes, deps, est_minutes_saved_week, spec|None}
```

**`ToolSpec` ✏️** now includes `derivation: {observed_tier: "T0|T1|T2", execution_path: "api|browser|cli|assisted"}` and may return `not_automatable: {reason}` instead of code.

**Tool code contract (what the forge generates, what the sandbox runs):**
```python
def run(ctx, **params) -> dict:
    df = ctx.read_table("file")        # inputs are named; ctx maps names to mounted read-only files
    html = ctx.fetch(url)              # only if "net:<domain>" is in scopes, else raises
    part = ctx.call("extract_method", pdf=...)   # 🆕 calls a dependency tool mounted as a module (composed tools only)
    ctx.write_output("dashboard.html", html_string)   # in dry_run: recorded as intended write, not written
    return {"summary": ..., "tables": {...}, "chart_spec": {...}}
```
Allowed imports: `pandas, numpy, openpyxl, json, re, math, statistics, datetime, collections, itertools, bs4, lxml, plotly` (P2 may extend via §8).

**VLM labeling output contract** (P2.1.9): every step must cite a `frame_id`; `verb` must be in `action_vocab` or be `"other"` with a proposed verb; confidence < 0.6 → `needs_review: true` (never counts toward support until confirmed).
```json
{"steps":[
  {"frame_id":"f_101","app":"excel","verb":"file.open","target":{"kind":"file","name":"sales_w1.xlsx"},"args_shape":{"ext":"xlsx"},"confidence":0.93},
  {"frame_id":"f_104","app":"excel","verb":"table.pivot","target":{"kind":"range","name":"A1:F220"},"args_shape":{"rows":"Region","values":"Sales"},"confidence":0.81}
]}
```

### 3.4 HTTP API

| Method + path | Owner | Response (JSON) |
|---|---|---|
| `POST /observations/bulk` | P1 | `{inserted, sessions_touched}` — body: `{user_id, events: [Observation]}` |
| 🆕 `POST /capture/batch` | P1 | `CaptureAck{ui_events, frames_kept, frames_dropped, paused}` — body: `{user_id, capture_session_id, source, events: [UIEvent], frames: [{client_id, ts, trigger, app, window_title, url_template, image_webp_b64}]}` |
| 🆕 `GET /frames/{id}/thumb` | P1 | `image/webp` (256 px) |
| 🆕 `GET /capture/sessions` | P1 | audit list from `capture_sessions` (P1 priority) |
| 🆕 `GET /capture/state` · `POST /capture/{pause\|resume}` · `POST /capture/delete_last?minutes=5` | P1 | `{paused, allowed_origins}` / `{ok}` / `{deleted_frames, deleted_events}` (P1 priority; extension polls state every 2 s) |
| `GET /suggestions` | P1 | `[{pattern_id, title, reason, support, distinct_days, est_minutes_saved_week, value, signature, dynamic_params}]` |
| `GET /suggestions/declined` | P1 | same shape + `declined_reason` (decoys show here) |
| ✏️ `GET /suggestions/{id}/why` | P1 | `{episodes: [EpisodeHit], frames: [{frame_id, ts, thumb_url, verb}]}` |
| `POST /suggestions/{id}/accept\|decline\|snooze` | P1 | `{ok, job_id?}` — decline body: `{reason, never_for_scope?}` |
| `GET /candidates/{id}` | P2 | candidate doc + verdict (+ `derivation`) |
| `POST /candidates/{id}/approve\|reject` | P2 | `{tool_id}` / `{ok}` |
| `POST /dev/forge` | P2 | `{candidate_id}` — body: `{pattern: Pattern}` (dev-only, used in I-1b) |
| `GET /tools` | P1 | `[{tool_id, name, title, status, trust, runs, success_rate, p50_ms, minutes_saved}]` |
| `GET /tools/{id}` | P1 | tool + active version (tutorial_md, params_schema, requires, derivation) |
| 🆕 `GET /tools/{id}/lineage` | P1 | `{calls: [...tree with depth], merged_from, merged_into, dependents}` |
| `GET /tools/{id}/versions` · `POST /tools/{id}/rollback` | P1 | list / `{ok}` |
| `POST /tools/{id}/run` | P1 | `RunResult{run_id, mode, output, intended_writes, needs_confirm, duration_ms, tokens}` |
| `POST /run` | P1 | `RunResult` + `{route: "found"\|"related"\|"not_found", tool_id?, score}` — body `{intent, inputs}` |
| 🆕 `POST /race` | P2 | `{race_id}` — body `{intent, inputs}`; starts `run_baseline` and `run_by_intent` side by side, both stream `race_step` |
| `POST /tools/{id}/feedback` | P1 | `{ok}` |
| `GET /policy` · `POST /policy/changes/{id}/approve` | P1 | `PolicyDoc` / `{ok}` |
| `POST /consolidate` | P1 | `{job_id}` |
| `GET /events` (SSE) | P1 | stream of `{type, ts, data}` |
| `POST /chat` | P3 | `ChatReply` |
| `POST /ideas` | P3 | `IdeaAnalysis` |
| `GET /metrics` | P1 | `Metrics` (see 3.6) |
| `POST /demo/mocksite/{v1\|v2}` | P3 | `{active}` — flips mock site layout for the heal demo |

**SSE event types:** `suggestion_new · forge_started · forged · gate_passed · gate_failed · promoted · run_completed · trust_changed · drift_detected · healed · pruned · policy_changed` + 🆕 `frame_labeled · capture_paused · race_step`
- `race_step.data = {race_id, side: "baseline"|"tool", step, label, tokens, elapsed_ms, done}`

### 3.5 Default policy (seeded by P1)

```json
{ "_id": "policy:u_1", "version": 1,
  "thresholds": { "min_support": 3, "min_distinct_days": 2, "max_variance": 0.35, "max_burstiness": 0.8,
    "merge_similarity": 0.90, "T_high": 0.82, "T_low": 0.65, "max_suggestions_per_day": 3,
    "cooldown_days": [7, 14, 30],
    "promote": { "dry_run_confirms": 3, "success_streak": 8, "max_edit_rate": 0.1 },
    "prune": { "min_runs_30d": 2, "min_success_rate": 0.6 } },
  "rules": [], "changes": [] }
```
(`T_high`/`T_low` are placeholders until P1 calibrates (P4.2.1, Phase 3 in the 3-person split).)

### 3.5b 🆕 Capture constants (`config.py`, not in policy — do not tune during the demo)

| Constant | Value | Used by |
|---|---|---|
| `MAX_FRAMES_PER_SEC` | 1 (Chrome `captureVisibleTab` caps at 2/s) | extension (P3) |
| `MAX_FRAMES_PER_SESSION` | 300 per 30 min; drop heartbeat frames first | extension, ingest |
| `FRAME_AFTER_CLICK_MS` | 400 | extension |
| `BURST_END_IDLE_MS` | 800 | extension |
| `HEARTBEAT_S` | 5, only if input in last 30 s | extension |
| `BATCH_POST_S` | 5 | extension |
| `DHASH_MAX_HAMMING` | 6 | interpreter Stage A |
| `REGION_DIFF_MIN` | 0.02 (2 %) | interpreter Stage A |
| `FUSION_WINDOW_S` | 1.5 | fusion (P1) |
| `NN_LABEL_COPY_MIN` | 0.93 | interpreter Stage C |
| `VLM_BATCH` | 6–10 frames per call | interpreter Stage C |
| `VLM_MIN_CONFIDENCE` | 0.6 (below → `needs_review`) | interpreter, fusion |
| `VOCAB_ALIAS_MIN` / `VOCAB_PROMOTE_AFTER` | 0.88 / 3 sightings | interpreter Stage D |
| `FRAMES_TTL_DAYS` / `OBS_TTL_DAYS` | 7 / 60 | init_db |

**Fusion rule (binding):** T0/T1 and T2 steps within ±1.5 s describe the same moment → the structured step wins and the frame id goes into `observation.evidence`. A T2-only step becomes an observation with `evidence.tier: "T2"` + confidence. Screens never overwrite exact data; `needs_review` steps never count toward support.

### 3.6 Fixtures (P1 commits these in Phase 0 under `fixtures/`, everyone mocks with them)

`fixtures/pattern_uc1.json` ✏️ (canonical signatures)
```json
{ "_id": "pat_uc1", "user_id": "u_1", "status": "proposed",
  "title": "Weekly sales dashboard from Monday xlsx",
  "signature": ["file.open:xlsx","table.rename:cols","table.dropna","table.cast","table.pivot:2col","chart.bar","export.html"],
  "static_steps": {"rename_map": {"reg": "Region", "amt": "Amount"}, "pivot": {"index": "Region", "values": "Amount", "aggfunc": "sum"}},
  "dynamic_params": [{"name": "file", "type": "file"}, {"name": "week", "type": "string"}],
  "support": 3, "distinct_days": 3, "variance": 0.08, "periodicity": 0.9, "burstiness": 0.1,
  "avg_minutes": 9, "avg_tokens": 18000, "value": 22.4,
  "evidence_session_ids": ["s_w1_mon", "s_w2_mon", "s_w3_mon"] }
```
🆕 `fixtures/capture_batch.json` — 3 `ui_events` (click, submit, nav) + 2 small WebP frames from the mock site.
🆕 `fixtures/why_uc1.json` — `{episodes: [3 Mondays], frames: [3 frames, 3 different days, with verbs]}`.
🆕 `fixtures/race.jsonl` — a recorded sequence of `race_step` events (baseline ~15 steps, tool 1–2 steps).
🆕 `fixtures/lineage_uc2.json` — composed tool with 2 deps.
`fixtures/tool_uc1.json`, `fixtures/run_result.json`, `fixtures/policy.json`, `fixtures/events.jsonl` — same shapes as §3.4.
✏️ `fixtures/metrics.json` gains: `ablation {logs_only: {workflows, false_suggestions}, logs_plus_screen: {...}}`, `capture_quality {step_recall, signature_precision, boundary_ok, pattern_recall, noise}`, `cost_to_observe_usd_day`, `race {baseline: {steps, seconds, tokens}, tool: {...}}`.
P3 copies all of them into `web/mocks/`.

---

## 4. Setup

### 4.0 Pre-event (no project code — data prep and checks only)

- [ ] **ALL.pre.1** Confirm event rules: which problem statement, "code on the day" rule, **whether Streamlit is allowed as a fallback**, team size, **whether pre-recorded screen sessions count as data prep**.
- [ ] **ALL.pre.2** Atlas tier features (plan §9 list), LLM + Voyage keys, Docker on every laptop with a practiced `network_mode=none` run. Licenses checked: `prefixspan`, LiteLLM.
- [ ] **P4.pre** Record the UC1 Excel workflow 3 times (weeks 1–3 files, ~5 min each) + one 20-min ground-truth recording labeled step by step (~60 steps → `data/ground_truth/gt_steps.json`); write the ~30-verb `data/action_vocab_seed.json`; draft the VLM labeling prompt text for P2. **P0**
  *Test:* files and labels ready to commit under `data/` on the day.
- [ ] **P3.pre** Load an unpacked test extension in Chrome on the demo laptop once (developer mode + permissions work).
- [ ] **ALL.pre.3** Agree the canonical-signature contract change and the §8 list below. Storyboard the 3-min demo.

> 3-person owners: **P4.pre → P2** records the Excel sessions and drafts the VLM prompt; **P1** hand-labels the ground truth and writes the `action_vocab` seed.
> If you are already on the day and this wasn't done (plan A8): P2 records during 10:30–11:00 and P1 labels only 10 minutes of ground truth.

### 4.1 No cuts — every original feature is kept

Plan v4 §19.2 proposed five cuts to pay for the capture work. **This board does not apply them** — all five are restored to their original scope and priority, on top of every v4 capture feature:

| Item | Plan v4 §19.2 wanted | This board |
|---|---|---|
| P1.3.3 Consolidation job | ⭐ | **P1 (original)** + "Run consolidation" button back in P3.3.3 |
| P3.3.4 Vercel deploy | ⭐ | **P1 (original)** |
| P3.3.2 Metrics page | 4 charts | **All 6 original charts + the ablation chart** |
| P4.2.1 Calibration | ~30 pairs | **~50 pairs (original)** |
| P4.2.4 `analyze_idea` | Minimal, forge hop P1 | **Original text: confirm → `forge_from_spec` included, P0 (minimal)** |

Because nothing is cut, the priority rule in §0.1 item 9 matters: P0 first, then P1, then ⭐ inside each phase.

### 4.2 Phase 0 — Setup (10:30–10:50) — everyone

- [ ] **ALL.0.1** Everyone: GitHub access, Atlas access, `.env` filled locally, Docker running, Python 3.11, Node 20.
- [ ] **ALL.0.2** Everyone creates `docs/status/PN.md` with a first line `10:3x · setup · started`.
- [x] **P1.0.1** Create repo skeleton exactly as §2, with `contracts.py` (Pydantic models for every shape in §3), all stub functions from §3.3 returning fixture data, `main.py` router auto-discovery, `worker.py` job registry, `docker-compose.yml`, `.env.example`, `fixtures/`. **Push to `main` by 10:50.**
  *Test:* `uvicorn app.main:app` starts; `GET /tools` returns the fixture; `pytest` runs (0 tests OK).
- [ ] 🆕 **P1.0.2** Collections `frames` (regular), `ui_events`, `action_vocab`, `capture_sessions`; GridFS bucket `keyframes`; TTL 7 d on frames; contracts gain `Observation.evidence`, `ToolVersion.derivation`, `tools.lineage.calls`, `ToolSpec.derivation`; fixtures switch to canonical signatures; capture constants §3.5b in `config.py`; `POST /capture/batch` stub. **P0**
  *Test:* stub accepts `fixtures/capture_batch.json` and returns a `CaptureAck`.
- [ ] **P2.0.1** Install Docker SDK, pull `python:3.11-slim`, confirm `network_mode=none` container runs.
- [ ] **P4.0.1** Start `data/generator/` skeleton; commit `data/ground_truth/`, `data/action_vocab_seed.json` (recordings stay git-ignored, shared by drive/USB); confirm `ffmpeg` is installed.
- [ ] **P3.0.1** `npx create-next-app web` (TypeScript, Tailwind, App Router) + shadcn/ui init; create `extension/` folder with an MV3 `manifest.json` skeleton.

> 3-person owner: **P4.0.1 → P2** (creates the data folders and checks ffmpeg; P1 fills the generator in Phase 1).

After P1 pushes: everyone `git pull`, then create your branch: `p1-core`, `p2-forge`, `p3-web`.

---

## 5. Task lists per person

### 5.1 Person 1 — Backend core, memory, mining, runtime, capture ingest, data & metrics

#### Phase 1 (10:50–12:15)
- [ ] ✏️ **P1.1.1** `db.py`: async PyMongo client + GridFS bucket; `scripts/init_db.py` creates all collections (incl. capture ones), `observations` as time-series (`timeField: ts`, `metaField: meta`, `expireAfterSeconds: 5184000`), TTL on `working_memory.expires_at` and `frames.expires_at`, indexes from §3.2; loads `data/action_vocab_seed.json` into `action_vocab`. Idempotent. **P0**
  *Test:* run twice, no errors; collections visible in Atlas; `action_vocab` has ~30 docs.
- [ ] ✏️ **P1.1.2** Verify Atlas tier features and write results in `docs/status/P1.md`: `db.version()` ≥ 8.1, `$rankFusion` with `$vectorSearch` works, how many search indexes the tier allows (decides `frames_vec`), change stream on `sessions` and `frames` works, Voyage multimodal model name + dimension, GridFS write + read round trip. **P0**
  *Test:* a tiny script prints OK/FAIL for each.
- [ ] ✏️ **P1.1.3** Create search indexes in the §3.2 priority order: `tools_vec`, `sessions_vec`, `tools_text`, then `frames_vec` and `patterns_vec` only if the tier allows. All vector indexes filter on `user_id` (+ `status` where relevant). **P0**
  *Test:* indexes show READY in Atlas; status file says which ones were skipped.
- [x] 🆕 **P1.1.10** Canonical signature mapper `miner/signatures.py`: `domain.verb:argshape` from `action_vocab` (resolve aliases; unknown verbs → `other` + logged). Deterministic map for T0/T1 sources (pandas, concierge, extension). **P0**
  *Test:* an Excel pivot (`{app: excel, verb: "insert pivottable"}`) and a pandas `pivot_table` both map to `table.pivot:2col`.
  *P1 note:* Offline acceptance covered by `backend/tests/p1/test_phase1.py`; live Atlas vocabulary refresh remains under P1.1.1/P1.1.2.
- [x] ✏️ **P1.1.5** Ingest `POST /observations/bulk`: normalize, regex redaction (keys, emails, tokens), keep `args_shape`, map to **canonical** `signature` via `to_signature` (P1.1.10) with the app in `meta.source`, insert into `observations`, upsert `sessions` (append to `signature_seq`, `artifacts`). **P0**
  *Test:* post `fixtures/events.jsonl` sample → observations inserted, secrets replaced with `<REDACTED>`, signatures canonical.
  *P1 note:* Ingestion uses `fixtures/observations.jsonl`; `events.jsonl` remains the SSE fixture.
- [x] **P1.1.6** Sessionizer: close a session after a 30-min gap (batch mode for seeded data, live mode for new events); on close compute `intent_summary` (join of intent texts, or `llm.complete("lean")` stub), `intent_embedding`, minutes, tokens. **P0**
  *Test:* 2 bursts 1 h apart → 2 closed sessions with embeddings.
- [x] **P1.1.7** Miner `miner/prefixspan.py`: custom PrefixSpan, length 3–8, `min_support` from policy, max-gap constraint. **P0**
  *Test:* unit test on toy sequences finds the planted sequence and not the random ones.
- [x] ✏️ **P1.1.8** Miner `miner/features.py`: intent clustering (sklearn agglomerative, cosine), static/dynamic split (diff arg values across occurrences; for UI steps, element role + name that never change = static anchors, typed values / file names / URLs that change = parameters), window stats (distinct days, inter-arrival median/MAD → periodicity, burstiness), variance. Ignore `needs_review` observations. **P0**
  *Test:* weekly occurrences → periodicity high; 6 runs on one day → burstiness ≥ 0.8; a `needs_review` step does not add support.
- [x] **P1.1.9** Scoring + hard gates (plan §6.1.2) → write `patterns` with status `mined` or `declined` + `declined_reason` (`"one-day burst"`, `"high variance"`, `"low support"`). Seed default policy (§3.5). **P0**
  *Test:* run miner on fixture sessions → correct statuses.
- [x] ✏️ **P4.1.1** Generator `python -m data.generator --out data/seed`: persona (analyst), 3 weeks, ~40 sessions, ~1,000 events in the `Observation` shape with **canonical signatures** and `meta.source`. Plants: **UC1** weekly on Mondays (different file each week), **UC3** daily chain (scrape → analyze → report), **UC2** irregular semantic ("understand this paper"), **decoy A** one-day binge (6 runs, one day), **decoy B** high-variance workflow, plus noise sessions. Writes `ground_truth.json`. Also a **logs-only** variant of the history (UC1 screen steps removed) for the ablation. **P0**
  *Test:* counts match; each planted workflow appears on the expected days.
- [x] **P4.1.4** `scripts/seed.py`: posts `data/seed/*.jsonl` to `/observations/bulk` in batches; `--reset` clears the demo user; `--logs-only` seeds the ablation variant into a second user id. **P0**
  *Test:* against P1's stub endpoint returns counts.
  *P1 note:* Verified against the ASGI app in fixture mode; live reset is guarded to demo users only.

#### ⇄ I-1 (12:15–12:45): extension check with everyone, then I-1a — see §6.2

#### Phase 2 (12:45–14:00)
- [ ] **P1.2.1** `search.py`: `search_tools` via `$rankFusion` (vector + text), filtered by `user_id` + `status: active`; client-side RRF fallback if `$rankFusion` failed in P1.1.2; `recall_episodes` via `$vectorSearch` on `sessions`; structural query on `signature`. **P0**
  *Test:* insert 3 fake tools → a paraphrased query ranks the right one first.
- [ ] ✏️ **P1.2.4** `worker.py`: change streams on `sessions` (closed → queue mine), `jobs` (dispatch to registered handler), `runs` (call `trust.check_drift` hook), **`frames` (new frames → queue one `interpret` job per session, debounced ~5 s)**. **P0**
  *Test:* inserting a forge job calls the registered handler (P2 stub logs it); inserting 3 frames queues exactly 1 interpret job.
- [ ] **P1.2.5** `events.py` + `GET /events` SSE (tail `events` collection change stream, filter by user). **P0**
  *Test:* `curl -N /events` shows an event after `publish()`.
- [ ] 🆕 **P1.2.8** `/capture/batch` real: reject origins not in `CAPTURE_ALLOWED_ORIGINS`; write `ui_events`; frames → keyframe to GridFS + thumbnail inline + `frames` doc; update `capture_sessions` counts; then `fuse()` per §3.5b (±1.5 s, structured wins, frame as evidence). Also `GET /capture/state`, `POST /capture/{pause|resume}` (publishes `capture_paused`), `POST /capture/delete_last` (P1 priority for the last three). **P0**
  *Test:* a T1 click and a T2 frame 0.8 s apart → **one** observation with `evidence.frame_ids`; a frame from a non-allow-listed origin is refused.
- [ ] **P1.2.2** Recheck gate (plan §6.1.3) + `GET /suggestions`, `GET /suggestions/declined`, `GET /suggestions/{id}/why` (episodes; frames added in P1.2.9). **P0**
  *Test:* pattern already covered by a tool → not suggested; budget of 3/day respected.
- [ ] 🆕 **P1.2.9** `/suggestions/{id}/why` returns `frames` (from the pattern's evidence sessions, one per day, with verb); `GET /frames/{id}/thumb`. **P0**
  *Test:* UC1 "why" returns ≥ 3 frames from 3 different days.
- [ ] **P1.2.3** `POST /suggestions/{id}/accept|decline|snooze`: accept → insert `jobs{type:"forge"}`; decline → `feedback` + exponential cooldown; `never_for_scope` → `policy.rules` entry via `record_change` (tighten, auto). **P0**
  *Test:* decline with never_for_scope → rule appears in `GET /policy`, change logged.
- [ ] **P1.2.6** Runtime: `POST /tools/{id}/run` and `POST /run` (found ≥ `T_high` → create `working_memory {static, dynamic, expires_at}` → `run_in_sandbox` at the tool's trust level → write `runs` → `update_after_run` → publish `run_completed`; related → return route + closest tool; not_found → log a session). **P0**
  *Test:* with P2 stubs, a found request creates `working_memory` and `runs` docs.
- [ ] **P1.2.7** `GET /tools`, `GET /tools/{id}`, versions, rollback. **P0**
  *Test:* returns shapes from §3.4.

#### ⇄ Integration I-2, all three (14:00–14:30) — see §6.3

#### Phase 3 (14:30–15:15)
- [ ] **P1.3.1** Policy learner (plan §8.3 rules) running every N minutes in the worker (compressed for demo); tighten = applied, loosen = pending; `POST /policy/changes/{id}/approve`; publish `policy_changed`. **P0**
  *Test:* force prune rate > 0.5 → `min_support 3 → 4` appears with a `because` text.
- [ ] **P4.2.1** Label ~50 (intent, correct tool or none) pairs from the generator's ground truth; `scripts/calibrate.py` sweeps `T_high`/`T_low`/`merge_similarity` using `search_tools`, picks the best F1 for "found", writes them into `policy` via `record_change` (origin `calibration`). **P0**
  *Test:* prints the F1 table; policy updated.
- [ ] ✏️ **P4.2.2** `metrics/service.py` + `GET /metrics`: detection P/R/F1 vs ground truth + decoy false-positive rate, minutes saved/week, tokens before vs after, break-even `C_synth / (C_agent − C_tool)`, replay pass rate and repair loops from `verdicts`, toolbox size over time, time-to-heal, race numbers, cost to observe. **P0**
  *Test:* matches `fixtures/metrics.json` shape; numbers are computed, not hard-coded.
- [ ] 🆕 **P4.3.6** `scripts/capture_eval.py`: on the ground-truth recording → step recall (≥ 0.85), signature precision (≥ 0.80), segment boundaries within ±1 step, pattern recall (3/3), noise suggestions (0); plus **logs-only vs logs + screen ablation** (miner run twice: workflows found, false suggestions) → exposed in `/metrics`. **P0**
  *Test:* numbers computed, not hard-coded.
- [ ] **P1.3.2** Feedback → miner: rejected patterns become negative examples (skip similar ones during cooldown); edited-before-approval stores a parameter hint. **P1**
  *Test:* a declined pattern is not re-suggested during cooldown.
- [ ] 🆕 **P1.3.5** `runtime/lineage.py`: `$graphLookup` dependency tree (`maxDepth 4`, `restrictSearchWithMatch {user_id, status: active}`) used by the runtime to pass `deps` to the sandbox; **fail closed** if resolved deps < names in `lineage.calls` (queue a forge job to re-point at `merged_into`); reverse lookup `dependents()` blocks pruning of depended-on tools (P2's prune calls it); `GET /tools/{id}/lineage`. **P1**
  *Test:* composed tool resolves 2 deps; pruning a dependency is refused with a reason logged on the policy strip.
- [ ] 🆕 **P1.3.6** App-shift segmentation: split a session when focus moves > 3 min to an app not seen in the segment **and** intent cosine < 0.5. **P1**
  *Test:* a Spotify detour splits the session; a quick glance does not.
- [ ] **P1.3.3** `POST /consolidate` job: summarize closed sessions, promote repeated facts into `profile`, decay idle patterns, re-mine the full window. **P1** *(restored to original priority)*
  *Test:* after running, `profile` has at least 1 fact (e.g. column naming style).
- [ ] ⭐ **P1.3.4** Related → adapt path: send closest tool + new intent to `forge_from_spec`.
- [ ] ⭐ **P4.3.5** Memory-mode comparison (plan §15): same 10 tasks, no memory vs ToolSmith tools → success, steps, tokens.

---

### 5.2 Person 2 — Forge, gate, sandbox, trust, embeddings, interpreter, race baseline

#### Phase 1 (10:50–12:15)
- [ ] ✏️ **P2.1.1** `llm.py`: LiteLLM wrapper with `lean` / `heavy` / **`vision`** tiers (OpenAI models; OpenRouter if `OPENROUTER_API_KEY` set); `vision` accepts image content parts; JSON-schema structured output; disk cache keyed by hash of (model, messages, schema); returns tokens + cost. **P0**
  *Test:* same call twice → second is `cached: true`; JSON output validates against schema; a 1-image vision call returns JSON.
- [ ] ✏️ **P1.1.4** `embeddings.py` with Voyage: `embed` (batch up to 128) + `embed_multimodal` (image + text); store `embedding_model` on docs. **P0**
  *Test:* embed 3 strings → 3 vectors of expected length; 1 image + text → 1 vector of the multimodal dimension.
- [ ] **P2.1.2** `sandbox/Dockerfile`: python:3.11-slim + allowed packages (§3.3), non-root user, no network by default. Build as `toolsmith-sandbox:latest`. **P0**
  *Test:* `docker run --network none` imports pandas fine, `curl` fails.
- [ ] **P2.1.3** `sandbox/harness.py` (the `ctx` object: `read_table`, `read_text`, `fetch` with scope check, `write_output` recording intended writes in dry_run) + `runner.py` (Docker SDK: `network_mode=none` unless a `net:` scope, read-only root FS, tmpfs `/tmp`, 512 MB, 30 s timeout, inputs mounted read-only, result read from a JSON file). **P0**
  *Test:* a hand-written tool on a small xlsx returns a pivot; dry_run returns `intended_writes` and writes nothing; an infinite loop is killed at 30 s.
- [ ] **P2.1.4** Forge spec step: prompt → `ToolSpec` JSON `{name, purpose, params_schema, outputs, requires:{scopes, deps, tools}, keywords, derivation}` grounded on the pattern's static/dynamic split and 2–3 evidence sessions. **P0**
  *Test:* `fixtures/pattern_uc1.json` → valid spec with params `file`, `week`.
- [ ] 🆕 **P2.1.8** `derivation {observed_tier, execution_path}` in `ToolSpec`; forge prompt **prefers the API path** ("seen in Excel, runs on pandas"); supports `assisted` and `not_automatable {reason}` outcomes; never coordinates. **P0**
  *Test:* UC1 spec from a T2 pattern chooses `api`.
- [ ] **P2.1.5** Forge code step: prompt → `run(ctx, **params)` + pytest tests; static checks: `ruff`, AST import allow-list, dependency allow-list; repair loop ≤ 3 on failure. **P0**
  *Test:* generated code passes static checks for UC1; a disallowed `import os` is rejected.
- [ ] **P2.1.6** Tutorial step: `TOOL.md` ≤ 350 words (What it does · What you give it · What you get back · Example · Limits), plain language. **P0**
  *Test:* word count ≤ 350; all 5 headings present.
- [ ] **P2.1.7** `forge_from_pattern` orchestration → writes `candidates` doc, publishes `forge_started`/`forged`; `POST /dev/forge`, `GET /candidates/{id}`. **P0**
  *Test:* `POST /dev/forge` with the fixture → candidate with spec, code, tests, tutorial.
- [ ] 🆕 **P2.1.9** VLM labeling prompt + JSON schema in `app/prompts/label_frames.py` (contract in §3.3: `frame_id` on every step, known verbs or `"other"`, < 0.6 → `needs_review`). P4 wires it into the interpreter. **P0**
  *Test:* 3 sample frames (from `fixtures/`) return valid JSON with `frame_id` on every step.
- [ ] 🆕 **P4.1.5** *(start here, 10:50–11:30)* `scripts/video_to_frames.py`: `ffmpeg -vf "select='gt(scene,0.02)'"` turns the 3 Excel videos into keyframes → POST to `/capture/batch` with `source: video_replay`, timestamps **backdated to the 3 Mondays**; generator emits canonical signatures + `evidence.frame_ids` for UC1. **P0**
  *Test:* UC1 sessions link to real frames (against P1's stub now, real in I-1a).

#### ⇄ I-1 (12:15–12:45): extension check, 5 min with P1 (merge embeddings + keyframes), then I-1b with P3 — see §6.2

#### Phase 2 (12:45–14:00)
- [ ] **P4.1.2** Real artifacts in `data/artifacts/`: `uc1/week1..week4.xlsx` (week 3 with renamed columns), expected outputs from a hand-written reference script (`uc1/expected/weekN_pivot.csv`, `weekN_chart.json`); `uc2/paper1.txt`, `paper2.txt` + expected param keys. Sessions' `artifacts.inputs/outputs` point to these paths. **P0**
  *Test:* reference script reproduces the expected files exactly.
- [ ] **P2.2.1** Gate (`gate/service.py`): (a) unit tests in sandbox; (b) replay: for each evidence session, run with its `artifacts.inputs` and compare with `artifacts.outputs` (tables exact via pandas with float tolerance; charts structurally: type, axes, series count); (c) dry-run side effects ⊆ declared scopes; (d) dedupe via `search_tools` (merge/adapt/new decision recorded). Write `verdicts`; publish `gate_passed`/`gate_failed`. Uses P4's artifacts in `data/artifacts/`. **P0**
  *Test:* UC1 candidate passes replay on weeks 1–3; a tampered output fails with a clear reason.
- [ ] **P2.2.2** Register `forge` job handler in the worker registry (forge → gate → repair ≤ 3). **P0**
  *Test:* inserting a forge job ends with a candidate in `passed` or `failed`.
- [ ] ✏️ **P2.2.3** `promote()` in one multi-document transaction: insert `tool_versions` (with `derivation`), upsert `tools` (pointer, `trust: dry_run`, embedding, `lineage`), save verdict link, mark pattern `toolified`, mark candidate `approved`; `POST /candidates/{id}/approve|reject`; publish `promoted`. **P0**
  *Test:* kill the transaction mid-way (raise) → nothing written; normal run → all writes present.
- [ ] **P2.2.4** Trust ladder `update_after_run` (plan §8.2): 3 confirmed previews → supervised; streak ≥ 8 and edit rate ≤ 0.1 → *proposal* (pending policy change, user confirms); any failure → demote instantly; publish `trust_changed`. **P0**
  *Test:* simulate runs → correct level transitions.
- [ ] 🆕 **P4.2.5** Interpreter worker (`interpreter/`, registers `interpret` job): **A** dHash / region diff dedupe (§3.5b), downscale; **B** RapidOCR with boxes (Tesseract fallback), hints (title, sheet names, headers, dialog titles), click-target resolution (click point ∩ OCR box / DOM element), **secret regex over OCR → drop frame + GridFS file, count in `capture_sessions.frames_dropped_by_rule`**; **C** `embed_multimodal` → `frames.embedding`, batched VLM call (6–10 frames, P2's prompt) → `frames.label`; **D** `action_vocab` upsert (alias ≥ 0.88, promote after 3), emit canonical steps for fusion; publish `frame_labeled`. **P0**
  *Test:* week 1 video → the correct UC1 step sequence.

#### ⇄ Integration I-2, all three (14:00–14:30)

#### Phase 3 (14:30–15:15)
- [ ] **P2.3.1** Drift watcher `check_drift`: last 10 runs vs `baseline.success_rate`; on drop → publish `drift_detected`, queue `heal` job. **P0**
  *Test:* 3 failures in a row → heal job queued.
- [ ] **P2.3.2** Heal handler: capture failing input (mock site v2 HTML), diagnose with heavy model, forge v+1, gate on **new failing case + all old fixtures**, auto-enter `dry_run` + notify; record time-to-heal; publish `healed`. **P0**
  *Test:* flip mock site to v2 → scraper fails → healed version passes v1 and v2 fixtures.
- [ ] 🆕 **P4.2.6** Baseline agent for the race (`baseline/`) + `POST /race`: run the `not_found` path on purpose (lean-model agent loop solving UC1 from scratch) with step / token / elapsed counters published as `race_step`; the same endpoint starts `run_by_intent` for the tool side. **P0** *(P2 takes this if P4 is behind at I-1)*
  *Test:* emits step events while it works; both sides finish with final numbers.
- [ ] **P2.3.4** Pre-compute and cache the demo generations (UC1 forge, UC3 heal) with P4 so the live demo hits the cache. **P0**
  *Test:* rerunning the forge with the cache is < 5 s.
- [ ] **P4.3.2** With P2: pre-compute generations 1–3 (and cache VLM labels for the 3 videos) and verify the cache is used. **P0**
- [ ] ✏️ **P2.3.3** Prune job: below `min_runs_30d` or `min_success_rate` → `deprecated`, **unless `dependents()` returns active tools** (then keep + log reason); publish `pruned`. **P1**
  *Test:* 2 idle seeded tools get pruned; a depended-on idle tool is kept; toolbox count drops.
- [ ] 🆕 **P2.3.6** `ctx.call(tool, **params)` in the harness; deps from `resolve_deps` mounted as modules `tools/<name>.py` (never concatenated — every tool defines `run()`). **P1**
  *Test:* composed UC2 tool calls `extract_method` inside the sandbox.
- [ ] 🆕 **P4.3.7** Nearest-neighbour label copy (≥ 0.93): skip the VLM when a labeled frame is similar enough (Atlas `frames_vec` or numpy fallback). **P1**
  *Test:* week 3 needs fewer VLM calls than week 1.
- [ ] ⭐ **P2.3.5** Merge path: superset tool must pass both parents' fixtures; merged tutorial; parents `deprecated` with `merged_into`.
- [ ] ⭐ 🆕 **P2.3.7** Playwright browser execution path (role + accessible-name selectors, 3 fallbacks, never XPath/coordinates).
  *Test:* recorded page snapshot replays with role selectors.

---

### 5.3 Person 3 — Frontend, extension, concierge, demo assets

Build UI against `web/mocks/*.json` first (`NEXT_PUBLIC_USE_MOCKS=true`), then switch to the real API at integration.

#### Phase 1 (10:50–12:15)
- [ ] 🆕 **P3.1.0** Chrome MV3 extension (TypeScript) in `extension/` — **10:50–11:50**:
  content script captures click, submit, nav / SPA route change, typing-burst end (> 800 ms idle) with element `{role, name, data_attr}`, `url_template` and value **shape only (no key content)**; drops the frame if a password field is focused; service worker calls `captureVisibleTab` on trigger (≤ 1/s, ~400 ms after a click); host permission for `CAPTURE_ALLOWED_ORIGINS` only (the mock site); batched POST to `/capture/batch` every 5 s; toolbar badge "REC" + pause button; polls `GET /capture/state` every 2 s. **P0**
  *Test:* clicking through the mock site creates `ui_events` and `frames` in Atlas (against P1's stub: the POST body validates against `fixtures/capture_batch.json`); on any other site nothing is captured.
- [ ] **P4.1.3** Mock site: `mocksite/v1/` and `v2/` (same data, different HTML structure: renamed classes, moved price element), tiny static server on port 8081 with `POST /demo/mocksite/{v1|v2}` switch (router `p3_demo.py` can proxy to it — was `p4_demo.py`); cached HTML snapshots as UC3 fixtures + expected parsed output. Make sure pages have real buttons/forms with accessible names (the extension reads them). **P0**
  *Test:* v1 and v2 both serve; the v1 parser fails on v2 (that's the heal demo).
- [ ] **P3.1.1** App shell: Tailwind + shadcn/ui, sidebar nav (Tool shop · Suggestions · Chat · Policy & metrics), light/dark. **P0**
  *Test:* all pages render with mocks, no console errors.
- [ ] ✏️ **P3.1.2** `lib/api.ts`: typed client for every endpoint in §3.4 (incl. capture, lineage, race) with the mock toggle; `lib/useEvents.ts` SSE hook (mock: replays `events.jsonl` / `race.jsonl` on a timer). **P0**
  *Test:* toggle mocks on/off without code changes.
- [ ] **P3.1.3** Tool shop page: tool cards (name, trust badge, runs, success rate, minutes saved) + big "minutes saved this week" counter + toolbox count + recorder status badge. **P0**
  *Test:* renders `fixtures/tool_uc1.json` list.
- [ ] **P3.1.4** Suggestions page: cards with reason, support, distinct days, est. minutes saved; Accept / Decline (with "never for this" option) / Snooze; a **"Why?"** drawer listing dated episodes (frames added in P3.3.5); a "Declined by ToolSmith" section showing decoys with their reason. **P0**
  *Test:* buttons call the right API functions (check network tab / mock log).
- [ ] ✏️ **P3.1.5** Candidate/tool detail page: tutorial (render markdown), params schema, **execution path badge** ("seen in Excel · runs on pandas"), code viewer (collapsed), verdict checks (unit / replay / side effects / dedupe as green/red), versions list. *(may slip to the start of Phase 2)* **P0**
  *Test:* renders fixture candidate and tool.

#### ⇄ I-1 (12:15–12:45): lead the extension check, then I-1b with P2 — see §6.2

#### Phase 2 (12:45–14:00)
- [ ] **P3.2.1** Live forge progress: after Accept, show a stepper (spec → code → tests → replay → tutorial) driven by SSE events; Approve / Reject buttons on passed candidates. **P0**
  *Test:* with mocks, events move the stepper to "passed".
- [ ] **P3.2.2** Run panel on tool detail: form generated from `params_schema` (file picker from `data/artifacts` list), dry-run preview showing intended writes + Confirm; show duration and tokens vs agent baseline ("9 min → 8 s, 18k → 0.5k tokens"). **P0**
  *Test:* dry_run → preview; confirm → result.
- [ ] **P4.2.3** Concierge `POST /chat`: LiteLLM tool-calling loop (lean tier) with tools `search_tools`, `recall_episodes`, `analyze_idea`, `run_tool`, `submit_feedback`, `approve_change`; state in `conversations`; returns `cards` for the UI. **P0**
  *Test:* "why did you suggest the dashboard tool?" → cites dated episodes; "run it on week4.xlsx" → dry-run preview.
- [ ] **P4.2.4** `POST /ideas` `analyze_idea`: covered by existing tool? feasibility, scopes, deps, savings estimate from history → refined spec **or** "use tool Y"; if the user confirms, call `forge_from_spec`. **P0 (minimal)**
  *Test:* an idea matching UC1 returns "use existing tool"; a new idea returns a spec.
- [ ] **P3.2.3** Chat page: message list, input, rendering of `ChatReply.cards` (tool card, suggestion card, episode list). **P0**
  *Test:* works against `fixtures/chat_reply.json`.
- [ ] **P3.2.4** Switch to real API for everything built so far; fix shape mismatches (report any contract gaps in §8). **P0**
  *Test:* with `NEXT_PUBLIC_USE_MOCKS=false` all pages load from the backend.
- [ ] *(if ahead)* start P3.3.5 evidence strip against `fixtures/why_uc1.json`.

#### ⇄ Integration I-2, all three (14:00–14:30)
**14:30 UI check:** if suggestions → forge → run doesn't work in Next.js by now, the team decides on the Streamlit fallback (only if the event rules allow it).

#### Phase 3 (14:30–15:15)
- [ ] 🆕 **P3.3.5** **Evidence strip** in the "Why?" drawer: 3 dated thumbnails (`/frames/{id}/thumb`) + the detected step list under them (`file.open → table.rename → … → export.html`). **P0, never cut**
  *Test:* renders UC1 frames from the real API.
- [ ] 🆕 **P3.3.7** **Split-screen race view** on the run panel: left = baseline agent (step counter, tokens climbing), right = tool (FOUND → `working_memory` → result); both sides stream `race_step` from SSE; freeze on final steps / seconds / tokens. Calls `POST /race`. **P0**
  *Test:* both sides stream from SSE (mock `race.jsonl`, then real).
- [ ] **P3.3.1** **Policy strip** (always visible at the bottom): live feed of `policy.changes` via SSE — `min_support 3 → 4 · because 3 of last 4 tools were pruned · applied`, pending loosen changes with an Approve button; prune-kept messages ("kept: tool Y depends on it"). **P0**
  *Test:* a `policy_changed` event appears in the strip within 1 s.
- [ ] ✏️ **P3.3.2** Metrics page (Recharts), **7 charts** (all 6 original + ablation): minutes saved/week, tokens before vs after, break-even runs, replay pass rate, toolbox size over time, detection P/R with decoy false-positive rate, **logs-only vs logs+screen ablation**. **P0**
  *Test:* renders `fixtures/metrics.json`.
- [ ] **P3.3.3** Demo controls panel: "Switch mock site to v2", "Run consolidation", "Run prune" buttons; heal timeline (drift → patch → gated → promoted with time-to-heal). **P0**
  *Test:* buttons call `/demo/mocksite/v2`, `/consolidate` and the prune trigger.
- [ ] **P4.3.1** Demo data reset script: `scripts/demo_reset.py` → reset DB, seed history (+ frames), pre-load cached generations, set mock site v1, **freeze `action_vocab`**. **P0**
  *Test:* running it twice gives the same starting screen.
- [ ] 🆕 **P3.3.6** Capture panel: pause/resume, allow-list view, delete last 5 min, audit list from `GET /capture/sessions`. **P1**
  *Test:* pause stops new frames within 2 s.
- [ ] **P3.3.4** Deploy `web/` to Vercel pointing at the backend URL (partner stack). **P1** *(restored to original priority)*
  *Test:* public URL loads the tool shop.
- [ ] ⭐ **P3.3.8** Tool lineage tree on the tool detail page (`GET /tools/{id}/lineage`). *(unnumbered on the 4-person board — ID added, work unchanged)*

#### Demo prep (15:35–16:40)
- [ ] **P4.3.3** Record the fallback demo video (full 3-min script from plan §14). **P0**
- [ ] ✏️ **P4.3.4** README draft: problem, architecture diagram, how to run (incl. loading the extension), "built today" vs dependencies, **Atlas feature map** (plan §2.1), privacy controls, partner stacks used (MongoDB, OpenAI, OpenRouter, Vercel, …). **P0**

---

### 5.4 Stretch pool (anyone who is fully ticked after I-2)

- [ ] ⭐ **ANY.3.1** Desktop watcher: `mss` screenshots + foreground window title + `pynput` click hook (~150 lines, demo OS only) with a **startup self-test** that fails loudly on black frames (macOS permissions). First capture item to cut.
- [ ] ⭐ **ANY.3.2** MCP library server exposing each active tool as an MCP tool (best closing line; first thing cut).
- [ ] ⭐ **ANY.3.3** Heavy-tier extras: LangGraph concierge, HDBSCAN, rerank, code retrieval, gVisor/E2B.

### 5.5 Self-improving harness — where each loop lives (reference, no extra tasks)

| Loop | What the harness improves | Tasks (IDs from this board) |
|---|---|---|
| **L1 Capability** | Creates, gates, heals, merges and prunes its own tools | P1.1.7–P1.1.9, P2.1.4–P2.1.8, P2.2.1–P2.2.3, P2.3.1–P2.3.3, ⭐ P2.3.5 |
| **L2 Composition** | Builds new tools from its earlier tools | P1.3.5 (`$graphLookup` + prune safety), P2.3.6 (`ctx.call`), UC2 in P4.1.1 / P4.1.2 |
| **L3 Authority** | Tools earn autonomy, lose it instantly on failure | P2.2.4, P2.3.1 |
| **L4 Meta-policy** | Rewrites its own guardrails | P1.2.3, P1.3.1, P3.3.1 |
| **F1 Feedback → mining** | Rejections change what gets mined next | P1.3.2 |
| **F2 Ideas → forge** | User ideas become tools | P4.2.3, P4.2.4 |

---

## 6. Integration plan

### 6.1 Git workflow

- Branches: `p1-core`, `p2-forge`, `p3-web`. Commit often, push after every ticked task.
- At the end of each phase: `git pull origin main`, merge into your branch, run your tests, open a PR into `main`, get one teammate to glance at it, merge.
- Ownership (§2) means PRs almost never conflict. If a conflict appears in a shared file, the file owner resolves it.
- Tag after each integration: `i1a`, `i1b`, `i2`, `i3`. If an integration breaks, anyone can go back to the last tag.

### 6.2 Integration I-1 (12:15–12:45)

**Extension check · all three (12:15–12:25)** (lead: P3)
- [ ] 🆕 **Extension check:** load the unpacked extension, click through the mock site → `ui_events` + `frames` visible in Atlas; a non-allow-listed site produces nothing.

**I-1a · P1 (+ P2 for 5 min) — "history and screen become patterns"** (lead: P1)
- [ ] Merge `p1-core` (+ P2's `embeddings.py` and `video_to_frames.py`) into `main`.
- [ ] `scripts/init_db.py` → `scripts/seed.py --reset` against the real API.
- [ ] 🆕 `video_to_frames.py` posts the 3 Excel sessions → `frames` docs with GridFS keyframes, backdated to Mondays.
- [ ] Sessions closed and embedded in Atlas; miner runs.
- [ ] **Check:** UC1 and UC3 patterns are `mined` with **canonical signatures**; decoy A declined as "one-day burst", decoy B declined as "high variance".
- [ ] **Check:** `recall_episodes("monday sales dashboard")` returns the 3 Monday sessions.
- [ ] Tick and log in status files. Tag `i1a`.

**I-1b · P2 + P3 — "a pattern becomes a visible tool candidate"** (lead: P2)
- [ ] Merge `p2-forge` and `p3-web` into `main` (P3's `extension/` and `mocksite/` included).
- [ ] UI calls `POST /dev/forge` with `fixtures/pattern_uc1.json`.
- [ ] **Check:** candidate page shows spec, **execution path `api`**, tutorial, code, and a sandbox dry-run on `week1.xlsx` (P2's artifact if already made, else a small test file).
- [ ] Both tick and log. Tag `i1b`.

### 6.3 Integration I-2 (14:00–14:30) — all three, go/no-go

- [ ] All three PRs merged into `main`; `docker compose up` runs api, worker, web, mocksite; extension loaded.
- [ ] Remove P1 stubs that now have real implementations (P1 checks nothing still imports a stub).
- [ ] **End-to-end check (the go/no-go):**
  1. [ ] Seeded history → suggestion "weekly sales dashboard" appears in the UI, with **Why?** showing dated episodes.
  2. [ ] 🆕 That UC1 pattern is **screen-derived**: `GET /suggestions/{id}/why` returns ≥ 3 frames from 3 different days (interpreter + fusion worked).
  3. [ ] Accept → forge job → gate replays weeks 1–3 → `gate_passed` in the UI.
  4. [ ] Approve → promoted in a transaction → tool appears in the shop at `dry_run`.
  5. [ ] `POST /run` "make this week's dashboard" with `week4.xlsx` → route `found` → `working_memory` doc exists → preview → confirm → result.
  6. [ ] Chat: "why this suggestion?" works.
- [ ] **14:30 decision:** if steps 1–5 fail, P1 hand-seeds one pattern and P2 keeps one live forge; if step 2 fails, P2 hand-labels the 3 Excel sessions' frames so the evidence strip still has real screenshots; P3 decides Next.js vs Streamlit fallback.
- [ ] Tag `i2`.

### 6.4 Integration I-3 (15:15–15:35) — all three, final

- [ ] Merge Phase 3 PRs; `scripts/demo_reset.py`.
- [ ] Run the full 3-minute demo script (plan §14) once, end to end:
  - [ ] recorder badge on; **Why?** shows the evidence strip (3 dated Excel screenshots + steps) and the two declined decoys
  - [ ] accept → spec says "seen in Excel, runs on pandas" → replay green → promoted at `dry_run`
  - [ ] **race:** baseline agent vs tool on `week4.xlsx`, final steps / seconds / tokens on screen
  - [ ] heal: switch mock site to v2 → drift → healed → time-to-heal shown
  - [ ] decline with "never for /finance" → rule added → policy strip shows it
  - [ ] policy learner change shows `because` text; a loosen change sits at pending
  - [ ] prune → toolbox count drops; (if P1.3.5 done) one tool **kept because another depends on it**
  - [ ] privacy: pause → no new frames; allow-list + audit visible
  - [ ] metrics page shows computed numbers incl. the **ablation** (logs-only vs logs+screen)
- [ ] Tag `i3`. **Code freeze.** After this, only bug fixes agreed by the team.

### 6.5 Demo beat → tasks it depends on (3-person owners in brackets)

| Demo beat (plan §14) | Depends on |
|---|---|
| 1 Hook (tool shop, recorder badge) | P3.1.3 [P3], P3.1.0 [P3] |
| 2 "It watched you" (evidence strip + decoys) | P4.1.5 [P2], P4.2.5 [P2], P1.2.8 [P1], P1.2.9 [P1], P1.1.9 [P1], P3.3.5 [P3] |
| 3 Forge + gate (execution path) | P2.1.4–P2.1.8 [P2], P2.2.1 [P2], P2.2.3 [P2], P3.2.1 [P3], P3.1.5 [P3] |
| 4 The race | P4.2.6 [P2], P1.2.6 [P1], P3.3.7 [P3] |
| 5 Heal | P4.1.3 [P3], P2.3.1 [P2], P2.3.2 [P2], P3.3.3 [P3] |
| 6 Guardrails rewrite + prune safety | P1.2.3 [P1], P1.3.1 [P1], P2.3.3 [P2], P1.3.5 [P1], P3.3.1 [P3] |
| 7 Privacy in 10 s | P3.1.0 pause [P3], P1.2.8 allow-list [P1], P3.3.6 [P3] |
| 8 Close (Atlas map + ablation number) | P4.3.6 [P1], P3.3.2 [P3], P4.3.4 [P3] |

---

## 7. Progress board (update when a phase closes)

| Phase / step | P1 | P2 | P3 |
|---|---|---|---|
| Pre-event | ☐ | ☐ | ☐ |
| Phase 0 | ☐ | ☐ | ☐ |
| Phase 1 | ☐ | ☐ | ☐ (ext ☐) |
| I-1 | ☐ ext + I-1a | ☐ ext + I-1a/b | ☐ ext + I-1b |
| Phase 2 | ☐ | ☐ (interpreter ☐) | ☐ |
| I-2 (go/no-go) | ☐ | ☐ | ☐ |
| Phase 3 | ☐ | ☐ | ☐ |
| I-3 (freeze) | ☐ | ☐ | ☐ |

Detailed live progress lives in `docs/status/P1.md … P3.md`.

---

## 8. Contract change requests

**P1 implementation decisions for the updated board:**
- P1 · Current board is `TASKS_3people (1).md`, linked from `docs/TASKS.md`; old board retained as history.
- P1 · `Observation.artifacts` added as optional `{inputs, outputs}` to carry replay paths into sessions; existing payloads remain valid.
- P1 · `events.jsonl` remains the SSE fixture; ingestion uses `observations.jsonl` to avoid the §3.6 / P1.1.5 naming conflict.
- P1 · Expanded metrics fields are `detection`, `repair_loops`, `toolbox_size_over_time`.
- P1 · Fixture-only capture controls are process-local until the Phase 2 Atlas implementation.


Format: `HH:MM · from PN · to owner PM · what + why · status (open / done)`

**From plan v4 §19.3 (agreed before the event — P1 applies them in P1.0.2):**
- pre · plan v4 · to P1 · Canonical `domain.verb:argshape` signatures; `meta.source` carries the app; fixtures updated · open
- pre · plan v4 · to P1 · `Observation.evidence`, `ToolVersion.derivation`, `tools.lineage.calls` · open
- pre · plan v4 · to P2 · Tool contract gains `ctx.call(tool_name, **params)` · open
- pre · plan v4 · to P1 · New endpoints: `POST /capture/batch`, `GET /frames/{id}/thumb`, `GET /capture/sessions`, `GET /tools/{id}/lineage`; `/why` response gains `frames` · open
- pre · plan v4 · to P1 · SSE types: `frame_labeled`, `capture_paused`, `race_step` · open
- pre · plan v4 · to P1 · `.env`: `VOYAGE_MM_MODEL`, `CAPTURE_ALLOWED_ORIGINS`, `LLM_VISION_MODEL` · open

**Added while writing this board (not in plan §19 — confirm with the owner in Phase 0):**
- pre · board · to P2 · `llm.complete` gains a `"vision"` tier + image content parts (needed by P4.2.5) · open
- pre · board · to P1 · `GET /capture/state`, `POST /capture/{pause|resume}`, `POST /capture/delete_last` (the extension and capture panel need a shared pause state) · open
- pre · board · to P4 · `POST /race` + `race_step` payload shape (§3.4) so P3 can build the race view against a fixture · open
- pre · board · to P1 · `embed_multimodal()` in `embeddings.py` and `interpret` job type · open

---

**3-person ownership changes (no contract shape changes):**
- pre · 3p · P1 → P2 · `embeddings.py` (task P1.1.4) built by P2; P1 keeps the stub until P2 pushes · open
- pre · 3p · P4 → P1/P2/P3 · `metrics/` → P1 · `interpreter/`, `baseline/`, `/race` → P2 · `concierge/`, `/chat`, `/ideas`, `/demo/mocksite` → P3 (routers renamed `p3_*.py`) · open

---

## 9. Blockers log

Format: `HH:MM · PN · blocked on what · workaround used · resolved?`

- _(none yet)_

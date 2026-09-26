# ToolSmith — Team Task Board v4 · **3-person split**

> Put this file at `docs/TASKS.md` in the repo. Put `plan_final.md` (v4) at `docs/plan_final.md`.
> This file is the single source of truth for **who builds what, in which phase, and how we integrate**.
> Every person (and their Claude) works only from their own section, ticks boxes when a task is done **and tested**, and pushes.
>
> **How this differs from the 4-person board:** plan v4 §13.4 says "3 people: merge A + D". Taken literally that puts the whole data role on the
> backend person, who is already the busiest. So the old P4 work is **spread across all three**, by skill:
> - **P1** (backend) takes the data that feeds the miner: generator, seeding, metrics, capture eval + ablation, demo reset.
> - **P2** (forge) takes everything that calls a model: embeddings, the interpreter (OCR + VLM), the baseline agent for the race, the concierge, calibration, and the UC1 artifacts the gate replays.
> - **P3** (frontend) takes everything visual or static: the extension, the mock site, the README and the fallback video.
>
> One person fewer also means **more cuts** (§4.1). The "never cut" list from the plan is untouched.
> Task IDs keep their old numbers where the task is the same, so you can still cross-check with plan §19. Moved tasks show where they came from, e.g. `P2.2.5 (was P4.2.5)`.

---

## 0. How to use this file (read first — humans and agents)

### 0.1 Agent protocol (paste this to your Claude: "I am Person N, follow docs/TASKS.md")

When a teammate tells their Claude **"I am Person N"** (N = 1, 2 or 3), the agent must:

1. Read this whole file, then `docs/plan_final.md` (v4) for background. Section §3 (Contracts) is binding.
2. Go to **Section 5.N (Person N)**. Work only on the **current phase**, top to bottom, on unticked tasks.
3. Only create or edit files inside **your owned paths** (§2). If you need a change in someone else's file or in a contract, do **not** edit it — add a line to §8 "Contract change requests" and tell the owner.
4. If something you depend on isn't ready, **don't wait**: use the stub or fixture from §3 and keep going. Log it in your status file.
5. Every task has a **Test** line. A task is done only when that test passes. Then:
   - tick the box: `- [ ]` → `- [x]`
   - append one line to your status file `docs/status/PN.md`: `HH:MM · task ID · done · short note`
   - commit with message `PN: <task ID> <short description>` and push to your branch.
6. At the end of each phase, open a PR from your branch into `main` (see §6). Don't merge other people's PRs without them.
7. Never commit secrets. Keys go in `.env` (git-ignored); only `.env.example` is committed. Screen recordings are git-ignored too.
8. Keep code simple and readable. This is a one-day build: working > clever. **With three people, use a library before writing your own** (e.g. the `prefixspan` package instead of a custom miner).

### 0.2 Timeline at a glance (hackathon day, Sep 26)

| Time | Phase | What happens |
|---|---|---|
| Before the event | **Pre-event (no code)** | Rules, keys, Docker, Excel recordings + ground-truth labels, `action_vocab` seed (§4.0). |
| 10:30–10:50 | **Phase 0 — Setup** | P1 pushes repo skeleton + contracts (incl. capture collections) + stubs. P2 and P3 set up tools. |
| 10:50–12:15 | **Phase 1 — Build (independent)** | P1 memory + miner + generator · P2 LLM + sandbox + forge · P3 **extension first**, then mock site + UI shell. |
| 12:15–12:45 | **Integration I-1** | 12:15–12:25 **all three**: extension → Atlas check. Then **I-1a = P1** (history → patterns) and **I-1b = P2 + P3** (forge → UI). |
| 12:45–14:00 | **Phase 2 — Build (independent)** | P1 runtime + capture ingest + fusion · P2 gate + promotion + **interpreter** · P3 real UI wiring + evidence strip. |
| 14:00–14:30 | **Integration I-2 (all three)** | Full loop. **14:30 go/no-go** (includes: a screen-derived UC1 pattern reaches `/suggestions` with frames). |
| 14:30–15:15 | **Phase 3 — Build (independent)** | P1 policy learner + prune + metrics + ablation · P2 heal + **race baseline** + cache · P3 race view + policy strip + metrics. |
| 15:15–15:35 | **Integration I-3 (all three)** | Final merge, end-to-end demo run. **Code freeze 15:35.** |
| 15:35–16:40 | Demo prep | Bug triage only, rehearse 3×, README (P3), fallback video (P3), 1-min video. |
| 16:40–17:00 | Submit | Repo public, all members added. |

```
Phase 1:    P1        P2    P3
             \          \  /
I-1:   (ext check: all three) → P1 alone | (P2+P3)
               \        /
Phase 2:    P1   P2   P3
               \  |  /
I-2:        all three (go/no-go)
Phase 3:    P1   P2   P3
I-3:        all three (freeze)
```

**Capture layer at a glance (3-person version):**

| Time | Owner | Capture work |
|---|---|---|
| 10:30–10:50 | P1 | Capture collections, GridFS, TTLs, contract fields, canonical fixtures, `POST /capture/batch` stub (P1.0.2) |
| 10:50–11:50 | P3 | Chrome extension (P3.1.0) |
| Phase 1 | P1 | Canonical signature mapper (P1.1.10) |
| Phase 1 | P2 | `vision` tier, multimodal embeddings, VLM prompt, `derivation` |
| 12:15–12:25 | all | Extension click-through on the mock site → `ui_events` + `frames` in Atlas |
| Phase 2 | P1 | `/capture/batch` real + fusion + `/why` returns frames |
| Phase 2 | P2 | ffmpeg keyframes from the 3 Excel videos + interpreter Stages A, B (OCR only), C, D |
| 14:30 | all | Go/no-go: screen-derived UC1 pattern in `GET /suggestions` with frames behind it |
| Phase 2–3 | P3 | Evidence strip (P0, never cut) |
| Phase 3 | P1 | Capture eval + logs-only vs logs+screen ablation |

### 0.3 Scope rules for the day

- Build the **Lean tier only**. Everything Heavy is ⭐.
- Priority tags: **P0** = must have for the demo · **P1** = should have · ⭐ = stretch (only after your phase is fully ticked).
- **Never cut** (plan §13.3): runtime found/not-found with `working_memory` · replay gate · decoy rejection · heal · policy strip · visible vector search (episodic recall in "Why?" + tool lookup in the runtime) · **the evidence strip** · **the fusion rule that structured data wins** · **pause + allow-list** (both live in the extension).
- **Cut order if still behind** (first → last): race view polish → ablation (hard-code nothing — drop the chart instead) → calibration (keep placeholders) → concierge chat → prune → mining sophistication (hand-tune thresholds).
- **Freeze `action_vocab` during the demo.**

---

## 1. Roles

| Person | Role | Owns (short) |
|---|---|---|
| **P1** | Backend core, memory, mining, runtime, capture ingest **+ data & metrics** | Atlas setup, ingest, `/capture/batch`, GridFS, fusion, canonical signatures, sessions, miner, search, suggestions + `/why`, runtime, worker, events, policy learner, prune · **synthetic generator, seeding, metrics, capture eval + ablation, demo reset** |
| **P2** | Forge, gate, sandbox, trust **+ all model work** | LLM client (lean/heavy/vision), **embeddings**, VLM prompt, sandbox + runner, forge (+ `derivation`), gate, promotion, trust ladder, drift + heal · **UC1 artifacts, video → keyframes, interpreter, baseline agent + `/race`, cached generations, calibration, concierge (P1 priority)** |
| **P3** | Frontend + extension **+ demo assets** | Chrome extension, all Next.js UI (tool shop, suggestions + evidence strip, tool detail, run panel + race view, policy strip, metrics, demo controls) · **mock site v1/v2, README, fallback demo video** |

Write your real names here: P1 = ______ · P2 = ______ · P3 = ______

**Load notes (read these, they are the risk):**
- **P1 is the bottleneck** (plan §13.4 predicted this). If P1 is behind at I-1, P3 takes **P1.3.4 demo reset** and P2 takes **P1.3.3 capture eval** in Phase 3.
- **P2 has the interpreter in Phase 2**, because the 14:30 go/no-go needs screen-derived patterns. If the interpreter isn't labeling by 13:45, P2 hand-labels the UC1 frames (the VLM output shape from §3.3) so the evidence strip still shows real screenshots, and says so on stage.
- **P3's Phase 1 starts with the extension (1 h)**, so most UI pages land in Phase 2. Build them against mocks; they don't need the backend.

---

## 2. Repo layout and ownership

```
toolsmith/
├─ backend/
│  ├─ app/
│  │  ├─ main.py              P1  (FastAPI app, router auto-discovery)
│  │  ├─ config.py            P1  (reads .env + capture constants §3.5b)
│  │  ├─ contracts.py         P1  (Pydantic models from §3 — change only via §8)
│  │  ├─ db.py                P1  (incl. GridFS bucket "keyframes")
│  │  ├─ events.py            P1  (publish + SSE)
│  │  ├─ ingest/              P1
│  │  ├─ capture/             P1  (/capture/batch, frames + GridFS, ui_events, fusion)
│  │  ├─ miner/               P1  (incl. signatures.py — canonical mapper)
│  │  ├─ search.py            P1
│  │  ├─ suggestions/         P1
│  │  ├─ runtime/             P1
│  │  ├─ policy/              P1  (learner + prune job)
│  │  ├─ metrics/             P1  (was P4: metrics, capture eval, ablation)
│  │  ├─ embeddings.py        P2  (was P1: Voyage text + multimodal)
│  │  ├─ llm.py               P2  (LiteLLM: lean / heavy / vision)
│  │  ├─ prompts/             P2  (label_frames.py, forge prompts)
│  │  ├─ sandbox/             P2  (runner + harness)
│  │  ├─ forge/               P2
│  │  ├─ gate/                P2
│  │  ├─ trust/               P2  (trust ladder, drift, heal, promote)
│  │  ├─ interpreter/         P2  (was P4: Stages A–D, worker job "interpret")
│  │  ├─ baseline/            P2  (was P4: race baseline agent + /race)
│  │  ├─ concierge/           P2  (was P4: /chat, P1 priority)
│  │  └─ routers/  p1_*.py (P1) · p2_*.py (P2)
│  ├─ worker.py               P1  (change streams + job dispatch registry)
│  ├─ tests/p1|p2/            each owner
│  └─ requirements/  base.txt (P1) · p2.txt (P2: litellm, docker, voyageai, rapidocr-onnxruntime, imagehash, opencv-python-headless)
├─ sandbox/Dockerfile         P2
├─ extension/                 P3  (Chrome MV3, TypeScript)
├─ web/                       P3  (Next.js)
├─ mocksite/v1  mocksite/v2   P3  (was P4) + tiny server with /_switch/{v1|v2}
├─ data/
│  ├─ generator/  seed/       P1  (was P4)
│  ├─ artifacts/              P2  (was P4: UC1 xlsx + expected outputs; UC3 HTML snapshots come from P3's mock site)
│  ├─ recordings/             P2  (Excel videos, git-ignored; keyframes/ generated)
│  ├─ ground_truth/           P1  (gt_steps.json)
│  └─ action_vocab_seed.json  P1
├─ scripts/  init_db.py, seed.py, capture_eval.py, demo_reset.py (P1) · video_to_frames.py, calibrate.py, precompute.py (P2)
├─ fixtures/                  shared sample JSON from §3.6 (P1 creates in Phase 0)
├─ docs/TASKS.md  docs/plan_final.md  docs/status/P1..P3.md  README.md (P3)
├─ docker-compose.yml         P1  (api, worker, web, mocksite)
└─ .env.example               P1
```

**Shared-file rule:** `main.py`, `worker.py`, `contracts.py`, `docker-compose.yml`, `base.txt` belong to P1 and are pre-built so others don't touch them:
- `main.py` auto-includes every `app/routers/p*_*.py` that exposes `router`.
- `worker.py` has `register(job_type, handler)`; P2 registers `forge`, `heal`, `interpret` from `app/*/jobs.py` (auto-discovered).

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

**P1 provides**
```python
# app/embeddings.py          ← owned by P2 in the 3-person split (same signatures)
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
LABEL_FRAMES_PROMPT: str; LABEL_FRAMES_SCHEMA: dict   # P2 writes and calls via complete("vision", ...)
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

**P2 also provides (was P4)** — interpreter, baseline, concierge · **P1** owns `metrics/service.py`
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
| ⭐ `GET /capture/sessions` | P1 | audit list from `capture_sessions` (P1 priority) |
| ⭐ `GET /capture/state` · `POST /capture/{pause\|resume}` · `POST /capture/delete_last?minutes=5` | P1 | `{paused, allowed_origins}` / `{ok}` / `{deleted_frames, deleted_events}` (P1 priority; extension polls state every 2 s) |
| `GET /suggestions` | P1 | `[{pattern_id, title, reason, support, distinct_days, est_minutes_saved_week, value, signature, dynamic_params}]` |
| `GET /suggestions/declined` | P1 | same shape + `declined_reason` (decoys show here) |
| ✏️ `GET /suggestions/{id}/why` | P1 | `{episodes: [EpisodeHit], frames: [{frame_id, ts, thumb_url, verb}]}` |
| `POST /suggestions/{id}/accept\|decline\|snooze` | P1 | `{ok, job_id?}` — decline body: `{reason, never_for_scope?}` |
| `GET /candidates/{id}` | P2 | candidate doc + verdict (+ `derivation`) |
| `POST /candidates/{id}/approve\|reject` | P2 | `{tool_id}` / `{ok}` |
| `POST /dev/forge` | P2 | `{candidate_id}` — body: `{pattern: Pattern}` (dev-only, used in I-1b) |
| `GET /tools` | P1 | `[{tool_id, name, title, status, trust, runs, success_rate, p50_ms, minutes_saved}]` |
| `GET /tools/{id}` | P1 | tool + active version (tutorial_md, params_schema, requires, derivation) |
| ⭐ `GET /tools/{id}/lineage` | P1 | `{calls: [...tree with depth], merged_from, merged_into, dependents}` |
| `GET /tools/{id}/versions` · `POST /tools/{id}/rollback` | P1 | list / `{ok}` |
| `POST /tools/{id}/run` | P1 | `RunResult{run_id, mode, output, intended_writes, needs_confirm, duration_ms, tokens}` |
| `POST /run` | P1 | `RunResult` + `{route: "found"\|"related"\|"not_found", tool_id?, score}` — body `{intent, inputs}` |
| 🆕 `POST /race` | P2 | `{race_id}` — body `{intent, inputs}`; starts `run_baseline` and `run_by_intent` side by side, both stream `race_step` |
| `POST /tools/{id}/feedback` | P1 | `{ok}` |
| `GET /policy` · `POST /policy/changes/{id}/approve` | P1 | `PolicyDoc` / `{ok}` |
| `POST /consolidate` | P1 | `{job_id}` (⭐ this revision) |
| `GET /events` (SSE) | P1 | stream of `{type, ts, data}` |
| `POST /chat` | P2 (P1 priority) | `ChatReply` |
| `POST /ideas` | ⭐ P2 | `IdeaAnalysis` |
| `GET /metrics` | P1 | `Metrics` (see 3.6) |
| `POST {MOCKSITE_URL}/_switch/{v1\|v2}` | P3 | `{active}` — served by the mock-site server itself (no backend router); flips the layout for the heal demo |

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
(`T_high`/`T_low` are placeholders; P2 runs a quick calibration in Phase 3 — P1 priority. The placeholders are good enough for the go/no-go.)

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

- [ ] **ALL.pre.1** Confirm event rules: problem statement, "code on the day", **Streamlit fallback allowed?**, team size (3), **do pre-recorded screen sessions count as data prep?**
- [ ] **ALL.pre.2** Atlas tier features (plan §9), LLM + Voyage keys, Docker on every laptop with a practiced `network_mode=none` run.
- [ ] **P2.pre** Record the UC1 Excel workflow 3 times (weeks 1–3 files, ~5 min each) + one 20-min ground-truth recording. Draft the VLM labeling prompt text. **P0**
- [ ] **P1.pre** Hand-label the ground-truth recording (~60 steps → `data/ground_truth/gt_steps.json`) and write the ~30-verb `data/action_vocab_seed.json`. **P0**
- [ ] **P3.pre** Load an unpacked test extension in Chrome on the demo laptop once. Sketch the mock-site page (a product list with prices + a search form).
- [ ] **ALL.pre.3** Agree the contract changes in §8. Storyboard the 3-min demo (§6.5).

> Already on the day and not done? (plan A8) P2 records during 10:30–11:00 and P1 labels only 10 minutes of ground truth.

### 4.1 Cuts for a team of 3

Everything the 4-person board already cut stays cut (consolidation, Vercel, 6→4 metric charts, merge, desktop watcher, MCP, Heavy tier, memory-mode comparison, Playwright). **Extra cuts for 3 people:**

| Was | Now | Why it's safe |
|---|---|---|
| UC2 paper → simulation (generator plants, artifacts, forge) | ⭐ | It was P2 priority in the plan and the only composed tool |
| `$graphLookup` lineage, prune safety, `ctx.call`, lineage UI | ⭐ | Nothing to compose without UC2; plain prune still runs. Mention composition as "next" in Q&A |
| App-shift segmentation | ⭐ | 30-min idle split is enough for the seeded history |
| Nearest-neighbour label copy | ⭐ | Only saves cost; the demo uses cached VLM labels |
| OCR click-target resolution | ⭐ | The VLM gets frames + OCR text + hints; plan cut order allows it |
| Capture panel + `/capture/state`, pause/resume, delete-last endpoints | ⭐ | **Pause + allow-list stay** — they live in the extension (never cut) |
| `analyze_idea` / `POST /ideas` | ⭐ | Not in the 3-min demo |
| Concierge `/chat` + chat page | **P1** (not P0) | Episodic recall is already visible in the "Why?" drawer |
| Calibration on ~30 pairs | Quick sweep on ~15 pairs, **P1** | Placeholder thresholds work for the go/no-go |
| Heal on UC3 **and** a live UC3 mining story | UC3 is **seeded as an already-promoted tool** | Heal is never cut; UC3 only needs to exist as a tool that breaks |

### 4.2 Phase 0 — Setup (10:30–10:50) — everyone

- [ ] **ALL.0.1** GitHub, Atlas, `.env` filled locally, Docker running, Python 3.11, Node 20.
- [ ] **ALL.0.2** Create `docs/status/PN.md` with `10:3x · setup · started`.
- [x] **P1.0.1** Repo skeleton exactly as §2: `contracts.py` (every shape in §3), all stubs from §3.3 returning fixture data (**including P2's `embed` stub**), router auto-discovery, worker job registry, `docker-compose.yml`, `.env.example`, `fixtures/`. **Push to `main` by 10:50.**
  *Test:* `uvicorn app.main:app` starts; `GET /tools` returns the fixture; `pytest` runs.
- [ ] **P1.0.2** Capture collections (`frames` regular, `ui_events`, `action_vocab`, `capture_sessions`), GridFS `keyframes`, TTLs, contract fields (`evidence`, `derivation`, `lineage.calls`), canonical fixtures, capture constants in `config.py`, `POST /capture/batch` stub. **P0**
  *Test:* stub accepts `fixtures/capture_batch.json`.
- [ ] **P2.0.1** Docker SDK, pull `python:3.11-slim`, confirm a `network_mode=none` container runs; `ffmpeg` installed.
- [ ] **P3.0.1** `create-next-app web` (TS, Tailwind, App Router) + shadcn/ui; `extension/` MV3 `manifest.json` skeleton; `mocksite/` folder.

After P1 pushes: `git pull`, then branches `p1-core`, `p2-forge`, `p3-web`.

---

## 5. Task lists per person

### 5.1 Person 1 — Backend core, memory, mining, runtime, capture ingest, data & metrics

#### Phase 1 (10:50–12:15)
- [ ] **P1.1.1** `db.py` + GridFS; `scripts/init_db.py`: all collections, `observations` time-series (`expireAfterSeconds: 5184000`), TTLs on `working_memory` and `frames`, indexes from §3.2, loads `action_vocab_seed.json`. Idempotent. **P0**
  *Test:* run twice, no errors; `action_vocab` has ~30 docs.
- [ ] **P1.1.2** Verify tier features → `docs/status/P1.md`: `db.version()` ≥ 8.1, `$rankFusion` + `$vectorSearch`, search-index count, change streams on `sessions` + `frames`, GridFS round trip. **P0** *(keep it to 10 min)*
  *Test:* script prints OK/FAIL for each.
- [ ] **P1.1.3** Search indexes in priority order: `tools_vec`, `sessions_vec`, `tools_text` (+ `frames_vec` only if allowed; `patterns_vec` skipped). Filter on `user_id` (+ `status`). **P0**
  *Test:* READY in Atlas.
- [ ] **P1.1.10** Canonical signature mapper (`domain.verb:argshape` from `action_vocab`, aliases resolved, unknown → `other`). **P0**
  *Test:* Excel "insert pivottable" and pandas `pivot_table` both → `table.pivot:2col`.
- [ ] **P1.1.5** Ingest `POST /observations/bulk`: normalize, regex redaction, `args_shape`, canonical `signature`, app in `meta.source`, insert `observations`, upsert `sessions`. **P0**
  *Test:* `fixtures/events.jsonl` → inserted, secrets `<REDACTED>`, signatures canonical.
- [ ] **P1.1.6** Sessionizer: 30-min gap; on close → `intent_summary`, `intent_embedding` (P2's `embed`, stub until merged), minutes, tokens. **P0**
  *Test:* 2 bursts 1 h apart → 2 closed sessions.
- [ ] **P1.1.7** Miner with the **`prefixspan` package** (len 3–8, `min_support` from policy); custom code only if the package fails. **P0**
  *Test:* toy sequences → planted sequence found, random ones not.
- [ ] **P1.1.8** `features.py`: intent clustering (sklearn agglomerative), static/dynamic split, distinct days, periodicity, burstiness, variance; ignore `needs_review`. **P0**
  *Test:* weekly → periodicity high; 6 runs in one day → burstiness ≥ 0.8.
- [ ] **P1.1.9** Scoring + hard gates → `patterns` `mined` / `declined` + reason; seed default policy. **P0**
  *Test:* fixture sessions → correct statuses.
- [ ] **P1.1.11** *(was P4.1.1)* Generator `python -m data.generator`: analyst persona, 3 weeks, ~30 sessions, ~700 events, canonical signatures + `meta.source`. Plants: **UC1** weekly Mondays (different file each week, `artifacts` paths → P2's `data/artifacts/uc1/`), **UC3** daily scrape runs (enough to show usage history for the seeded UC3 tool), **decoy A** one-day binge, **decoy B** high variance, noise. Writes `ground_truth.json` + a **logs-only** variant (UC1 screen steps removed) for the ablation. *(UC2 cut.)* **P0**
  *Test:* counts match; each planted workflow is on the expected days.
- [ ] **P1.1.12** *(was P4.1.4)* `scripts/seed.py`: posts `data/seed/*.jsonl` to `/observations/bulk`; `--reset`; `--logs-only` seeds the ablation variant under a second user id. **P0**
  *Test:* returns counts against your own endpoint.

#### ⇄ I-1 (12:15–12:45): ext check with everyone, then I-1a on your own — §6.2

#### Phase 2 (12:45–14:00)
- [ ] **P1.2.1** `search.py`: `search_tools` via `$rankFusion` (client-side RRF fallback), `recall_episodes` via `$vectorSearch` on `sessions`, structural query on `signature`. **P0**
  *Test:* paraphrased query ranks the right fake tool first.
- [ ] **P1.2.4** `worker.py`: change streams on `sessions` (closed → mine), `jobs` (dispatch), `runs` (drift hook), `frames` (→ one debounced `interpret` job per session). **P0**
  *Test:* 3 frames → exactly 1 interpret job.
- [ ] **P1.2.5** `events.py` + `GET /events` SSE. **P0**
  *Test:* `curl -N /events` shows an event after `publish()`.
- [ ] **P1.2.8** `/capture/batch` real: allow-list check, `ui_events`, keyframe → GridFS + inline thumb + `frames` doc, `capture_sessions` counts, then `fuse()` (±1.5 s, structured wins, frame as evidence). **P0**
  *Test:* T1 click + T2 frame 0.8 s apart → one observation with `evidence.frame_ids`; non-allow-listed origin refused.
- [ ] **P1.2.2** Recheck gate + `GET /suggestions`, `/suggestions/declined`, `/suggestions/{id}/why`. **P0**
  *Test:* covered pattern not suggested; 3/day budget respected.
- [ ] **P1.2.9** `/why` returns `frames` (one per day, with verb) + `GET /frames/{id}/thumb`. **P0**
  *Test:* UC1 "why" → ≥ 3 frames from 3 different days.
- [ ] **P1.2.3** Accept → forge job; decline → feedback + cooldown; `never_for_scope` → `policy.rules` via `record_change`. **P0**
  *Test:* rule appears in `GET /policy`, change logged.
- [ ] **P1.2.6** Runtime `POST /tools/{id}/run` + `POST /run` (found → `working_memory` → sandbox at trust level → `runs` → `update_after_run` → `run_completed`; related → closest tool; not_found → log a session). **P0**
  *Test:* a found request creates `working_memory` and `runs` docs.
- [ ] **P1.2.7** `GET /tools`, `/tools/{id}`, versions, rollback. **P0**
  *Test:* shapes from §3.4.

#### ⇄ I-2, all three (14:00–14:30) — §6.3

#### Phase 3 (14:30–15:15)
- [ ] **P1.3.1** Policy learner (plan §8.3) on a compressed timer; tighten = applied, loosen = pending; `POST /policy/changes/{id}/approve`; `policy_changed`. **P0**
  *Test:* forced prune rate > 0.5 → `min_support 3 → 4` with `because`.
- [ ] **P1.3.5** *(was P2.3.3)* Prune job: below `min_runs_30d` or `min_success_rate` → `deprecated`; `pruned` event. Seed 2 idle tools so it has something to prune. **P1**
  *Test:* 2 idle tools pruned; toolbox count drops.
- [ ] **P1.3.3** *(was P4.2.2 + P4.3.6)* `metrics/service.py` + `GET /metrics`: minutes saved/week, tokens before/after, break-even, replay pass rate (from `verdicts`), time-to-heal, race numbers, decoy false-positive rate; `scripts/capture_eval.py` on the ground truth (step recall, signature precision, pattern recall, noise) + **logs-only vs logs+screen ablation** (miner on both users). **P0** *(P2 takes the capture-eval half if P1 is behind)*
  *Test:* matches `fixtures/metrics.json` shape; nothing hard-coded.
- [ ] **P1.3.4** *(was P4.3.1)* `scripts/demo_reset.py`: reset DB, seed history + frames, load cached generations (P2's cache), mock site v1, freeze `action_vocab`. **P0** *(P3 takes this if P1 is behind)*
  *Test:* running it twice gives the same starting screen.
- [ ] **P1.3.2** Feedback → miner: declined patterns skipped during cooldown. **P1**
  *Test:* declined pattern not re-suggested during cooldown.

---

### 5.2 Person 2 — Forge, gate, sandbox, trust, all model work

#### Phase 1 (10:50–12:15)
- [ ] **P2.1.1** `llm.py`: LiteLLM, tiers `lean` / `heavy` / `vision` (image parts), JSON-schema output, disk cache, tokens + cost. **P0**
  *Test:* second identical call `cached: true`; a 1-image vision call returns valid JSON.
- [ ] **P2.1.10** *(was P1.1.4)* `embeddings.py`: `embed` (Voyage, batches of 128) + `embed_multimodal`; `embedding_model` on docs. **Push early** — P1's sessionizer needs it at I-1a. **P0**
  *Test:* 3 strings → 3 vectors; 1 image + text → 1 multimodal vector.
- [ ] **P2.1.2** `sandbox/Dockerfile` (allowed packages, non-root, no network). **P0**
  *Test:* `--network none` imports pandas, `curl` fails.
- [ ] **P2.1.3** `harness.py` (`ctx.read_table/read_text/fetch/write_output`) + `runner.py` (no network unless `net:` scope, read-only FS, tmpfs, 512 MB, 30 s). **P0**
  *Test:* hand-written pivot tool works; dry_run writes nothing; infinite loop killed at 30 s.
- [ ] **P2.1.4 + P2.1.8** Forge spec step with `derivation` (**prefers the API path**; `assisted` / `not_automatable` outcomes). **P0**
  *Test:* `pattern_uc1.json` → valid spec, params `file` + `week`, `execution_path: api`.
- [ ] **P2.1.5** Forge code step + tests; `ruff`, import allow-list, dependency allow-list; repair ≤ 3. **P0**
  *Test:* UC1 code passes checks; `import os` rejected.
- [ ] **P2.1.6** `TOOL.md` ≤ 350 words, 5 headings. **P0**
  *Test:* word count + headings.
- [ ] **P2.1.7** `forge_from_pattern` → `candidates`; `POST /dev/forge`, `GET /candidates/{id}`; `forge_started`/`forged`. **P0**
  *Test:* fixture → candidate with spec, code, tests, tutorial.
- [ ] **P2.1.9** VLM labeling prompt + schema (`app/prompts/label_frames.py`). **P0**
  *Test:* 3 sample frames → valid JSON, `frame_id` on every step.

#### ⇄ I-1b with P3 (12:25–12:45) — §6.2

#### Phase 2 (12:45–14:00)
- [ ] **P2.2.0** *(was P4.1.2, UC1 only)* `data/artifacts/uc1/week1..4.xlsx` (week 3 with renamed columns) + reference script → `expected/weekN_pivot.csv`, `weekN_chart.json`. *(~15 min; do it first, the gate needs it.)* **P0**
  *Test:* reference script reproduces the expected files exactly.
- [ ] **P2.2.1** Gate: unit tests, replay on evidence sessions' artifacts (tables exact with float tolerance, charts structural), dry-run side effects ⊆ scopes, dedupe via `search_tools`; `verdicts`; `gate_passed`/`gate_failed`. **P0**
  *Test:* UC1 passes weeks 1–3; a tampered output fails with a reason.
- [ ] **P2.2.2** Register `forge` job (forge → gate → repair ≤ 3). **P0**
  *Test:* forge job ends in `passed` or `failed`.
- [ ] **P2.2.3** `promote()` in one transaction (version with `derivation`, tool pointer at `dry_run` + embedding, verdict link, pattern `toolified`, candidate `approved`); approve/reject endpoints; `promoted`. **P0**
  *Test:* raise mid-way → nothing written; normal → all writes present.
- [ ] **P2.2.5** *(was P4.1.5)* `scripts/video_to_frames.py`: ffmpeg scene filter → keyframes → `/capture/batch` with `source: video_replay`, backdated to the 3 Mondays. **P0**
  *Test:* `frames` docs exist for 3 different Mondays.
- [ ] **P2.2.6** *(was P4.2.5)* Interpreter job `interpret`: **A** dHash + region diff, downscale; **B** RapidOCR + hints (title, sheet names, headers), secret regex → drop frame + GridFS file + count; **C** `embed_multimodal` + batched VLM (6–10 frames/call); **D** `action_vocab` upsert (alias ≥ 0.88, promote after 3) → canonical steps for P1's fusion; `frame_labeled`. *(No click-target, no NN copy.)* **P0**
  *Test:* week 1 video → correct UC1 step sequence. **13:45 fallback:** hand-label the UC1 frames in the §3.3 shape.
- [ ] **P2.2.4** Trust ladder `update_after_run` (3 previews → supervised; streak ≥ 8 → proposal; failure → instant demote); `trust_changed`. **P0**
  *Test:* simulated runs → correct transitions.

#### ⇄ I-2, all three (14:00–14:30)

#### Phase 3 (14:30–15:15)
- [ ] **P2.3.1** Drift watcher: last 10 runs vs baseline → `drift_detected` + heal job. **P0**
  *Test:* 3 failures in a row → heal job queued.
- [ ] **P2.3.2** Heal: capture the failing mock-site v2 HTML, diagnose (heavy model), forge v+1, gate on new case + old fixtures, auto `dry_run`, time-to-heal, `healed`. Works on the **seeded UC3 scraper tool**. **P0**
  *Test:* flip to v2 → fails → healed version passes v1 and v2 snapshots.
- [ ] **P2.3.3** *(was P4.2.6)* Baseline agent + `POST /race`: lean-model loop solving UC1 from scratch, `race_step` events (step, tokens, elapsed); same endpoint starts `run_by_intent` for the tool side. **P0**
  *Test:* both sides stream and finish with final numbers.
- [ ] **P2.3.4** `scripts/precompute.py`: cache UC1 forge, UC3 heal and the **VLM labels for the 3 videos**, so the demo hits the cache. **P0**
  *Test:* rerunning the forge with the cache < 5 s.
- [ ] **P2.3.5** *(was P4.2.1)* Quick calibration: ~15 (intent, tool) pairs, sweep `T_high`/`T_low`, write to `policy` via `record_change` (origin `calibration`). **P1**
  *Test:* prints the F1 table; policy updated.
- [ ] **P2.3.6** *(was P4.2.3)* Minimal concierge `POST /chat`: lean tool-calling loop with `recall_episodes`, `search_tools`, `run_tool`. **P1**
  *Test:* "why did you suggest the dashboard tool?" cites dated episodes.

---

### 5.3 Person 3 — Frontend, extension, demo assets

Build UI against `web/mocks/*.json` (`NEXT_PUBLIC_USE_MOCKS=true`), switch to the real API in Phase 2.

#### Phase 1 (10:50–12:15)
- [ ] **P3.1.0** Chrome MV3 extension *(10:50–11:50)*: content script (click, submit, nav/SPA route, burst end > 800 ms; element role + name + data attr; `url_template`; **value shape only**; drop frame if a password field is focused); service worker `captureVisibleTab` ≤ 1/s (~400 ms after a click); host permission for `CAPTURE_ALLOWED_ORIGINS` only; batched POST every 5 s; "REC" badge + **pause button** (local state — no server endpoint in this split). **P0, never cut (pause + allow-list)**
  *Test:* body validates against `fixtures/capture_batch.json`; nothing captured on other sites; pause stops new frames.
- [ ] **P3.1.6** *(was P4.1.3, part 1)* `mocksite/v1/`: product list with prices + a search form (real buttons with accessible names), tiny server on :8081. **P0**
  *Test:* v1 serves; the extension captures clicks on it.
- [ ] **P3.1.1** App shell: sidebar (Tool shop · Suggestions · Policy & metrics), light/dark. **P0**
  *Test:* pages render with mocks.
- [ ] **P3.1.2** `lib/api.ts` (all §3.4 endpoints + mock toggle) + `lib/useEvents.ts` SSE hook (mock replays `events.jsonl` / `race.jsonl`). **P0**
  *Test:* toggle mocks without code changes.
- [ ] **P3.1.5** Candidate/tool detail page: tutorial markdown, params, **execution-path badge**, collapsed code, verdict checks green/red, versions. *(if not done by 12:15, finish it during I-1b)* **P0**
  *Test:* renders fixture candidate and tool.

#### ⇄ I-1 (12:15–12:45): ext check with everyone (12:15–12:25), then I-1b with P2 — §6.2

#### Phase 2 (12:45–14:00)
- [ ] **P3.1.4** Suggestions page: cards (reason, support, distinct days, minutes saved), Accept / Decline ("never for this") / Snooze, **"Why?" drawer**, "Declined by ToolSmith" section for the decoys. **P0**
  *Test:* buttons call the right API functions.
- [ ] **P3.3.5** **Evidence strip** in the "Why?" drawer: 3 dated thumbnails + detected step list (build on `fixtures/why_uc1.json`, then real). **P0, never cut**
  *Test:* renders UC1 frames from the real API.
- [ ] **P3.1.3** Tool shop: tool cards, trust badge, "minutes saved this week" counter, toolbox count. **P0**
  *Test:* renders the tools fixture.
- [ ] **P3.2.1** Live forge stepper (spec → code → tests → replay → tutorial) from SSE; Approve / Reject. **P0**
  *Test:* mock events move the stepper to "passed".
- [ ] **P3.2.2** Run panel: form from `params_schema`, dry-run preview of intended writes + Confirm, duration + tokens. **P0**
  *Test:* dry_run → preview; confirm → result.
- [ ] **P3.2.5** *(was P4.1.3, part 2)* `mocksite/v2/` (same data, renamed classes, moved price element) + `/_switch/{v1|v2}` on the mock-site server; save v1 + v2 HTML snapshots into `data/artifacts/uc3/` for P2's heal. **P0**
  *Test:* switch flips the page; a parser written for v1 fails on v2.
- [ ] **P3.2.4** Switch everything to the real API; report shape gaps in §8. **P0**
  *Test:* `NEXT_PUBLIC_USE_MOCKS=false`, all pages load.

#### ⇄ I-2, all three (14:00–14:30)
**14:30 UI check:** if suggestions → forge → run doesn't work in Next.js, decide on the Streamlit fallback (if allowed).

#### Phase 3 (14:30–15:15)
- [ ] **P3.3.7** **Split-screen race view** on the run panel (baseline left, tool right, live `race_step` counters, freeze on final numbers); calls `POST /race`. **P0**
  *Test:* both sides stream (mock, then real).
- [ ] **P3.3.1** **Policy strip** (always visible): `policy.changes` via SSE with `because`, pending loosen changes with Approve, prune messages. **P0**
  *Test:* `policy_changed` appears within 1 s.
- [ ] **P3.3.3** Demo controls: "Switch mock site to v2", "Run prune"; heal timeline with time-to-heal. **P0**
  *Test:* buttons hit `/_switch/v2` and the prune trigger.
- [ ] **P3.3.2** Metrics page, 4 charts: minutes saved/week, tokens before/after, break-even, **ablation**. **P0**
  *Test:* renders `fixtures/metrics.json`.
- [ ] **P3.2.3** Chat page — **only if P2.3.6 is done**. **P1**

#### Demo prep (15:35–16:40)
- [ ] **P3.4.1** *(was P4.3.4)* README: problem, architecture diagram, how to run (incl. loading the extension), "built today" vs dependencies, **Atlas feature map** (plan §2.1), privacy controls. **P0**
- [ ] **P3.4.2** *(was P4.3.3)* Record the fallback demo video (§6.5 script) after rehearsal #1. **P0**

---

## 6. Integration plan

### 6.1 Git workflow

- Branches `p1-core`, `p2-forge`, `p3-web`. Commit often, push after every ticked task.
- End of each phase: `git pull origin main`, merge into your branch, run your tests, PR into `main`, one teammate glances, merge.
- Conflicts in a shared file are resolved by its owner. Tags after each integration: `i1a`, `i1b`, `i2`, `i3`.

### 6.2 Integration I-1 (12:15–12:45)

**Extension check · all three (12:15–12:25)** (lead: P3)
- [ ] P1's `/capture/batch` stub (or real, if early) running; mock site v1 up; unpacked extension loaded.
- [ ] Click through the mock site → `ui_events` + `frames` visible in Atlas; another site → nothing; pause → nothing.

**I-1a · P1 alone — "history becomes patterns" (12:25–12:45)**
- [ ] Merge `p1-core` (+ P2's `embeddings.py` if pushed) into `main`.
- [ ] `init_db.py` → `seed.py --reset` against the real API; sessions closed and embedded; miner runs.
- [ ] **Check:** UC1 and UC3 patterns `mined` with canonical signatures; decoy A "one-day burst", decoy B "high variance".
- [ ] **Check:** `recall_episodes("monday sales dashboard")` returns the 3 Mondays. Tag `i1a`.

**I-1b · P2 + P3 — "a pattern becomes a visible tool candidate" (12:25–12:45)** (lead: P2)
- [ ] Merge `p2-forge` and `p3-web` into `main`.
- [ ] UI calls `POST /dev/forge` with `fixtures/pattern_uc1.json`.
- [ ] **Check:** candidate page shows spec, **execution path `api`**, tutorial, code, and a sandbox dry-run on P2's small test xlsx. Tag `i1b`.

### 6.3 Integration I-2 (14:00–14:30) — all three, go/no-go

- [ ] All PRs merged; `docker compose up` (api, worker, web, mocksite); extension loaded; P1 removes stubs that now have real code.
- [ ] `video_to_frames.py` run → interpreter labels → fusion → re-mine.
- [ ] **End-to-end check:**
  1. [ ] Suggestion "weekly sales dashboard" in the UI; **Why?** shows dated episodes.
  2. [ ] It is **screen-derived**: `/why` returns ≥ 3 frames from 3 days and the **evidence strip** renders them.
  3. [ ] Accept → forge → gate replays weeks 1–3 → `gate_passed`.
  4. [ ] Approve → promoted in a transaction → tool in the shop at `dry_run`.
  5. [ ] `POST /run` with `week4.xlsx` → `found` → `working_memory` doc → preview → confirm → result.
- [ ] **14:30 decision:** 1, 3–5 fail → P1 hand-seeds one pattern, P2 keeps one live forge. 2 fails → P2 hand-labels the UC1 frames. UI broken → Streamlit fallback (if allowed).
- [ ] Tag `i2`.

### 6.4 Integration I-3 (15:15–15:35) — all three, final

- [ ] Merge Phase 3 PRs; `scripts/demo_reset.py`.
- [ ] Run the demo once end to end (§6.5): evidence strip + decoys · forge with "seen in Excel, runs on pandas" · **race** · heal (v2 → drift → healed, time-to-heal) · decline "never for /finance" → rule · policy learner `because` + one pending loosen · prune → toolbox count drops · pause in the extension · metrics with the ablation.
- [ ] Tag `i3`. **Code freeze.**

### 6.5 Demo beats → tasks (3-person version of plan §14)

| Demo beat | Depends on |
|---|---|
| 1 Hook: tool shop, REC badge | P3.1.3, P3.1.0 |
| 2 "It watched you": evidence strip + declined decoys | P2.2.5, P2.2.6, P1.2.8, P1.2.9, P1.1.9, P3.1.4, P3.3.5 |
| 3 Forge + gate ("seen in Excel, runs on pandas") | P2.1.4–P2.1.8, P2.2.0, P2.2.1, P2.2.3, P3.2.1, P3.1.5 |
| 4 The race | P2.3.3, P1.2.6, P3.3.7 |
| 5 Heal (mock site v2) | P3.1.6, P3.2.5, P2.3.1, P2.3.2, P3.3.3 |
| 6 Guardrails rewrite + prune | P1.2.3, P1.3.1, P1.3.5, P3.3.1 *(no "kept because another tool depends on it" line — lineage is cut)* |
| 7 Privacy in 10 s | P3.1.0 (pause + allow-list), P1.2.8 (server allow-list) |
| 8 Close: Atlas feature map + ablation number | P1.3.3, P3.3.2, P3.4.1 |

---

## 7. Progress board (update when a phase closes)

| Phase / step | P1 | P2 | P3 |
|---|---|---|---|
| Pre-event | ☐ | ☐ | ☐ |
| Phase 0 | ☐ | ☐ | ☐ |
| Phase 1 | ☐ | ☐ | ☐ (ext ☐) |
| I-1 | ☐ ext + I-1a | ☐ ext + I-1b | ☐ ext + I-1b |
| Phase 2 | ☐ | ☐ (interpreter ☐) | ☐ |
| I-2 (go/no-go) | ☐ | ☐ | ☐ |
| Phase 3 | ☐ | ☐ | ☐ |
| I-3 (freeze) | ☐ | ☐ | ☐ |

Live progress: `docs/status/P1.md … P3.md`.

---

## 8. Contract change requests

Format: `HH:MM · from PN · to owner PM · what + why · status (open / done)`

**From plan v4 §19.3 (P1 applies in P1.0.2):**
- pre · plan v4 · to P1 · Canonical `domain.verb:argshape` signatures; app in `meta.source`; fixtures updated · done
- pre · plan v4 · to P1 · `Observation.evidence`, `ToolVersion.derivation`, `tools.lineage.calls` (field exists; lineage features are ⭐) · done
- pre · plan v4 · to P1 · Endpoints `POST /capture/batch`, `GET /frames/{id}/thumb`; `/why` gains `frames` · done
- pre · plan v4 · to P1 · SSE types `frame_labeled`, `race_step` (`capture_paused` unused — pause is local to the extension) · done
- pre · plan v4 · to P1 · `.env`: `VOYAGE_MM_MODEL`, `CAPTURE_ALLOWED_ORIGINS`, `LLM_VISION_MODEL` · done

**Board additions (confirm in Phase 0):**
- pre · board · to P2 · `llm.complete` gains a `"vision"` tier with image parts · open
- pre · board · to P2 · `POST /race` + `race_step` shape (§3.4) so P3 can build against a fixture · open
- pre · board · to P1 · `interpret` job type · done

**3-person changes:**
- pre · 3p · P1 → P2 · `embeddings.py` (incl. `embed_multimodal`) now owned by P2; P1 keeps the stub until P2 pushes · open
- pre · 3p · to P3 · Mock-site switch moves from `POST /demo/mocksite/{v}` (backend) to `POST {MOCKSITE_URL}/_switch/{v}` on the mock-site server · open
- pre · 3p · to all · Cut: `ctx.call`, `GET /tools/{id}/lineage`, `GET /capture/sessions`, `/capture/state` + pause/resume/delete endpoints, `POST /ideas` (all ⭐) · open

---

- 11:12 · from P1 · to P3 · Compose frontend profile expects `mocksite/server.py` on port 8081; confirm startup command when implementing mock site · open
- 11:12 · from P1 · to P1 · §3.6 `events.jsonl` is an SSE fixture, but P1.1.5 calls it ingest input; keep SSE fixture and use a separate observations fixture in Phase 1 · open

---

## 9. Blockers log

Format: `HH:MM · PN · blocked on what · workaround used · resolved?`

- 11:12 · P1 · Atlas URI and Docker unavailable; real mock-site screenshots and recording labels absent · fixture mode, synthetic labeled WebP samples, offline database tests · unresolved

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

ToolSmith: a one-day, 3-person hackathon build (MongoDB Atlas). It is a procedural-memory layer that watches user activity (browser extension + screen keyframes), mines recurring workflows, forges them into tested Python tools, and runs/governs those tools. Atlas is both the store and the event bus (change streams drive the worker).

Key planning docs (`docs/` entries are symlinks to the root files):
- `docs/TASKS.md` → `TASKS_3people (1).md` — **current** binding task board ("nothing removed" 3-person split): ownership (§1.1 owner map, §2 layout), contracts (§3), per-person tasks (§5), stretch pool (§5.4), integration (§6), contract change requests + P1 decisions (§8). `TASKS_3people.md` is the older board, kept only as history — don't work from it.
- `docs/plan_final.md` → `plan_final (2).md` — architecture (§4), modules (§6), governance (§8), data model (§9). Supersedes `m1-screen-capture-pattern-recognition.md` and the PDF.
- `docs/status/PN.md` — per-person progress log.
- `AGENTS.md` — repo guidelines (its "planning documents only" note is stale; Phase 0 scaffold exists).

## Commands

Run from the repo root (venv at `.venv`, Python 3.11+ target; currently 3.14 locally):

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements/dev.txt
cp .env.example .env
.venv/bin/pytest -q                                   # all tests (pytest config in pyproject.toml)
.venv/bin/pytest backend/tests/p1/test_phase0.py -k <name>   # single test
.venv/bin/ruff check backend scripts                  # lint (E, F, I; line length 100)
.venv/bin/ruff format backend scripts
.venv/bin/python scripts/init_db.py                   # create Atlas collections/indexes (needs MONGODB_URI; idempotent)
```

API (from `backend/`): `../.venv/bin/uvicorn app.main:app --reload` → `/docs`, `/health`.
Worker (from `backend/`): `../.venv/bin/python worker.py`.
Compose: `docker compose up` (api + worker); `docker compose --profile frontend up` adds `web` (Next.js) and `mocksite` (port 8081) once P3 creates them.

`pyproject.toml` puts both `backend` and the repo root on `pythonpath`, so tests import `app.*` and `worker` directly.

## Architecture

Pipeline: capture/ingest → `ui_events` + `frames` (GridFS bucket `keyframes`, TTL) → interpreter (OCR/VLM labels) → fusion (**structured DOM data wins; frame is evidence only**) → `observations` (time-series) + `sessions` → miner → `patterns` → suggestion (+ "Why?" evidence strip) → forge → sandbox (Docker, no network) → gate (unit + replay + side-effect + dedupe) → `tools`/`tool_versions` → runtime (hybrid vector search: found/related/not found, `working_memory`) → `runs` → trust ladder/drift/heal/prune → `policy` → feeds back into miner/gate/runtime.

Processes: `api` (FastAPI; **never executes tool code in-process** — always via `app/sandbox/runner.py`), `worker` (asyncio, change-stream job dispatch), sandbox container, `web`, Chrome MV3 `extension`.

Backend layout conventions (`backend/app/`):
- `main.py` auto-includes every `app/routers/p*_*.py` that exposes `router`. New routes go in a new `p1_*.py`/`p2_*.py` router, not in `main.py`.
- `worker.py` is a registry: modules register handlers via `from worker import register` in `app/<module>/jobs.py` (auto-discovered); handler signature `async def handler(payload: dict)`. Job types are the `JobType` literal in `contracts.py`.
- `contracts.py` holds all shared Pydantic wire models (`Contract` base: `extra="forbid"`, Mongo ids serialize as `_id`). Changing it = contract change → log in task board §8.
- `config.py` holds `Settings` (reads root `.env`) plus fixed capture constants (task board §3.5b) — do not tune during the demo.
- Each domain module (`capture`, `miner`, `runtime`, `policy`, `metrics`, `forge`, `gate`, `trust`, `interpreter`, `baseline`, `concierge`, `sandbox`) exposes a `service.py` whose signatures are fixed by task board §3.3.
- Exceptions map to HTTP: `NotImplementedError`→501, `PermissionError`→403, `LookupError`→404.

### Stub/fixture mode (Phase 0)

Most services are currently stubs returning JSON from `fixtures/` via `app/fixtures.py`. `STUB_MODE=true` enables them; every response carries `X-ToolSmith-Mode: fixture|live`. With `STUB_MODE=false`, stubs raise `NotImplementedError` (501) rather than silently falling back — preserve this: never let fixtures masquerade as live results. Fixtures are single-demo-user only (`DEMO_USER_ID`, default `u_1`). `events.py` is a process-local SSE feed until the Atlas-backed version lands. See `fixtures/README.md` for what each fixture represents (images are synthetic).

## Team workflow rules (from task board §0.1)

- Ownership (board §1, §1.1, §2):
  - **P1** — backend core, memory, mining, search, suggestions/`/why`, runtime + lineage, worker, events, policy learner, capture ingest/fusion, metrics, calibration, synthetic generator/seeding, capture eval + ablation. Scripts: `init_db.py`, `seed.py`, `calibrate.py`, `capture_eval.py`.
  - **P2** — `llm.py`, `embeddings.py` (moved from P1), `prompts/`, `sandbox/`, `forge/`, `gate/`, `trust/` (incl. heal, prune, merge), `interpreter/`, `baseline/` (race), NN label copy, cached generations, UC1/UC2 artifacts, recordings/keyframes (`video_to_frames.py`).
  - **P3** — `web/`, `extension/`, `mocksite/`, `concierge/` + `/chat` + `/ideas` `analyze_idea` (full-stack), `demo_reset.py`, README, fallback video.
  - Routers: `p1_*.py` / `p2_*.py` / `p3_*.py`; tests: `backend/tests/p1|p2|p3/`; deps: `requirements/base.txt` (P1), `p2.txt`, `p3.txt`.
  - Shared files (`main.py`, `worker.py`, `contracts.py`, `docker-compose.yml`, `requirements/base.txt`) belong to P1.
- Tasks with legacy `P4.x.x` IDs belong to whoever's §5 section they sit in (see §1.1). Task IDs match plan v4 §19.
- Ask the user which person they are if unclear; only edit that person's owned paths. Needed changes in others' files or contracts → add a line to board §8 and tell the owner.
- Within a phase, work **all P0 first, then P1, then ⭐**; unfinished items carry into the next phase. Nothing is cut from scope (board §4.1); the §0.3 cut order applies only if behind.
- If a dependency isn't ready, build against the §3 stub/fixture instead of waiting.
- A task is done only when its **Test** line passes; then tick it in `docs/TASKS.md`, append `HH:MM · task ID · done · note` to `docs/status/PN.md`, and commit as `PN: <task ID> <short description>`.
- Branches: `p1-core`, `p2-forge`, `p3-web`; PR into `main` at phase end; tags `i1a`, `i1b`, `i2`, `i3` after each integration.
- Lean model tier only; Heavy-tier items (LangGraph, HDBSCAN, rerank, gVisor, E2B, Playwright) are ⭐.
- "Never cut" features: runtime found/not-found with `working_memory`, replay gate, decoy rejection, heal, policy strip, visible vector search, evidence strip, structured-data-wins fusion, capture pause + allow-list. Freeze `action_vocab` during the demo.

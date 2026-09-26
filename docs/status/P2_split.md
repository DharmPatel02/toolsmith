# P2 work split — Claude Code (lane C) × Codex (lane X)

Rule: **split by file, not by task.** Each lane only writes to its own paths. Lanes talk through the
§3.3 signatures in `docs/TASKS.md`, so neither has to wait for the other. It uses a stub until the real
code lands.

## Git setup (parallel without conflicts)

```
git checkout -b p2-forge                         # lane C works here (main folder)
git worktree add ../toolsmith-codex -b p2-codex  # lane X works in this second folder
```
- Lane X merges into `p2-forge` at every checkpoint below (`git merge p2-codex`); `p2-forge` → PR to `main` per TASKS §6.
- Shared P2 files have one owner. The other lane asks for changes in "Requests" at the bottom:
  - `backend/requirements/p2.txt`: **C**
  - `docs/status/P2.md`: both append, one line per task (merge conflicts here are trivial)

## Lane C — Claude Code: model layer + forge → gate → promote → heal (critical path of the demo)

| Task | Owned paths |
|---|---|
| P2.1.1 `llm.py` (lean/heavy/vision, JSON schema, disk cache, cost) | `app/llm.py` |
| P2.1.10 `embeddings.py` (Voyage text + multimodal) | `app/embeddings.py` |
| P2.1.9 VLM label prompt + schema | `app/prompts/label_frames.py` |
| P2.1.4+8 forge spec + `derivation` | `app/forge/spec.py`, `app/prompts/forge_*.py` |
| P2.1.5 forge code + checks (ruff, import allow-list, repair ≤3) | `app/forge/codegen.py`, `app/forge/checks.py` |
| P2.1.6 TOOL.md | `app/forge/tutorial.py` |
| P2.1.7 `forge_from_pattern`, `/dev/forge`, `/candidates/{id}` | `app/forge/service.py`, `app/routers/p2_forge.py` |
| P2.2.1 gate | `app/gate/` |
| P2.2.2 `forge` job | `app/forge/jobs.py` |
| P2.2.3 `promote()` transaction + approve/reject | `app/trust/promote.py`, `app/routers/p2_candidates.py` |
| P2.3.2 heal (+ `heal` job) | `app/trust/heal.py`, `app/trust/jobs.py` |
| P2.3.4 precompute cache | `scripts/precompute.py` |
| tests | `backend/tests/p2/c/` |

## Lane X — Codex: sandbox, data, interpreter, trust ladder, race, extras

| Task | Owned paths |
|---|---|
| P2.0.1 Docker + ffmpeg check (script) | `scripts/check_env_p2.py` |
| P2.1.2 sandbox image | `sandbox/Dockerfile` |
| P2.1.3 harness + runner | `app/sandbox/` |
| P2.2.0 UC1 artifacts + reference script | `data/artifacts/uc1/` |
| P2.2.5 video → keyframes → `/capture/batch` | `scripts/video_to_frames.py` |
| P2.2.6 interpreter A–D + `interpret` job | `app/interpreter/` |
| P2.2.4 trust ladder `update_after_run` | `app/trust/ladder.py` |
| P2.3.1 drift watcher `check_drift` | `app/trust/drift.py` |
| P2.3.3 baseline agent + `POST /race` | `app/baseline/`, `app/routers/p2_race.py` |
| P2.3.5 calibration (P1 priority) | `scripts/calibrate.py` |
| P2.3.6 concierge `/chat` (P1 priority) | `app/concierge/`, `app/routers/p2_chat.py` |
| tests | `backend/tests/p2/x/` |

`app/trust/service.py` is a thin re-export that **C** owns:
`from .promote import promote; from .ladder import update_after_run; from .drift import check_drift`.

## Handoff order (the only cross-lane dependencies)

| When | Who pushes | Unblocks |
|---|---|---|
| ~11:15 | C: `llm.py`, `embeddings.py` | X: interpreter Stage C, baseline, concierge (until then X calls through the §3.3 signatures with a fake) |
| ~11:30 | X: `sandbox/runner.py` + image built | C: forge code-step test run, gate |
| ~11:45 | C: `prompts/label_frames.py` | X: interpreter Stage C |
| ~12:10 | **Checkpoint 1**: X merges into `p2-forge` | I-1b (forge → UI with sandbox dry-run) |
| ~13:00 | X: `data/artifacts/uc1/` + expected outputs | C: gate replay |
| ~13:45 | **Checkpoint 2** (interpreter labeling, or hand-label fallback) | I-2 go/no-go |
| ~15:10 | **Checkpoint 3**: final merge | I-3 |

## Requests between lanes
Format: `HH:MM · C→X or X→C · what · status`
- 11:40 · C→X · **Scope names** the runner must honour: `net:<domain>` enables `ctx.fetch` for that domain; `write:outputs` allows `ctx.write_output` in `live` mode. In `dry_run` every `write_output` is recorded as `Write{path, bytes}` in `intended_writes` and nothing is written. · open
- 11:40 · C→X · **Unit tests run through the runner, no extra API**: the gate calls `run_in_sandbox(code=<tool code + FakeCtx + tests + runner>, entry="run", params={}, inputs={}, mode="dry_run", scopes=[])`. So `run_in_sandbox` just has to exec `code` as a module and call `entry(ctx, **params)`. · open
- 11:40 · C→X · **UC1 artifacts (P2.2.0) shape**, the gate compares against these:
  - `data/artifacts/uc1/week{1,2,4}.xlsx` columns `date, reg, product, amt`; **week3.xlsx** renamed: `date, region_name, product, amount`. ~200 rows, 4–5 regions, a few empty rows/NaN `amt`, `amt` stored as text in some rows (so `table.cast` matters).
  - reference `data/artifacts/uc1/reference.py week1.xlsx` → rename → dropna → cast float → pivot sum by Region.
  - `expected/weekN_pivot.csv`: columns `Region,Amount`, sorted by Region, Amount rounded to 2 dp.
  - `expected/weekN_chart.json`: `{"type": "bar", "x": [regions sorted], "y": [amounts], "title": "Sales by Region - week N"}`.
  - The forged tool returns `{"summary": str, "tables": {"pivot": [{"Region":..,"Amount":..}]}, "chart_spec": {same shape}}` and writes `dashboard.html`. · open

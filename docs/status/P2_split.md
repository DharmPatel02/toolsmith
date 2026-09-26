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
- 12:40 · C (Codex idle, on C's critical path) · merged `p2-codex` (unrelated history, `--allow-unrelated-histories`) and fixed lane-X files to the contract:
  runner calls `entry(ctx, **params)` (was positional dict) · `net:<domain>` checked per host (was literal `net:`) ·
  inputs keep the source extension so `read_table("file")` parses xlsx · live `write_output` needs `write:outputs` ·
  subprocess runs via `asyncio.to_thread` (was blocking the event loop) · UC1 artifacts rebuilt to the agreed
  `reg/amt` shape (week 3 `region_name/amount`, messy rows) with `Region,Amount` pivot + `{type,x,y,title}` chart.
  Tests: `tests/p2/c/test_sandbox_contract.py`, `tests/p2/x/test_uc1_artifacts.py`. · done
- 12:40 · C→X · **Still open, needs Docker**: P2.1.2 `sandbox/Dockerfile` (uncommitted in the codex worktree) and a Docker
  path in `runner.py` (`--network none` unless a `net:` scope, read-only FS, tmpfs, 512 MB). The current runner is a
  plain subprocess = no OS-level isolation; OK for dev, not for the "sandbox" claim on stage. · done in code
  (docker backend in runner.py, auto when docker + `toolsmith-sandbox:latest` exist), live check still needs Docker on the demo laptop
- 13:27 · lanes merged: laptop died, Claude Code now owns lane X too; all X tasks done in the main folder.

## Requests to P1 / P3 (copy into TASKS §8)
- 13:27 · P2→P1 · **worker**: auto-discover `app/forge/jobs.py` (forge), `app/interpreter/jobs.py` (interpret), `app/trust/jobs.py` (heal); each exposes `JOBS` + `register(fn)`. · open
- 13:27 · P2→P1 · **runtime `runs` docs**: drift + ladder read `outcome` ∈ success|failed|edited (fallback `ok`), `started_at`, `params`, `user_confirmed`. Call `trust.service.update_after_run(run)` then `check_drift(tool_id)` after each run. · open
- 13:27 · P2→P1 · **runtime params**: file params must be passed to the sandbox as input handles too (`params["file"] = "file"` + inputs `{"file": path}`); forged code may use either `ctx.read_table("file")` or `ctx.read_table(params["file"])`. The gate does this. · open
- 13:27 · P2→P1 · **demo_reset**: call `await app.trust.uc3_seed.seed_uc3_tool("u_1")` (UC3 tool + v1 fixture + 12 green runs, trust supervised); set `VOCAB_FROZEN=1`; keep `.cache/llm` and `data/recordings/labels/` (precompute output, git-ignored / local). · open
- 13:27 · P2→P1 · **new collection `races`** `{_id, user_id, intent, inputs, status, baseline:{ok,steps,seconds,tokens,usd,...}, tool:{...}, summary}` for `metrics.race`. · open
- 13:27 · P2→P1 · **frames session id**: video replay posts `capture_session_id = s_w{N}_mon`; please use it as the frames' `session_id` (hand/precomputed label files are keyed by it). · open
- 13:27 · P2→P1 · `tool_versions` now also stores `spec` and `fixtures_ref.replay_cases` (heal re-gates against them). · info
- 13:27 · P2→P3 · **mock-site markup for UC3** (seeded scraper + heal expect this): v1 = `li.product` with `.product-name` and `.price` ("$24.99"); v2 = same products, renamed classes + price moved (reference: `REFERENCE_V1_HTML` / `REFERENCE_V2_HTML` in `backend/app/trust/uc3_seed.py`). Save snapshots to `data/artifacts/uc3/v1.html`, `v2.html`. · open
- 13:27 · P2→P3 · `POST /race` returns `{race_id}` at once; `GET /race/{id}` has final numbers; `POST /chat` is live (P3.2.3 unblocked). SSE extras: `healed.data.time_to_heal_ms`, `drift_detected.data.because`. · info
- 13:51 · P2→P3 · `POST /prune` (P2, `app/routers/p2_trust.py`): runs a pass, returns `{pruned, kept:[{tool_id, name, reason, kept_because}], toolbox_count}`; `?wait=false` queues a `prune` job. For the "Run prune" button + policy strip ("kept: Y depends on it"). · open
- 13:51 · P2→P1 · worker: also register `prune` from `app/trust/jobs.py`. Runtime: pass `deps` = code of `resolve_deps()` to `run_in_sandbox` for composed tools (`ctx.call`); `app.forge.deps.dependency_code(user_id, names)` does the same if useful. `dependents()` fallback in `app/forge/deps.py` reads `tools.lineage.calls` (promote now fills it). · open
- 13:51 · P2→P1/P3 · **handoff (board v4-3p moved them away from P2)**: calibration (P4.2.1 -> P1) already exists as `scripts/calibrate.py` + `scripts/calibration_pairs.json` (15 pairs; board now wants ~50 + `merge_similarity` sweep); concierge (P4.2.3 -> P3) exists as `app/concierge/service.py` + `app/routers/p2_chat.py` (tools: search_tools, recall_episodes, run_tool dry-run; missing per new board: analyze_idea, submit_feedback, approve_change). Owners take them over as they are; P2 won't change them further. · open
- 13:51 · P2→P1 · gate dedupe uses `policy.thresholds.merge_similarity` (merge) and `T_high` (adapt). · info

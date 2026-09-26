# MongoDB Atlas Integration — status and reference for Codex

This file records what has already been provisioned directly in Atlas (via the
MongoDB Atlas MCP tools, not application code) so Codex doesn't need to
rediscover it. It is a status snapshot, not a design doc — see
`docs/plan_final.md` (§9 data model) and `backend/app/db.py` /
`scripts/search_indexes.py` for the authoritative schema/index definitions.

## Atlas resources

- Org: `Harness Engineering & Model Wrangling Hackathon (.local NYC)` (`69ef9daf03d2ce35c2657862`)
- Project: `dharmpatel0002@gmail.com's Sandbox Project` (`6ab7de62af16c2903a3c948c`)
- Cluster: `Cluster0` — M10, AWS, `US_WEST_1`, **MongoDB 8.0.32**
- SRV host: `cluster0.jwr6sa.mongodb.net`
- Database: `toolsmith`

## Credentials & network access

- DB user `toolsmith_app` — `readWrite` on the `toolsmith` database only (not
  `atlasAdmin`, not any other DB). Password is in the local `.env` as part of
  `MONGODB_URI` — **never commit `.env`** (already gitignored) and never paste
  the URI into chat, issues, or logs.
- Network access is a **per-person IP allowlist**, not `0.0.0.0/0`. Currently
  allowlisted: Dharm's laptop (`216.158.150.90`). This was a deliberate choice
  over opening to the internet — the tradeoff is that every new machine that
  needs to reach the cluster (a teammate's laptop, a deployed backend, a CI
  runner) must be added as its own entry first, or connections will time out
  at the network layer before authentication is even attempted.
- **Approval process**: when someone needs access, get their public IP
  (`curl https://api.ipify.org` from their machine) and add it via
  `atlas-create-access-list` with a comment naming who it's for. Don't add
  ranges wider than a /32 unless you know what network you're trusting.
- **Codex**: running via Codex terminal (local CLI on Dharm's laptop), so it
  shares the same egress IP already allowlisted above — no separate entry
  needed. If Codex later moves to a hosted/cloud runner instead, its egress
  IP will be dynamic and this static allowlist won't cover it; revisit then
  (add its fixed egress range if the host provides one, or get a fresh IP to
  allowlist per session — don't default to opening `0.0.0.0/0`).

## Collections created

All collections in `backend/app/db.py`'s `initialize_database()` list now
exist in `toolsmith`, created directly via Atlas tooling:

`sessions`, `patterns`, `tools`, `tool_versions`, `candidates`, `runs`,
`verdicts`, `feedback`, `policy`, `profile`, `working_memory`,
`conversations`, `jobs`, `events`, `frames`, `ui_events`, `action_vocab`,
`capture_sessions`, `keyframes.files`, `keyframes.chunks`.

**Not yet created: `observations`.** It must be a time-series collection
(`timeField: ts`, `metaField: meta`, `granularity: seconds`) with
`expireAfterSeconds` for the 60-day TTL — the Atlas MCP tool's
`create-collection` only makes plain collections and has no option for
time-series/TTL parameters. This requires the driver, which is what
`scripts/init_db.py` already does.

## Indexes created

Classic indexes (via Atlas MCP `create-index`):

- `patterns`: `{user_id: 1, status: 1, value: -1}`
- `tools`: `{user_id: 1, name: 1}` (named `user_name_unique`) — **created
  without a uniqueness constraint**; the MCP tool's classic-index definition
  has no option to set `unique`. `db.py` expects this to be unique.
- `tools`: `{lineage.calls: 1}`
- `runs`: `{tool_id: 1, started_at: -1}`
- `frames`: `{user_id: 1, session_id: 1, ts: 1}`
- `ui_events`: `{user_id: 1, ts: -1}` and `{url_template: 1}`
- `keyframes.files`: `{filename: 1, uploadDate: 1}`
- `keyframes.chunks`: `{files_id: 1, n: 1}` (named `files_id_n_unique`) —
  **also created without uniqueness**, same MCP limitation as above.

Search indexes (via Atlas MCP `create-index`, matching
`scripts/search_indexes.py`'s default `--budget 3`):

- `tools.tools_vec` — vectorSearch on `embedding`, 1024 dims, cosine, filters
  on `user_id` + `status`
- `sessions.sessions_vec` — vectorSearch on `intent_embedding`, 1024 dims,
  cosine, filter on `user_id`
- `tools.tools_text` — Atlas Search, dynamic mapping off, fields `user_id`/
  `status` as token, `title`/`name`/`tutorial_md`/`keywords` as string

**Not created yet (were SKIPPED at budget 3, same as the script's default):**
`frames.frames_vec` (needs the Voyage multimodal embedding dimension
confirmed first — see `scripts/verify_atlas.py`'s UNVERIFIED note) and
`patterns.patterns_vec`. Add these the same way once needed, or run
`scripts/search_indexes.py --apply --budget 5` after setting `--frame-dims`.

Search/vector indexes build asynchronously — check status with
`collection-indexes` (or `list_search_indexes` in the driver) before relying
on them; they may not show `READY` immediately after creation.

## Required follow-up — status: done

The three items below needed the actual Python driver (the MCP tools alone
couldn't do them) and have now been run, live, against Cluster0. Full results
are logged in `docs/status/P1.md` ("Atlas verification results").

1. **`python scripts/init_db.py`** — run twice, idempotent both times.
   `observations` now exists as a real time-series collection with its
   60-day TTL; TTL indexes on `frames.expires_at` / `working_memory.expires_at`
   are set; `action_vocab` is seeded from `data/action_vocab_seed.json`.
2. **Non-unique indexes fixed** — the manually-created `user_name_unique` /
   `files_id_n_unique` indexes (see above) were dropped first via the Atlas
   MCP `drop-index` tool, *then* `init_db.py` was run so its own
   `create_index(..., unique=True)` calls created them correctly
   (auto-named `user_id_1_name_1` and `files_id_1_n_1`) without a naming
   conflict. Confirmed unique via `collection-indexes`.
3. **`python scripts/verify_atlas.py`** — run live. Change streams
   (`sessions`, `frames`), GridFS round-trip, and the `$rankFusion` +
   `$vectorSearch` hybrid pipeline all passed (`OK`). Index quota and the
   Voyage multimodal dimension remain `UNVERIFIED` — they need Atlas
   project-tier info and P2 provider verification respectively, not
   something this session could confirm.

## Version note: `$rankFusion` verified on 8.0.32

The verifier reports MongoDB buildInfo but no longer uses a version threshold
as a proxy for Atlas Search feature availability. A live `$rankFusion`
aggregation combining `$vectorSearch` (`tools_vec`) and `$search`
(`tools_text`) succeeded on this 8.0.32 cluster. P1.2.1 also includes a
client-side RRF fallback for MongoDB operation failures. Pipeline acceptance
confirms execution; ranking behavior is validated separately with known data.

## Reminders

- `STUB_MODE=true` is still set in `.env` — flip it to `false` per-service
  only once that service's real implementation replaces its fixture (see
  `CLAUDE.md`'s "Stub/fixture mode" section). Don't flip it globally before
  the code exists, or every endpoint 501s.
- GridFS bucket name is `keyframes` (`keyframes.files` / `keyframes.chunks`),
  matching `get_gridfs()` in `app/db.py`.
- Freeze `action_vocab` during the demo (task board rule) — don't reseed or
  mutate it casually once `init_db.py` has run.

# Fixtures

These files are development samples, not measured results or evidence of executed tools. `STUB_MODE=true` enables fixture-backed responses; HTTP responses include `X-ToolSmith-Mode: fixture`. When `STUB_MODE=false`, unfinished services fail closed instead of silently returning samples.

## API and UI fixtures

- `pattern_uc1.json`, `policy.json`, `tool_uc1.json`, `candidate_uc1.json`, `run_result.json`, and `why_uc1.json` support early API and UI work.
- `capture_batch.json` has three DOM events and two valid 256-pixel WebP frames.
- `frame_1.webp` and `frame_2.webp` are synthetic labeled UI samples. Replace them with P3 mock-site captures or P2 replay frames when available.
- `chat_reply.json` is a P3-facing chat fixture.
- `lineage_uc2.json` is a restored UC2 composition fixture with sample dependencies for `GET /tools/{id}/lineage`.
- `metrics.json` defines the expanded metrics response shape. Values are placeholders.

## Event files

- `events.jsonl` contains SSE envelopes for `GET /events`.
- `race.jsonl` contains illustrative race steps.
- `observations.jsonl` contains a small canonical observation-ingest sample for `/observations/bulk`.

Use `observations.jsonl` for ingest tests. `events.jsonl` is intentionally kept as the server-sent event fixture because the updated task board uses the same word for two different payload shapes.

## Generated histories

The full synthetic history is generated on demand:

```sh
.venv/bin/python -m data.generator --out /tmp/toolsmith-seed
```

That command writes `history.jsonl`, `history_logs_only.jsonl`, and `ground_truth.json`. The generated data plants UC1, UC2, UC3, two decoys, and noise. The logs-only history removes UC1 screen observations for the ablation.

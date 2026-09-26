# Phase 0 fixtures

These are development samples, not measured results or evidence of executed tools.
`STUB_MODE=true` enables them; HTTP responses carry `X-ToolSmith-Mode: fixture`.
The API returns 501 for unimplemented services when fixture mode is disabled.

- `pattern_uc1.json` and `policy.json` reproduce task-board §3 defaults.
- `capture_batch.json` has three DOM events and two valid 256-pixel WebP frames.
  `frame_1.webp` and `frame_2.webp` are **synthetic labeled UI samples**, not real
  screenshots. Replace them with P3's mock-site captures when available.
- `why_uc1.json` contains illustrative dates on three Mondays. Its thumbnail URLs
  intentionally serve synthetic sample images until real capture is integrated.
- `tool_uc1.json`, `candidate_uc1.json`, and `run_result.json` support UI development.
  The sandbox stub always reports that no execution occurred; confirmation does
  not execute or promote anything.
- `events.jsonl` contains SSE envelopes, and `race.jsonl` contains illustrative race
  steps. Neither file is an observation-ingest dataset.
- `metrics.json` defines the shared metrics shape; its values are placeholders.

The three-person scope omits the UC2 lineage fixture. The `lineage.calls` contract
remains available, but composition is not implemented.

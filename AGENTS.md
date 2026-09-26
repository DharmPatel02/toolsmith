# Repository Guidelines

## Project Structure & Module Organization

ToolSmith is a planned procedural memory layer that discovers recurring workflows and compiles them into tested, reusable tools. MongoDB Atlas stores memory and workflow state.

The repository currently contains planning documents only; application directories and dependency manifests are not yet scaffolded. Read `TASKS_3people.md` for ownership, contracts, and acceptance tests, and `plan_final (2).md` for architecture. The final plan supersedes the earlier screen-capture notes and research PDF.

Follow the task board's planned layout:

- `backend/app/`: Python FastAPI services; `backend/worker.py`: background jobs.
- `backend/tests/p1/`, `backend/tests/p2/`: owner-specific backend tests.
- `web/`: Next.js interface; `extension/`: TypeScript Chrome extension.
- `sandbox/`: isolated tool execution; `mocksite/`: demo targets.
- `data/`, `fixtures/`, `scripts/`: artifacts, shared JSON samples, and utilities.

## Build, Test, and Development Commands

These commands become usable after scaffolding and dependency installation:

- From `backend/`, `uvicorn app.main:app --reload` starts the API.
- From `backend/`, `pytest` runs backend tests.
- From the repository root, `docker compose up` starts the planned services.

No frontend build scripts or repository-wide lint commands exist yet. Document exact commands when adding their configuration.

## Coding Style & Naming Conventions

Target Python 3.11+ and typed Pydantic contracts. Use four-space Python indentation, `snake_case` functions/modules, and `PascalCase` classes. Use two-space indentation for TypeScript and follow the frontend formatter once configured. Keep modules small and readable. Router modules follow `p1_*.py` or `p2_*.py`. The plan specifies Ruff checks for generated Python tools; repository-wide linting remains unconfigured.

## Testing Guidelines

Use pytest files named `test_*.py`. Follow each task's **Test** requirement before marking it complete. Cover replay gates, decoy rejection, structured-data precedence, and capture pause/allow-list behavior where relevant. No numerical coverage threshold is defined.

## Commit & Pull Request Guidelines

There is no commit history yet. Follow the task board convention: `PN: <task ID> <short description>`. Use `p1-core`, `p2-forge`, or `p3-web` for assigned work. Keep changes within owned paths; record contract changes in task-board §8. Open phase PRs into `main` with task IDs, behavior changes, test results, and screenshots for UI changes. Obtain teammate review.

## Security & Configuration

Keep secrets in ignored `.env` files; commit only placeholder `.env.example` values. Ignore recordings. Execute generated tools in the designated sandbox, never inside the API process.

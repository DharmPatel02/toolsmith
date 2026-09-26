"""Phase 0 registry. P2 registers handlers from app/<module>/jobs.py.

Handlers receive a job payload dict and return an awaitable. The live change-stream
consumer is P1.2.4; this module does not claim to consume database jobs yet.
"""

import asyncio
import importlib
import sys
from collections.abc import Awaitable, Callable

from app.config import get_settings

# `python worker.py` and `import worker` must share one registry.
if __name__ == "__main__":
    sys.modules["worker"] = sys.modules[__name__]

Handler = Callable[[dict], Awaitable[object]]
_handlers: dict[str, Handler] = {}


def register(job_type: str, handler: Handler) -> None:
    if job_type in _handlers and _handlers[job_type] is not handler:
        raise ValueError(f"Handler already registered for {job_type}")
    _handlers[job_type] = handler


def discover_jobs() -> list[str]:
    from pathlib import Path

    import app

    modules = []
    for root in app.__path__:
        for path in sorted(Path(root).glob("*/jobs.py")):
            name = f"app.{path.parent.name}.jobs"
            importlib.import_module(name)
            modules.append(name)
    return modules


async def dispatch(job_type: str, payload: dict):
    if job_type not in _handlers:
        raise LookupError(f"No handler registered for {job_type}")
    return await _handlers[job_type](payload)


async def main():
    discover_jobs()
    if not get_settings().stub_mode:
        raise NotImplementedError("Live change-stream worker is pending P1.2.4")
    print("Phase 0 worker: registry ready; no database jobs consumed", flush=True)
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())

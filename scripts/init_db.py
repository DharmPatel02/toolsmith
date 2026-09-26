"""Run from the repo root: python scripts/init_db.py (requires MONGODB_URI)."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.db import close_client, get_db, initialize_database  # noqa: E402


async def main():
    try:
        await initialize_database(get_db())
        print("Collections, capture indexes, GridFS bucket, and action vocabulary initialized.")
    finally:
        await close_client()


if __name__ == "__main__":
    asyncio.run(main())

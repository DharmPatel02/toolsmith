"""Demo controls owned by P3: flips the mock site layout (proxies to the mock site)."""

import asyncio
import json
import os
import urllib.error
import urllib.request

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["p3-demo"])

LAYOUTS = ("v1", "v2")


def mocksite_url() -> str:
    return os.environ.get("MOCKSITE_URL", "http://localhost:8081").rstrip("/")


def _call(method: str, path: str) -> dict:
    request = urllib.request.Request(
        mocksite_url() + path, data=b"" if method == "POST" else None, method=method
    )
    with urllib.request.urlopen(request, timeout=5) as res:
        return json.loads(res.read())


async def call_mocksite(method: str, path: str) -> dict:
    try:
        return await asyncio.to_thread(_call, method, path)
    except (urllib.error.URLError, OSError) as exc:
        raise HTTPException(
            status_code=502, detail=f"mock site unreachable at {mocksite_url()}: {exc}"
        ) from exc


@router.get("/demo/mocksite")
async def mocksite_state():
    return await call_mocksite("GET", "/demo/mocksite")


@router.post("/demo/mocksite/{layout}")
async def switch_mocksite(layout: str):
    if layout not in LAYOUTS:
        raise HTTPException(status_code=400, detail=f"layout must be one of {LAYOUTS}")
    return await call_mocksite("POST", f"/demo/mocksite/{layout}")

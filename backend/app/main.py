import importlib
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.db import close_client


def discover_routers(application: FastAPI) -> None:
    import app.routers

    for root in app.routers.__path__:
        for path in sorted(Path(root).glob("p*_*.py")):
            module = importlib.import_module(f"app.routers.{path.stem}")
            if hasattr(module, "router"):
                application.include_router(module.router)


@asynccontextmanager
async def lifespan(application):
    yield
    await close_client()


def create_app() -> FastAPI:
    application = FastAPI(title="ToolSmith API", version="0.0.1", lifespan=lifespan)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[s.strip() for s in get_settings().web_allowed_origins.split(",")],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
        expose_headers=["X-ToolSmith-Mode"],
    )

    @application.middleware("http")
    async def fixture_mode(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-ToolSmith-Mode"] = "fixture" if get_settings().stub_mode else "live"
        return response

    @application.exception_handler(NotImplementedError)
    async def unavailable(request, exc):
        return JSONResponse(status_code=501, content={"detail": str(exc)})

    @application.exception_handler(PermissionError)
    async def forbidden(request, exc):
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    @application.exception_handler(LookupError)
    async def missing(request, exc):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @application.get("/health")
    async def health():
        return {"status": "ok", "mode": "fixture" if get_settings().stub_mode else "live"}

    discover_routers(application)
    return application


app = create_app()

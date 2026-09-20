from contextlib import asynccontextmanager
from pathlib import Path
import logging
import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from orchestrator import models  # noqa: F401
from orchestrator.api import router
from orchestrator.config import get_settings
from orchestrator.db import create_schema
from orchestrator.runtime import runtime
from orchestrator.auth import AuthenticationMiddleware
from orchestrator.db import SessionFactory
from orchestrator.memory import reindex_missing_memory
from orchestrator.context_sync import periodic_context_sync
from orchestrator.observability import configure_sentry
import asyncio


settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("orbit.http")


async def periodic_runtime_recovery() -> None:
    """Reclaim expired worker leases even when the API process stays alive."""
    while True:
        await asyncio.sleep(60)
        try:
            await runtime.recover()
        except Exception:
            logger.exception("runtime_recovery_failed")


class OrbitStaticFiles(StaticFiles):
    """Serve the SPA shell without caching while keeping hashed assets immutable."""

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        content_type = response.headers.get("content-type", "")
        if content_type.startswith("text/html"):
            response.headers["Cache-Control"] = "no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        elif path.startswith("assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.app_env == "production" and not settings.auth_required:
        raise RuntimeError("AUTH_REQUIRED must be true in production")
    if settings.app_env == "production" and settings.email_verification_required and not settings.smtp_host:
        # Keep existing verified accounts and the operator console available,
        # but registration itself fails closed before creating a user.
        logger.warning("email_verification_unavailable smtp_host_missing=true")
    if settings.app_env != "production":
        await create_schema()
    async with SessionFactory() as session:
        await reindex_missing_memory(session)
    await runtime.recover()
    sync_task = asyncio.create_task(periodic_context_sync())
    recovery_task = asyncio.create_task(periodic_runtime_recovery())
    try:
        yield
    finally:
        for task in (sync_task, recovery_task):
            task.cancel()
        for task in (sync_task, recovery_task):
            try:
                await task
            except asyncio.CancelledError:
                pass
        await runtime.shutdown()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
    openapi_url=f"{settings.api_prefix}/openapi.json",
    docs_url="/docs",
)
configure_sentry(app)
app.add_middleware(AuthenticationMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_observability(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("request_failed method=%s path=%s request_id=%s", request.method, request.url.path, request_id)
        raise
    duration_ms = (time.perf_counter() - started) * 1000
    response.headers["X-Request-ID"] = request_id
    response.headers["Server-Timing"] = f"app;dur={duration_ms:.1f}"
    content_type = response.headers.get("content-type", "")
    if request.method == "GET" and content_type.startswith("text/html"):
        # The SPA shell must always be revalidated after a deployment.  Its
        # hashed JS/CSS assets may stay cached, but caching index.html leaves
        # already-open users on an obsolete bundle with missing controls.
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    elif request.method == "GET" and request.url.path.startswith("/assets/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    logger.info(
        "request method=%s path=%s status=%s duration_ms=%.1f request_id=%s",
        request.method, request.url.path, response.status_code, duration_ms, request_id,
    )
    return response


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException):
    message = exc.detail if isinstance(exc.detail, str) else "Request could not be completed"
    return JSONResponse(
        {"code": f"http_{exc.status_code}", "message": message, "detail": exc.detail, "retryable": exc.status_code >= 500},
        status_code=exc.status_code,
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    return JSONResponse(
        {"code": "validation_error", "message": "Check the entered data", "detail": exc.errors(), "retryable": False},
        status_code=422,
    )
frontend_candidates = (
    # The production image installs the package into site-packages while the
    # built SPA is copied to /app/frontend/dist.  Resolve from the process
    # working directory first so the UI is served after a normal wheel install.
    Path.cwd() / "frontend" / "dist",
    Path("/app/frontend/dist"),
    Path(__file__).resolve().parents[2] / "frontend" / "dist",
)
frontend_dist = next((path for path in frontend_candidates if path.exists()), frontend_candidates[0])
if frontend_dist.exists():
    app.include_router(router, prefix=settings.api_prefix)
    app.mount("/", OrbitStaticFiles(directory=frontend_dist, html=True), name="frontend")
else:
    app.include_router(router, prefix=settings.api_prefix)

    @app.get("/")
    async def root() -> dict[str, str]:
        return {"name": settings.app_name, "docs": "/docs"}

import asyncio
import logging
import time
from pathlib import Path
from urllib.parse import urlparse

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from . import __version__
from .config import get_settings
from .agent_tools import router as tools_router
from .api import chat as chat_api, inventory as inventory_api, session as session_api
from .db import engine

settings = get_settings()
log = logging.getLogger("raahi")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.async_database_url.startswith("sqlite"):  # local dev only; Supabase uses supabase/migrations
        from .seed import init_db
        await init_db()
    warm = asyncio.create_task(_warm_up())  # don't block startup; the first real request finds a warm pool and cache
    yield
    warm.cancel()


async def _warm_up():
    """Open the DB pool and load static inventory so the first Sarvam tool call is not a cold one (R1, R2)."""
    try:
        from .db import SessionLocal
        from datetime import timedelta

        from .scouts import _cached, _load_static, find_place, search_flights, search_hotels
        from .timeutil import today_ist
        async with SessionLocal() as s:
            await _cached("static", lambda: _load_static(s))
            await find_place(s, "Paytm Marol office")
            await search_hotels(s, "DEL")
            tomorrow = today_ist() + timedelta(days=1)  # the hero demo: tomorrow out, two days later back
            await search_flights(s, "BOM", "DEL", tomorrow)
            await search_flights(s, "DEL", "BOM", tomorrow + timedelta(days=2))
        log.info("warm-up done")
    except Exception as e:
        log.warning("warm-up failed: %s", type(e).__name__)


app = FastAPI(title="Raahi", version=__version__, lifespan=lifespan)
app.include_router(chat_api.router)
app.include_router(inventory_api.router)
app.include_router(tools_router)
app.include_router(session_api.router)

STATIC_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"


_last_db_failure: dict = {"at": 0.0, "body": None}
RETRY_AFTER_AUTH_FAILURE_S = 60


@app.get("/healthz")
async def healthz():
    """Always 200 so Render keeps the service up; `db` says whether Postgres is reachable. Errors are redacted."""
    db_ok, err, db_ms = True, None, None
    # After an auth failure, do not retry for a minute: Render pings /healthz every 10 s and every bad login keeps
    # Supabase's circuit breaker (ECIRCUITBREAKER) open.
    f = _last_db_failure
    if f["body"] and time.monotonic() - f["at"] < RETRY_AFTER_AUTH_FAILURE_S:
        return {**f["body"], "cached": True}
    try:
        async with asyncio.timeout(20):
            async with engine.connect() as conn:
                await conn.execute(text("select 1"))
                t0 = time.perf_counter()
                await conn.execute(text("select 1"))  # one warm round trip: the number that decides planning speed
                db_ms = round((time.perf_counter() - t0) * 1000)
    except Exception as e:  # never include str(e) raw: guard against anything that looks like a connection string
        db_ok, err = False, type(e).__name__
        orig = getattr(e, "orig", None) or e
        detail = f"{type(orig).__name__}: {str(orig)[:140]}"
        if "@" in detail or "://" in detail or "password" in detail.lower():
            detail = type(orig).__name__
        err = f"{err} / {detail}"
        log.error("healthz db check failed: %s", err)
    host = urlparse(settings.async_database_url).hostname if settings.database_url else "sqlite"
    body = {"status": "ok" if db_ok else "degraded", "db": db_ok, "db_error": err, "db_host": host, "db_roundtrip_ms": db_ms,
            "version": __version__, "commit": settings.commit}
    from .agent_tools import LAST_AUTH_FAILURE
    if LAST_AUTH_FAILURE:
        body["last_tool_auth_failure"] = dict(LAST_AUTH_FAILURE)
    if not db_ok and any(k in (err or "") for k in ("authentication", "ECIRCUITBREAKER", "password", "Tenant or user")):
        f["at"], f["body"] = time.monotonic(), body
    else:
        f["body"] = None
    return body


if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse({"error": "not_found"}, status_code=404)
        candidate = (STATIC_DIR / path).resolve()
        if path and candidate.is_file() and STATIC_DIR in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(STATIC_DIR / "index.html")

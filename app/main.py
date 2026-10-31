import asyncio
import logging
from pathlib import Path
from urllib.parse import urlparse

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from . import __version__
from .config import get_settings
from .api import chat as chat_api, inventory as inventory_api
from .db import engine

settings = get_settings()
log = logging.getLogger("raahi")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.async_database_url.startswith("sqlite"):  # local dev only; Supabase uses supabase/migrations
        from .seed import init_db
        await init_db()
    yield


app = FastAPI(title="Raahi", version=__version__, lifespan=lifespan)
app.include_router(chat_api.router)
app.include_router(inventory_api.router)

STATIC_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"


@app.get("/healthz")
async def healthz():
    """Always 200 so Render keeps the service up; `db` says whether Postgres is reachable. Errors are redacted."""
    db_ok, err = True, None
    try:
        async with asyncio.timeout(20):
            async with engine.connect() as conn:
                await conn.execute(text("select 1"))
    except Exception as e:  # never include str(e): it can contain the connection string
        db_ok, err = False, type(e).__name__
        log.error("healthz db check failed: %s", err)
    host = urlparse(settings.async_database_url).hostname if settings.database_url else "sqlite"
    return {"status": "ok" if db_ok else "degraded", "db": db_ok, "db_error": err, "db_host": host,
            "version": __version__, "commit": settings.commit}


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

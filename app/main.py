from pathlib import Path

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
    db_ok = True
    try:
        async with engine.connect() as conn:
            await conn.execute(text("select 1"))
    except Exception:
        db_ok = False
    body = {
        "status": "ok" if db_ok else "degraded",
        "db": db_ok,
        "version": __version__,
        "commit": settings.commit,
    }
    return JSONResponse(body, status_code=200 if db_ok else 503)


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

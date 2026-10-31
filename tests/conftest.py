import os
from pathlib import Path

# Tests always use a throwaway SQLite file, never the real Supabase database from .env.
_DB = Path(__file__).parent / "test.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_DB.as_posix()}"
os.environ["AGENT_TOOL_SECRET"] = "test-secret"
os.environ["DEMO_ADMIN_PIN"] = "1234"

import pytest_asyncio  # noqa: E402

from app import models as m  # noqa: E402
from app import seed  # noqa: E402
from app.db import engine  # noqa: E402


import sqlalchemy as sa  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402


@sa.event.listens_for(Session, "before_flush")
def _enforce_varchar_lengths(session, *_):
    """SQLite ignores VARCHAR(n); Postgres rejects overflows. Fail the test the way Postgres would."""
    for obj in list(session.new) + list(session.dirty):
        for col in obj.__table__.columns:
            n = getattr(col.type, "length", None)
            v = getattr(obj, col.key, None)
            if n and isinstance(v, str) and len(v) > n:
                raise AssertionError(f"{obj.__tablename__}.{col.key} = {v!r} exceeds VARCHAR({n})")


@pytest_asyncio.fixture(loop_scope="function", autouse=True)
async def fresh_db():
    async with engine.begin() as conn:
        await conn.run_sync(m.Base.metadata.drop_all)
        await conn.run_sync(m.Base.metadata.create_all)
    await seed.seed()
    yield
    await engine.dispose()

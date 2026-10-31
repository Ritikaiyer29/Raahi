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


@pytest_asyncio.fixture(loop_scope="function", autouse=True)
async def fresh_db():
    async with engine.begin() as conn:
        await conn.run_sync(m.Base.metadata.drop_all)
        await conn.run_sync(m.Base.metadata.create_all)
    await seed.seed()
    yield
    await engine.dispose()

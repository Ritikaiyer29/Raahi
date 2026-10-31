from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import get_settings

_settings = get_settings()
_url = _settings.async_database_url

_connect_args: dict = {}
if _url.startswith("postgresql+asyncpg"):
    # Supavisor transaction mode (port 6543) does not support prepared statements.
    _connect_args = {"statement_cache_size": 0}

_pool: dict = {}
if _url.startswith("postgresql"):
    # Supabase's session-mode pooler allows only a small number of clients. Keep this process well under it.
    _pool = dict(pool_size=3, max_overflow=2, pool_recycle=300, pool_timeout=15)

engine = create_async_engine(_url, pool_pre_ping=True, connect_args=_connect_args, **_pool)

if _url.startswith("sqlite"):
    from sqlalchemy import event

    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_fks(dbapi_conn, _):
        # Enforce foreign keys locally too, so tests catch what Postgres would reject.
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session():
    async with SessionLocal() as session:
        yield session

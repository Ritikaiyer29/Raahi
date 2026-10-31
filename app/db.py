from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import get_settings

_settings = get_settings()
_url = _settings.async_database_url

_connect_args: dict = {}
if _url.startswith("postgresql+asyncpg"):
    # Supavisor transaction mode (port 6543) does not support prepared statements.
    _connect_args = {"statement_cache_size": 0}

engine = create_async_engine(_url, pool_pre_ping=True, connect_args=_connect_args)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session():
    async with SessionLocal() as session:
        yield session

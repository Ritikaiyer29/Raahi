# Decisions

- **Migrations:** SQLAlchemy models are the source of truth; `supabase/migrations/0001_init.sql` will be generated from them (plain SQL, no Alembic).
- **Local dev DB:** if `DATABASE_URL` is empty the backend uses SQLite so tests run without Supabase. Production uses the Supavisor pooler (asyncpg, `statement_cache_size=0` so transaction mode also works).
- **Python in Docker:** 3.12-slim (requirement was 3.11+).
- **Brand:** text wordmark only; the skyline illustration you supplied is used on the Home card.

# Decisions

- **Migrations:** SQLAlchemy models are the source of truth; `supabase/migrations/0001_init.sql` is generated from them (`python -m app.gen_sql`, plain SQL, no Alembic).
- **Local dev DB:** if `DATABASE_URL` is empty the backend uses SQLite so tests run without Supabase. Production uses the Supavisor session pooler (asyncpg, `statement_cache_size=0` so transaction mode also works).
- **Python in Docker:** 3.12-slim (requirement was 3.11+).
- **Brand:** text wordmark only; the skyline illustration supplied by the team is used on the Home card.
- **Render plan:** free by default (no card). Switch to Starter for demo day (R1).
- **`/healthz` always returns 200** and reports `db`, `db_error` (class name only) and `db_host`, so a DB problem shows as a readable message instead of a failed deploy.
- **Delhi terminals:** all seeded DEL flights use T3 so the Airport Express connects. Fictional airlines and flight numbers.
- **Return flights** depart at 14:00 or later by default (after hotel check-out). Demo assumption.
- **One orchestrator, two doors:** app API and Sarvam tool API call the same trip service; no logic is duplicated in the voice prompt.
- **Plan first (v2):** missing origin defaults to the user's saved base (demo: Paytm Marol office) and missing date to tomorrow, both shown as editable chips. The only pre-plan question is a missing destination.
- **Near-tie is not a question (v2):** when two options are within 5 %, both are shown; the cheaper is Raahi's pick. ASK is reserved for checkout-time problems (price drift, waitlist).
- **Voice tool input:** tools receive the raw utterance and re-parse it with the same Concierge, so voice and chat cannot disagree.
- **Sarvam tool auth:** the bearer secret is stored as a credential in the Sarvam console (the MCP refuses to set auth, by design). Timeout 20 s.
- **Entertainment and dining** are partner inventory (mock) with a visible badge; never presented as Paytm's catalogue.

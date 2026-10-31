# Changelog

## M0 – Skeleton (local)
- FastAPI app with `/healthz` (DB check, version, commit) serving the built React app
- Multi-stage Dockerfile, `render.yaml`, `.env.example`
- React + Vite + Tailwind shell with Paytm theme, service grid, and your skyline illustration (`frontend/public/brand/skyline.png`)

## M1 – Data + brains
- 32-table schema (`app/models.py`) -> `supabase/migrations/0001_init.sql` via `python -m app.gen_sql`; RLS on, anon/authenticated revoked. Applied to Supabase.
- Idempotent seed: Mumbai Aqua/Line 1, Delhi Airport Express/Yellow, 10 days of BOM<->DEL flights, trains, buses, hotels, add-ons, demo user Anika
- Checker (10 deterministic rules, thresholds in `app/checker/config.py`), Planner (door-to-door, rejected options kept with reason), Scouts
- Intent parsing for English/Hindi/Hinglish; `POST /api/chat`, `GET /api/trips/{id}`, `/api/agent-events`, `/api/inventory/*`
- 15 tests (checker, planner, intent, chat flow, inventory)

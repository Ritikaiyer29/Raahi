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

## v2 step 1–2 – Tool endpoints, plan first, checkout
- Sarvam tool API `/api/agent/tools/*` (9 tools): bearer auth, 4-digit session code (spoken when a call starts without one), speakable contract, sensitive-data refusal, rate limit
- Plan first: only a missing destination is asked; origin/date defaults and all choices returned as editable `assumptions` chips; chip edits re-plan in place
- Year inference ("5th November"), Hindi month names; near-ties shown instead of asked; 8 s planning budget with a clean timeout reply
- Checkout: cart, add-ons, idempotent approval, price-drift ASK at checkout, atomic mock booking with DEMO tickets; support cases (Handoff)
- Performance: inventory cache, startup warm-up, batched writes (39 → 16 queries per plan); `/healthz` reports `db_roundtrip_ms`
- Postgres fixes found by a live run: deferred foreign keys (0003), `carts.status` length (0004); tests now enforce FKs and VARCHAR lengths
- Migrations 0002–0004 applied to Supabase; 26 tests

## Frontend + realtime
- Sessions: the app opens one and shows its 4-digit Raahi code; phone calls and chat attach to it (`?session=<code>` opens one elsewhere)
- `/api/conversations/{id}/stream`: SSE sending the whole session state on every change (messages, chips, plans, cart, tickets, agent events), heartbeat 15 s; polling fallback
- React app: Home, Trip (chat, chips, plan cards with timeline and checks, rejected card), auto-opening approval sheet, Wallet with QR tickets, live Agent activity panel, EN/हिंदी
- Sarvam agent v1 deployed on +91 80642 69831; call script in docs/DEMO_DAY.md

## Travel-agent conversation + trains
- Raahi asks what was not said (flight or train, return or one way, hotel), at most two things in one natural sentence; follow-ups acknowledge the answer; "you decide" skips questions
- Train planning: Aqua Line extended to Mumbai Central, Rajdhani overnight with class choice and availability, New Delhi metro to CP; flight-or-train comparison
- Optional hotel, one-way plans, past departures never offered, arrive-by only when stated
- Chips for flight/train and hotel; train legs in the timeline; voice turn carries the session code
- Migration 0005 (trip_requests.preferences) applied; Supabase re-seeded; 36 tests

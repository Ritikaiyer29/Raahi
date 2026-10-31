# Raahi build plan (v2)

Principle: **The model plans. Code checks. The traveller pays once. A human handles exceptions.**
Tagline: **"The agent that connects every tile."**
Architecture: `docs/ARCHITECTURE.md`. Risks and preflight: `docs/RISKS.md`.

Status: [ ] todo · [~] in progress · [x] done. OPTIONAL items are cut first.

## Done so far
- [x] `choose_disruption_option` returns an honest "not available yet" until the Guardian lands (step 4)
- [x] FastAPI + React shell in one Docker image, `/healthz`, `render.yaml` (free plan), live on Render
- [x] Supabase schema (32 tables, RLS on), migration applied, demo seed
- [x] Checker (10 rules), intercity Planner with rejected options, rules parser (EN, HI, Hinglish), `/api/chat`, inventory API, agent events
- [x] 15 tests

## 1. Tool endpoints deployed
- [x] `/api/agent/tools/*` with bearer auth, session code binding, response contract (`ok, say_en, say_hi, missing_slots, assumptions, next_action, errors`)
- [x] Tools: `get_session_context`, `plan_trip`, `get_plan_details`, `modify_plan`, `send_for_approval`, `get_booking_status`, `get_trip_status`, `choose_disruption_option`, `request_human_help`
- [x] Startup warm-up + inventory cache (R1, R2)

## 2. Plan first, never stall (v2 §2.1, §2.2)
- [x] Defaults instead of questions; `assumptions` array in `/api/chat` and `plan_trip`
- [x] Ask only when the destination is unknown (one question). Origin defaults to the user's saved base; date defaults to tomorrow, shown as a chip
- [x] Year inference ("5th November" → next occurrence in IST)
- [ ] Place inference ("Borivali, Mumbai" never triggers "depart from Mumbai?")
- [x] Near-tie no longer asks: the alternative is shown as option 2
- [x] `POST /api/conversations/{id}/assumptions` re-plans in place
- [x] 8 s planning budget; timeout → last plan or retry + `agent_events.status = timeout`

## 3. Coverage, first and last mile (v2 §2.3)
- [ ] Borivali in places/metro data; legs outside inventory shown as "Not covered by Paytm inventory in this prototype"
- [ ] International destination → plan Indian legs, mark the rest not covered
- [ ] Train candidate in intercity planner (waitlist → ASK at checkout)

## 4. Commute, checkout, wallet, Guardian
- [ ] `plan_type` on `trip_requests`/`trips`; plan-type plug-in interface
- [ ] Commute plan type + `commute_buffer` rule, "leave by" time
- [x] Select plan, cart, add-ons, approval (idempotent), atomic mock booking, tickets with QR payloads
- [x] Live session stream `/api/conversations/{id}/stream` (full state on every change, heartbeat) + polling fallback
- [ ] Guardian loop, `/api/demo/inject-delay`, alert with 3 options, choice applied ("Raahi noticed your flight is delayed")
- [x] UI: Home with Raahi code + call button, service tiles + inventory lists, chat (voice turns marked), editable assumption chips, plan cards with door-to-door timeline and checks, rejected card, auto-opening approval sheet with add-ons, wallet with QR tickets, live agent activity panel, EN/हिंदी toggle
- [ ] Guardian alert sheet
- [ ] `/demo` panel (PIN): reset, re-seed, inject delay, replay demo sentence

## 5. Sarvam phone agent (v2 §4)
- [x] Verified workspace capabilities via MCP (31 Oct): HTTP tools with bearer credential, `resp_template`, timeout ≤ 30 s; **0 telephony connections / numbers / deployments**
- [x] Agent created (draft `Raahi---Pay-56850687-568d`): 9 tools, prompt, voicemail, nudges, call goal. Not yet committed.
- [x] Tool secret stored and selected on the 9 tools
- [x] Chat tests on the draft: plan, approval, booking status, card refusal, human handoff
- [ ] Real phone call test (call the number)
- [x] Number +91 80642 69831 bought and onboarded (vobiz connection)
- [x] Version 1 committed and deployed to +91 80642 69831 (24/7)
- [ ] `docs/SARVAM_SETUP.md`, call script in `docs/DEMO_DAY.md`, backup video

## 6. Day plans (v2 §3A.2)
- [ ] `movies`, `movie_shows`, `restaurants`, `activities` (demo, `source` field, partner badge)
- [ ] One template: travel → show → dinner → home, with the 8 day-plan rules and a rejected card
- [ ] `plan_day` tool

## 7. OPTIONAL
- [ ] `.ics` calendar export
- [ ] Messaging (`app/messaging/`, WhatsApp Cloud API test number)
- [ ] Traveller profile + `name_matches_id`, `passport_validity`, DigiLocker (mock)

## 8. Docs and demo
- [ ] `app/preflight.py`; README with real / mocked / roadmap; DEMO_DAY script; tag `demo-stable`; record video

Never cut: a plan from one sentence, the rejected card, one cart with one approval, the trip wallet, a delay alert that changes the trip.

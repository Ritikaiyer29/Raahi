# Raahi build plan

Principle: **The model plans. Code checks. The traveller pays once. A human handles exceptions.**

Status legend: [ ] todo · [~] in progress · [x] done

## M0 – Skeleton live
- [x] Repo layout, `docs/PLAN.md`
- [x] FastAPI app with `/healthz` (DB check, version, commit), serves built frontend
- [x] Multi-stage `Dockerfile`, `render.yaml`, `.env.example`
- [x] React + Vite + Tailwind shell, Paytm theme, skyline illustration (`public/brand/skyline.png`)
- [~] Supabase connected + migration applied + seeded; Render deploy pending

## M1 – Data + brains
- [x] SQLAlchemy models + `supabase/migrations/0001_init.sql` (RLS on, no anon policies)
- [x] Idempotent seed (`python -m app.seed`)
- [x] Scouts, Planner, Checker (`app/checker/`), intent parsing + fallback, `POST /api/chat`
- [x] Tests: checker, planner, intent

## M2 – Core UI
- [ ] Home + service grid, conversation + slot chips, plan options + rejected card
- [ ] Checkout + simulated approval, trip wallet + QR, SSE, agent activity panel

## M3 – Sarvam
- [ ] Agent tool endpoints + auth + response contract, `sarvam/` prompt + tools, `docs/SARVAM_SETUP.md`

## M4 – Guardian + Handoff
- [ ] Status feed, delay injection, alert UI, support console, demo panel

## M5 – Polish
- [ ] Hindi strings, loading/empty/error states, docs, demo rehearsal

Cut order if short: in-app STT/TTS, buses, Travel Pass screen, Playwright.
Never cut: Checker + rejected option, one-payment checkout, trip wallet, Guardian delay flow, agent activity panel.

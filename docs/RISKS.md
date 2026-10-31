# Hackathon risk register

Each risk has a fix we build and a fallback for the stage. Status: [x] done · [ ] todo.

| # | Risk on the day | Fix in the product | Fallback on stage |
|---|---|---|---|
| R1 | **Render free tier sleeps.** First request takes 30 to 60 s, so a Sarvam tool call times out | [ ] Startup warm-up (open DB pool, load inventory cache). [ ] External pinger on `/healthz` every 10 min. Set Sarvam tool timeout to 20 s, not the default 8 | Switch to the Starter plan for demo day. Open `/healthz` 5 min before presenting |
| R2 | **Slow DB link.** Supabase is in Paris; the first connect from India took 7 s | [ ] In-memory inventory cache (60 s). [ ] Fewer round trips per plan. Check the Render region is Frankfurt, the closest to Paris | Pre-run the demo sentence once before going on stage |
| R3 | **No phone number in Sarvam.** The workspace has 0 connections, 0 numbers, 0 deployments (checked 31 Oct) | Buy a number in the Sarvam dashboard, onboard it, deploy a committed agent version. Test with a verified-number test call first | A test call where the agent dials a verified phone (no number to buy). Then app chat with the same flow |
| R4 | **Judges call at the same time,** with unknown Sarvam concurrency | Session code per call means each caller gets their own conversation and trip. [ ] Each new session gets its own demo user, not a shared "Anika" | Ask one judge at a time. Show the code on the projector |
| R5 | **Stage Wi-Fi fails** | `docker run` the same image on the laptop with SQLite and local seed | Phone hotspot. Pre-recorded backup video |
| R6 | **Dates drift.** Seed is relative to the seed day, and "the 24th" changes meaning | [ ] Re-seed on demo morning. [ ] Preflight script checks flights exist for the next 10 days | `/demo` panel: Reset + Re-seed buttons |
| R7 | **LLM variance** gives a different parse or a hallucinated price | The LLM never picks options or prices. Schema-validated output. The rules parser always handles the demo sentence. Prices only come from tools | Turn the LLM off (`SARVAM_LLM_MODEL` empty) and the rules parser runs alone |
| R8 | **A deploy breaks the live demo** (Render auto-deploys every push) | [ ] Tag `demo-stable`, turn off auto-deploy 2 h before the slot. Tests pass before each push | Redeploy the tag from the Render dashboard |
| R9 | **The agent stalls** ("fetching…" with no result) | [ ] 8 s budget per plan. On timeout: last plan or a Retry button, plus an `agent_events` row with status `timeout` | "Replay demo sentence" button on `/demo` |
| R10 | **Two judges overwrite each other's trip** | Revision check on every write. Idempotency key on approval and disruption choices | Reset only that session |
| R11 | **Public URL abuse,** or a judge pokes the demo controls | PIN on `/api/demo/*`. [ ] Rate limit. Message length cap (1000) | Change `DEMO_ADMIN_PIN` in Render |
| R12 | **Secrets leak** in a screenshot or the repo | `.env` gitignored. Health check redacts errors. Keys only in Render and the Sarvam console | Rotate the Supabase DB password and the tool secret after the event |
| R13 | **Overclaiming** (judges ask "is this real?") | "DEMO" watermarks. "Partner inventory (mock)" badges. README lists real, mocked and roadmap. Agent count stated as "N of 7 built" | Say it plainly: mocked bookings, real rules and planning |
| R14 | **Checkin comparison backfires** | Product copy never names Checkin. Pitch uses our own 31 Oct screenshots only | Do not run Checkin live |
| R15 | **Scope overrun** | Strict order in `docs/PLAN.md`. Never-cut list | Skip day plans. The hero trip alone carries the demo |
| R16 | **Hindi voice reads English text** | Each tool returns `say_en` and `say_hi`. [ ] Test which one Sarvam speaks when the caller switches to Hindi | Keep the voice demo in English or Hinglish |
| R17 | **Approval tapped twice** | Idempotency key. The approve button disables after the first tap | n/a |

## Preflight (run 30 min before the slot)

`python -m app.preflight --base https://<service>.onrender.com` (to build) checks:
1. `/healthz` reports `db: true` in under 2 s, with the expected commit.
2. Flights exist for tomorrow and the return date.
3. The demo sentence returns `plan_ready`, with the 06:00 rejection, in under 5 s.
4. A tool call with the bearer secret returns `ok`. A call without it returns 401.
5. SSE sends a heartbeat within 20 s.

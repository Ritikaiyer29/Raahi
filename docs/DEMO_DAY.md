# Demo day

Live app: https://raahi-mtoy.onrender.com · Phone: **+91 80642 69831** · Agent: `Raahi---Pay-56850687-568d` v1

## 10 minutes before

1. Open `https://raahi-mtoy.onrender.com/healthz`. Expect `"db": true` and `db_roundtrip_ms` around 10. The free plan sleeps after 15 min idle, so this also wakes it. (Better: switch Render to Starter for the day.)
2. Open the app on the projector laptop (desktop width shows the phone frame plus the live Agent activity panel). Tap the ↻ button for a fresh trip. Note the 4-digit Raahi code on Home.
3. Do one quick rehearsal call (script below), then ↻ again for a clean session.

## The call script (about 2 minutes)

Keep the app on screen; everything the caller does appears there live.

| # | Caller says | Raahi should | Screen shows |
|---|---|---|---|
| 1 | *(dial +91 80642 69831)* | "Namaste, this is Raahi, the Paytm travel assistant. Where would you like to travel?" | nothing yet |
| 2 | "My Raahi code is **4 8 2 1**. I'm at Paytm's Marol office. I need to be at Connaught Place by lunch tomorrow, back on the 24th. Keep it cheap." | A short filler ("checking Paytm flights and metro timings"), then the plan: Aqua Line to T1, 08:30 flight, Airport Express, hotel 2 nights, back on the return date, **total ₹13,220**, "Shall I send it to your Paytm screen?" | Trip screen opens by itself: chat bubbles marked *via phone*, assumption chips, Raahi's pick, options 2 and 3, the **Rejected 06:00 flight** card. Activity: Concierge → Scouts → Planner → Checker |
| 3 | "What's the plan in detail?" *(optional)* | Leg by leg with times | same |
| 4 | "Yes, send it. Add the cancellation cover." | "Sent to your Paytm screen… total ₹13,319… nothing is charged until you approve." | **Approval sheet pops up by itself** with every leg and the ₹99 cover ticked. Activity: Checkout create cart |
| 5 | "Is it booked?" | "Not booked yet, it's waiting for your approval on the Paytm screen." | unchanged |
| 6 | *(tap **Approve ₹13,319 (demo)** on screen)* | | Wallet opens: 8 DEMO tickets with QR codes. Activity: Checker price drift 0%, Checkout book all legs |
| 7 | "Is it booked now?" | "Booked. 8 tickets in your trip wallet… flight reference P N R …, these are demo bookings." | |
| 8 | "Thanks, bye." | Thanks you and ends the call | |

Use the code shown on **your** screen in step 2. If the caller forgets the code, Raahi still plans and speaks a new code; open `https://raahi-mtoy.onrender.com/?session=<that code>` to show it.

### Safety moments (pick one if judges ask)

- "Can you take my card number? It's 4111…" → Raahi stops the caller: payment is approved only on the Paytm screen.
- "My last refund never came, I want a person." → Raahi opens a support case and reads the case number.
- "Are you a real person?" → Raahi says it is an AI travel assistant and people handle exceptions.

### Hindi / Hinglish

Try once in rehearsal: "Mujhe kal lunch tak Marol se Connaught Place jaana hai, 24 ko wapas, sasta chahiye." The planner understands it; whether Sarvam speaks the reply in Hindi on a live call is **not yet verified**. If it answers in English, keep the stage demo in English.

## If something fails

| Problem | Do this |
|---|---|
| Call does not connect or Raahi says the system is slow | Check `/healthz`. Then run the same sentence in the app chat (Trip tab, type it). Same backend, same result |
| `/healthz` shows `db: false` | Wait 1 minute and reload (Supabase pooler hiccup). Persisting: check `DATABASE_URL` in Render |
| Tool calls 401 | `/healthz` shows `last_tool_auth_failure` lengths. The Sarvam secret must equal Render's `AGENT_TOOL_SECRET` exactly |
| Screen does not update | The header code must match the one said on the call. Reload the page (it resumes the session) |
| Anything else | Play the backup video |

## What is real and what is mocked

Real: the planner, the 10 Checker rules (including the first-metro rejection), the one-cart approval with idempotency, the live screen updates, the Sarvam voice agent and its tools, the support case handoff.
Mocked: flights, hotels, trains and fares (fictional demo inventory), metro hours and fares (demo assumptions), bookings, PNRs and payment (all `DEMO-`). Trip Guardian (delay alerts) is next.

## Pitch line

The model plans. Code checks. The traveller pays once. A human handles exceptions.

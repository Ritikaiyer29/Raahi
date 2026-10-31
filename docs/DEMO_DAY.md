# Demo day runbook

Live app: https://raahi-mtoy.onrender.com · Phone: **+91 80642 69831** · Sarvam agent `Raahi---Pay-56850687-568d`, version 2
Stage script for the judges: `docs/JUDGES_SCRIPT.md`.

## 10 minutes before

1. Open `https://raahi-mtoy.onrender.com/healthz`. Expect `"db": true` and `db_roundtrip_ms` around 10. The free plan sleeps after 15 min idle; this wakes it. (Better: switch Render to Starter for the day.)
2. Open the app on the projector laptop at full width: phone frame on the left, live **Agent activity** on the right. Tap ↻ for a fresh trip. Note the 4-digit Raahi code on Home.
3. Do one full rehearsal call (below), then ↻ again for a clean session.
4. Phone on loudspeaker, volume up, hotspot ready.

## The call (about 2.5 minutes)

| # | Caller says | Raahi should say | Screen shows |
|---|---|---|---|
| 1 | *(dial +91 80642 69831)* | "Namaste, this is Raahi, the Paytm travel assistant. Where would you like to travel?" | Home with the code |
| 2 | "My Raahi code is **_ _ _ _**. I'm at Paytm's Marol office. I need to be at Connaught Place by lunch tomorrow, back on the 24th. Keep it cheap." | Asks, like a travel agent, only what you did not say: *"Connaught Place by lunch tomorrow, got it. Would you like to fly, or is the overnight Rajdhani okay? And shall I book you a stay near Connaught Place for the two nights?"* | Trip screen opens by itself, your words marked *via phone*. Activity: **Concierge · asking about mode, hotel** |
| 3 | "I'd rather fly. And yes, book the hotel." | Short filler, then: Aqua Line to the airport, the 8:30 BlueKite flight, Connaught Place by 11:44, Hotel Janpath for two nights, back on 3 Nov at 6:40 PM, **₹13,220**. "Shall I send it to your Paytm screen?" | Activity: Concierge → Scouts → Planner → **Checker (3 passed, 2 rejected)**. Chips, Raahi's pick, options 2 and 3, and the **Rejected 06:00 flight** card |
| 4 | "Yes, send it. Add the cancellation cover." | "Sent to your Paytm screen… ₹13,319… nothing is charged until you approve." | **Approval sheet pops up by itself**, ₹99 cover ticked |
| 5 | "Is it booked?" | "Not yet, it's waiting for your approval on the Paytm screen." | unchanged |
| 6 | *(tap **Approve ₹13,319 (demo)**)* | | Wallet: 8 DEMO tickets with QR codes. Activity: Checker price drift 0%, Checkout book all legs |
| 7 | "Is it booked now?" | "Booked. 8 tickets in your trip wallet… flight reference P N R …, demo bookings." | |
| 8 | "Thanks, bye." | Thanks you and ends the call | |

Variants that also work: answer step 2 with **"Whichever is cheaper"** (Raahi compares flights and trains and picks the Rajdhani tonight, about ₹11,340), or with **"You decide"** (no questions, plans straight away). Use the code shown on **your** screen. If the caller forgets it, Raahi speaks a new code first; open `https://raahi-mtoy.onrender.com/?session=<that code>`.

### Safety moments (if judges ask)

- Read out a fake card number or OTP → Raahi stops you: payment is approved only on the Paytm screen.
- "My last refund never came, I want a person." → Raahi opens a support case and reads the case number.
- "Are you a real person?" → Raahi says it is an AI travel assistant and people handle exceptions.

### Hindi / Hinglish

The planner and its questions work in Hindi and Hinglish in the app. On a live call, whether Sarvam speaks the reply in Hindi is **not yet verified**. Rehearse once; if it answers in English, keep the stage demo in English.

## If something fails

| Problem | Do this |
|---|---|
| Call does not connect, or Raahi says the system is slow | Check `/healthz`. Then type the same sentences in the app's Trip tab: same backend, same result |
| `/healthz` shows `db: false` | Wait a minute and reload (pooler hiccup). If it persists, check `DATABASE_URL` in Render |
| Tool calls return 401 | `/healthz` shows `last_tool_auth_failure` lengths. The Sarvam secret must equal Render's `AGENT_TOOL_SECRET` exactly |
| Screen does not update | The code in the header must match the one said on the call. Reload the page (it resumes the session) |
| Anything else | Play the backup video |

## What is real and what is mocked

Real: the travel-agent conversation and parsing, the door-to-door planner for flights and trains, the 10 Checker rules (including the first-metro rejection), one cart with an idempotent approval, the live screen, the Sarvam voice agent and its 9 tools, the support-case handoff.
Mocked: flights, trains, hotels and fares (fictional demo inventory), metro hours and fares (demo assumptions), bookings, PNRs and payment (all `DEMO-`). Trip Guardian (delay alerts) is next.

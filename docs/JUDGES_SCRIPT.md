# Raahi: script for the judges (about 5 minutes)

Two people: **Presenter** speaks to the judges; **Caller** makes the phone call. Projector shows the app at full width
(phone frame on the left, Agent activity on the right). Times are cumulative.

---

## 0:00 · The problem (30 s)

> **Presenter:** Paytm already sells every piece of a trip: metro QR tickets, flights, IRCTC trains, buses, hotels, insurance.
> But they are separate icons. To get from this office to a meeting in Delhi, you open five tiles, do the timing maths
> yourself, and pay five times.
>
> We are Raahi, राही, "the one on the road". **The agent that connects every tile.** One sentence in, one door-to-door plan out,
> one payment, and an agent that stays with you until you arrive.

Point at the Home screen: the service tiles, and the Raahi card with its 4-digit code.

## 0:30 · The principle (15 s)

> **Presenter:** One rule runs the whole system: **the model plans, code checks, the traveller pays once, and a human handles
> exceptions.** Watch the right-hand panel: every agent that works on this trip shows up there, live.

## 0:45 · Live call (2 min 30 s)

> **Presenter:** We'll book a real trip by phone. This is a Sarvam voice agent on a real Indian number.

**Caller** dials **+91 80642 69831** on loudspeaker.

| Caller | While Raahi works, Presenter says |
|---|---|
| *(greeting plays)* | "It's a phone call, not an app. Anyone can do this, in Hindi or English." |
| "My Raahi code is **_ _ _ _**. I'm at Paytm's Marol office. I need to be at Connaught Place by lunch tomorrow, back on the 24th. Keep it cheap." | "One long sentence: origin, deadline, return, budget." *(Raahi replies with two short questions)* "Notice it didn't fire ten questions at us. It only asked what we didn't say: fly or train, and do we need a hotel. Like a good travel agent." |
| "I'd rather fly. And yes, book the hotel." | Point at the activity panel: "Concierge understood it, Scouts searched Paytm's flights, trains, metro and hotels, the Planner built door-to-door options, and the **Checker**, plain code, no AI, validated every one." |
| *(Raahi reads the plan: ₹13,220)* | Point at the **Rejected** card: "This is my favourite part. The cheapest flight is at 6 a.m. Raahi rejected it on its own, because the first Aqua Line metro is at 6:30 and you can't reach the terminal in time. An LLM alone would have booked it." |
| "Yes, send it. Add the cancellation cover." | The approval sheet pops up on screen. "The phone can plan, but it can never pay. One cart: metro, flight, hotel, the return, the ₹99 cover. One approval, on the Paytm screen." |
| "Is it booked?" | "It won't claim it's booked until the system confirms it." |
| *(Presenter taps **Approve ₹13,319 (demo)**)* | The wallet opens. "One tap. Eight tickets: metro QR codes, both flights, the hotel voucher, the cover. All in one trip wallet." |
| "Is it booked now?" → "Thanks, bye." | "Now it says booked, and gives the reference." |

## 3:15 · Why this is agentic (45 s)

> **Presenter:** Four things make this an AI teammate, not a chatbot:
> 1. **It acts across systems**: metro, flights, trains, hotels and add-ons in one plan.
> 2. **It checks its own work**: ten deterministic rules. It showed you what it rejected, and why.
> 3. **Humans stay in control**: voice can never pay; one explicit approval, and double taps never double-book.
> 4. **It knows its limits**: card numbers on a call are refused, and disputes go to a person with the full timeline.

Optional, if time allows (10 s each): caller says *"Can you take my card number?"* (refused), or *"I want a person about a refund"* (case number).

## 4:00 · Architecture in one breath (30 s)

> **Presenter:** One FastAPI service on Render with two front doors: the Sarvam voice agent and the app. Both call the same trip
> service, so voice and screen can never disagree. Supabase Postgres holds every state change with a revision number, and the
> screen updates live over a stream. The LLM understands and talks; prices, timings and bookings are always plain code.

## 4:30 · Honest scope and what's next (30 s)

> **Presenter:** What's real today: the conversation, the planner for flights and trains, the ten checks, one-payment checkout,
> the live screen and the phone agent. What's mocked: the inventory and the bookings, all marked DEMO, because we don't have
> Paytm's APIs. Next: the Trip Guardian, which notices a delayed flight and calls you with options before you notice, plus daily
> commutes and day plans on the same engine.
>
> The model plans. Code checks. You pay once. A human handles exceptions. That's Raahi.

---

## If the call fails on stage

Say: *"Live networks at hackathons. Same brain, typed."* Then type the same two sentences into the app's Trip tab. Everything on
screen is identical. If the app also fails, play the backup video.

## Likely judge questions

| Question | Answer |
|---|---|
| Is the data real? | Inventory and bookings are demo data marked DEMO. The metro station order follows the real Aqua Line and Airport Express; first and last train times are demo assumptions. The planning and checking logic is real. |
| Why not let the LLM plan? | It can invent a 6 a.m. flight you can't reach. The LLM handles language; code handles time, money and safety, and every rule is testable. We have 37 automated tests. |
| What if two people call at once? | Each call is tied to its own 4-digit session code, and every write checks a revision number, so the app and the phone can't overwrite each other. |
| How does payment stay safe? | The voice agent has no payment tool. It can only create a cart. Approval is on screen, with an idempotency key, and the agent refuses card numbers and OTPs. |
| How would this ship inside Paytm? | Swap the demo inventory for Paytm's flight, IRCTC, metro and hotel partner APIs behind the same Scouts interface, and the simulated approval for Paytm's UPI flow. The Planner, Checker and voice layer stay. |
| Hindi? | The planner and its questions understand English, Hindi and Hinglish. The voice agent supports Hindi; on stage we demo in English. |
| Latency? | Backend in Frankfurt next to the database: a plan takes about a second; the call adds speech time. |

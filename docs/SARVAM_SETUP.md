# Sarvam voice agent setup

Status on 31 Oct 2026: agent created as a **draft** (not yet committed or deployed). The tools point at the Render URL below.

| Item | Value |
|---|---|
| Agent name | Raahi - Paytm Travel Teammate |
| Agent id | `Raahi---Pay-56850687-568d` |
| Phone number | +91 80642 69831 (vobiz connection `c3d7fc2b-88-7a4609d2-30e3`, onboarded) |
| Tool base URL | `https://raahi-wzf9.onrender.com/api/agent/tools/` (update all 9 tools if the Render URL changes) |
| Voice | Neha - Support Agent (`01a0cf16-98e5-7477-b1c4-73db8ad8ba82`), English + Hindi |
| Tool timeout | 25 s (Sarvam allows up to 30 s) |
| Prompt | `sarvam/agent_prompt.md` (the Sarvam draft is the source of truth) |

## One manual step the MCP cannot do: tool authentication

Sarvam stores the secret; our MCP session is not allowed to set auth. In the Sarvam console:
1. Secrets → add a secret named `RAAHI_TOOL_SECRET` with the **same value** as `AGENT_TOOL_SECRET` in Render.
2. Open the agent → each of the 9 tools → Auth → **Bearer** → choose `RAAHI_TOOL_SECRET`.

Without this, every tool call returns 401 and the agent says its "travel system is slow" line.

## Tools (all HTTP POST, response template `{{say_en}}`)

`plan_trip`, `get_session_context`, `get_plan_details`, `modify_plan`, `send_for_approval`, `get_booking_status`, `get_trip_status`, `choose_disruption_option` (`wait`, `later_flight`, `cancel_refund`), `request_human_help`.

The agent speaks exactly the `say_en` text our backend returns. `missing_slots`, `assumptions` and `next_action` stay in the JSON; the prompt tells the agent to follow the reply.

## Identity binding

`plan_trip` with no `session_code` creates a session and the reply ends with "Your Raahi code is 4 8 2 1". The agent passes that code to every later tool. The app opens the same session from the code (`GET /api/sessions/{code}`). The model never passes a user or trip id.

## Test

1. Chat test (no phone): `send_chat` against the draft, or the Sarvam console chat. Needs the auth step above.
2. Phone test: verify your own number in Sarvam, then `place_test_call`; the agent dials you.
3. Inbound: commit a version, then create a deployment on the number above.

## Known unknowns (TODO, test on a real call)

- Which language the call speaks when the caller switches to Hindi: our template always renders `say_en`.
- Sarvam's concurrent-call limit for this number is not visible through the API. Take one caller at a time.
- `choose_disruption_option` answers "not available yet" until the Guardian is built.

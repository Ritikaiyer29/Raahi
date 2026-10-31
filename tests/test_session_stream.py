import json

import httpx

from app.main import app

AUTH = {"Authorization": "Bearer test-secret"}
BASE = "I'm at Paytm's Marol office. I need to be at Connaught Place by lunch tomorrow, back on the 24th. Keep it cheap."
SENTENCE = BASE + " Flight please, and book a hotel near CP."


def client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def test_phone_call_on_a_session_code_shows_up_in_the_app_state():
    async with client() as c:
        sess = (await c.post("/api/sessions")).json()
        empty = (await c.get(f"/api/conversations/{sess['conversation_id']}/state")).json()
        assert empty["session_code"] == sess["session_code"] and empty["trip"] is None and len(empty["addons"]) == 3
        # the phone agent plans on the code shown on screen
        r = (await c.post("/api/agent/tools/plan_trip", json={"session_code": sess["session_code"], "request_text": SENTENCE},
                          headers=AUTH)).json()
        assert r["ok"]
        st = (await c.get(f"/api/conversations/{sess['conversation_id']}/state")).json()
        assert st["version"] != empty["version"]
        assert st["trip"]["plans"][0]["is_pick"] and any(p["status"] == "rejected" for p in st["trip"]["plans"])
        assert [m["role"] for m in st["messages"]] == ["user", "assistant"] and st["messages"][0]["channel"] == "voice"
        assert {a["slot"] for a in st["assumptions"]} >= {"party_size", "priority", "return_date"}
        agents = [e["agent"] for e in st["agent_events"]]
        assert agents[:4] == ["Concierge", "Scouts", "Planner", "Checker"]
        # voice sends the cart; the app sees it awaiting approval
        await c.post("/api/agent/tools/send_for_approval", json={"session_code": sess["session_code"]}, headers=AUTH)
        st2 = (await c.get(f"/api/sessions/{sess['session_code']}/state")).json()
        assert st2["trip"]["cart"]["status"] == "awaiting_approval" and "Checkout" in [e["agent"] for e in st2["agent_events"]]


async def test_stream_sends_current_state_first():
    async with client() as c:
        sess = (await c.post("/api/sessions")).json()
        await c.post("/api/chat", json={"message": SENTENCE, "conversation_id": sess["conversation_id"]})
        r = await c.get(f"/api/conversations/{sess['conversation_id']}/stream?once=true")
        assert r.headers["content-type"].startswith("text/event-stream")
        lines = r.text.splitlines()
        assert lines[0] == "id: 1" and lines[1] == "event: state"
        st = json.loads(lines[2].removeprefix("data: "))
        assert st["trip"]["plans"] and st["conversation_id"] == sess["conversation_id"]

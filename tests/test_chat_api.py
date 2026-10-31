import httpx

from app.main import app

SENTENCE = "I'm at Paytm's Marol office. I need to be at Connaught Place by lunch tomorrow, back on the 24th. Keep it cheap."


def client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def test_demo_sentence_end_to_end():
    async with client() as c:
        r = (await c.post("/api/chat", json={"message": SENTENCE})).json()
        assert r["status"] == "plan_ready" and r["triage"] == "AUTO"
        assert r["missing_slots"] == [] and r["slots"]["return_date"]
        assert "Total ₹" in r["reply_en"] and "send it to your Paytm screen" in r["reply_en"]
        assert r["rejected"][0]["rule_id"] == "first_last_metro"
        snap = (await c.get(f"/api/trips/{r['trip_id']}")).json()
        assert snap["trip"]["revision"] >= 1
        plans = snap["plans"]
        assert [p["status"] for p in plans].count("proposed") >= 2
        assert plans[0]["is_pick"] and plans[0]["legs"][0]["mode"] == "walk"
        assert any(p["status"] == "rejected" for p in plans)
        agents = [e["agent"] for e in (await c.get("/api/agent-events")).json()]
        assert agents[:4] == ["Concierge", "Scouts", "Planner", "Checker"]


async def test_asks_exactly_one_question_then_plans():
    async with client() as c:
        r = (await c.post("/api/chat", json={"message": "I want to go to Connaught Place"})).json()
        assert r["status"] == "need_info" and r["missing_slots"] == ["origin", "depart_date"]
        assert r["reply_en"].count("?") == 1
        r = (await c.post("/api/chat", json={"message": "from Marol, tomorrow", "conversation_id": r["conversation_id"]})).json()
        assert r["status"] in ("plan_ready", "ask") and r["trip_id"]


async def test_inventory_endpoints():
    async with client() as c:
        assert len((await c.get("/api/inventory/flights")).json()) > 5
        assert (await c.get("/api/inventory/metro?city=DEL")).json()[0]["first_train"]
        assert len((await c.get("/api/inventory/addons")).json()) == 3

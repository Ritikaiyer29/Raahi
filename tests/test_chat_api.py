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


async def test_plan_first_no_questions_and_assumptions():
    async with client() as c:
        r = (await c.post("/api/chat", json={"message": SENTENCE})).json()
        assert r["missing_slots"] == [] and r["reply_en"].count("?") == 1  # only "Shall I send it…?"
        slots = {a["slot"]: a for a in r["assumptions"]}
        assert slots["party_size"]["label_en"] == "1 traveller" and slots["priority"]["value"] == "economical"
        assert "flights only" not in r["reply_en"].lower()
        # Missing origin and date are assumed, not asked
        r = (await c.post("/api/chat", json={"message": "I want to go to Connaught Place"})).json()
        assert r["status"] == "plan_ready" and r["missing_slots"] == []
        assumed = {a["slot"] for a in r["assumptions"] if a["assumed"]}
        assert {"origin", "depart_date"} <= assumed


async def test_only_missing_destination_asks_one_question():
    async with client() as c:
        r = (await c.post("/api/chat", json={"message": "I need to travel tomorrow, keep it cheap"})).json()
        assert r["status"] == "need_info" and r["missing_slots"] == ["destination"] and r["reply_en"].count("?") == 1
        r = (await c.post("/api/chat", json={"message": "Connaught Place", "conversation_id": r["conversation_id"]})).json()
        assert r["status"] == "plan_ready"


async def test_editing_a_chip_replans_and_reranks():
    async with client() as c:
        r = (await c.post("/api/chat", json={"message": SENTENCE})).json()
        cheap = (await c.get(f"/api/trips/{r['trip_id']}")).json()["plans"][0]
        r2 = (await c.post(f"/api/conversations/{r['conversation_id']}/assumptions", json={"overrides": {"priority": "fastest"}})).json()
        assert r2["status"] == "plan_ready" and r2["revision"] > r["revision"]
        assert {a["slot"]: a for a in r2["assumptions"]}["priority"]["label_en"] == "Fastest"
        fast = (await c.get(f"/api/trips/{r['trip_id']}")).json()["plans"][0]
        assert fast["total_duration"] <= cheap["total_duration"]


async def test_checkout_one_approval_idempotent_and_atomic():
    async with client() as c:
        r = (await c.post("/api/chat", json={"message": SENTENCE})).json()
        snap = (await c.get(f"/api/trips/{r['trip_id']}")).json()
        rejected = next(p for p in snap["plans"] if p["status"] == "rejected")
        assert (await c.post(f"/api/plans/{rejected['id']}/select", json={})).status_code == 409
        cart = (await c.post(f"/api/plans/{snap['plans'][0]['id']}/select", json={})).json()
        total = (await c.post(f"/api/carts/{cart['cart_id']}/addons", json={"codes": ["CANCEL99"]})).json()["total"]
        assert total == cart["total"] + 99
        assert (await c.post(f"/api/carts/{cart['cart_id']}/approve")).status_code == 400  # no key
        h = {"Idempotency-Key": "test-key-1"}
        a1 = (await c.post(f"/api/carts/{cart['cart_id']}/approve", headers=h)).json()
        a2 = (await c.post(f"/api/carts/{cart['cart_id']}/approve", headers=h)).json()
        assert a1["status"] == "booked" and a1 == a2
        snap = (await c.get(f"/api/trips/{r['trip_id']}")).json()
        assert snap["trip"]["status"] == "booked" and snap["booking"]["status"] == "confirmed"
        types = [t["type"] for t in snap["tickets"]]
        assert types.count("flight") == 2 and "metro_qr" in types and "hotel" in types and "addon" in types
        assert all(t["ticket_no"].startswith("DEMO-") for t in snap["tickets"])


async def test_price_drift_asks_before_booking():
    from app.checkout import DEMO_FLAGS
    async with client() as c:
        r = (await c.post("/api/chat", json={"message": SENTENCE})).json()
        snap = (await c.get(f"/api/trips/{r['trip_id']}")).json()
        cart = (await c.post(f"/api/plans/{snap['plans'][0]['id']}/select", json={})).json()
        DEMO_FLAGS["price_drift_pct"] = 20
        try:
            a = (await c.post(f"/api/carts/{cart['cart_id']}/approve", headers={"Idempotency-Key": "k2"})).json()
        finally:
            DEMO_FLAGS["price_drift_pct"] = 0
        assert a["status"] == "ask" and a["reason"] == "price_drift"
        assert (await c.get(f"/api/trips/{r['trip_id']}")).json()["booking"] is None


async def test_inventory_endpoints():
    async with client() as c:
        assert len((await c.get("/api/inventory/flights")).json()) > 5
        assert (await c.get("/api/inventory/metro?city=DEL")).json()[0]["first_train"]
        assert len((await c.get("/api/inventory/addons")).json()) == 3

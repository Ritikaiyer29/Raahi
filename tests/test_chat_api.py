import httpx

from app.main import app

BASE = "I'm at Paytm's Marol office. I need to be at Connaught Place by lunch tomorrow, back on the 24th. Keep it cheap."
SENTENCE = BASE + " Flight please, and book a hotel near CP."


def client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def test_demo_sentence_end_to_end():
    async with client() as c:
        r = (await c.post("/api/chat", json={"message": SENTENCE})).json()
        assert r["status"] == "plan_ready" and r["triage"] == "AUTO"
        assert r["missing_slots"] == [] and r["slots"]["return_date"]
        assert "All in, ₹" in r["reply_en"] and "send it to your Paytm screen" in r["reply_en"]
        assert r["rejected"][0]["rule_id"] == "first_last_metro"
        snap = (await c.get(f"/api/trips/{r['trip_id']}")).json()
        assert snap["trip"]["revision"] >= 1
        plans = snap["plans"]
        assert [p["status"] for p in plans].count("proposed") >= 2
        assert plans[0]["is_pick"] and plans[0]["legs"][0]["mode"] == "walk"
        assert any(p["status"] == "rejected" for p in plans)
        agents = [e["agent"] for e in (await c.get("/api/agent-events")).json()]
        assert agents[:4] == ["Concierge", "Scouts", "Planner", "Checker"]


async def test_travel_agent_asks_two_things_naturally_then_plans():
    async with client() as c:
        r = (await c.post("/api/chat", json={"message": BASE})).json()
        # return date and "cheap" were said, so only flight/train and hotel are asked, in one sentence
        assert r["status"] == "need_info" and r["asking"] == ["mode", "hotel"] and r["assumptions"] == []
        assert r["reply_en"].count("?") == 2 and "Connaught Place" in r["reply_en"]
        r = (await c.post("/api/chat", json={"message": "Flight please, and yes book a hotel", "conversation_id": r["conversation_id"]})).json()
        assert r["status"] == "plan_ready" and r["asking"] == []
        chips = {a["slot"]: a for a in r["assumptions"]}
        assert chips["mode"]["label_en"] == "Flight" and chips["hotel"]["label_en"] == "Hotel stay"
        assert "flights only" not in r["reply_en"].lower()


async def test_only_asks_what_was_not_said():
    async with client() as c:
        r = (await c.post("/api/chat", json={"message": "BKC to Connaught Place tomorrow"})).json()
        assert r["status"] == "need_info" and r["asking"] == ["mode", "trip_type"]
        conv = r["conversation_id"]
        r = (await c.post("/api/chat", json={"message": "Train, and I'll be there for 2 days", "conversation_id": conv})).json()
        assert r["status"] == "need_info" and r["asking"] == ["hotel"]
        r = (await c.post("/api/chat", json={"message": "yes please", "conversation_id": conv})).json()
        assert r["status"] == "plan_ready"
        snap = (await c.get(f"/api/trips/{r['trip_id']}")).json()
        pick = snap["plans"][0]
        assert [l["mode"] for l in pick["legs"] if l["mode"] in ("train", "flight")] == ["train", "train"]
        assert any(l["mode"] == "hotel" for l in pick["legs"]) and "Rajdhani" in r["reply_en"]


async def test_you_decide_skips_questions_and_compares_flights_with_trains():
    async with client() as c:
        r = (await c.post("/api/chat", json={"message": "Marol to Connaught Place by lunch tomorrow, back on the 24th, cheap. You decide."})).json()
        assert r["status"] == "plan_ready"
        chips = {a["slot"]: a for a in r["assumptions"]}
        assert chips["mode"]["value"] == "any" and chips["mode"]["assumed"] and chips["hotel"]["value"] is True
        snap = (await c.get(f"/api/trips/{r['trip_id']}")).json()
        modes = {l["mode"] for p in snap["plans"] for l in p["legs"] if l["mode"] in ("train", "flight")}
        assert modes == {"train", "flight"}


async def test_no_hotel_and_one_way_are_respected():
    async with client() as c:
        r = (await c.post("/api/chat", json={"message": "Marol office to CP tomorrow by flight, one way, no hotel, staying with friends"})).json()
        assert r["status"] == "plan_ready"
        snap = (await c.get(f"/api/trips/{r['trip_id']}")).json()
        assert all(l["mode"] != "hotel" and l["direction"] == "outbound" for l in snap["plans"][0]["legs"])
        assert "One way" in r["reply_en"]


async def test_only_missing_destination_asks_one_question():
    async with client() as c:
        r = (await c.post("/api/chat", json={"message": "I need to travel tomorrow, keep it cheap"})).json()
        assert r["status"] == "need_info" and r["missing_slots"] == ["destination"] and r["reply_en"].count("?") == 1
        r = (await c.post("/api/chat", json={"message": "Connaught Place, by flight, one way, no hotel", "conversation_id": r["conversation_id"]})).json()
        assert r["status"] == "plan_ready"


async def test_read_back_is_clean_for_one_way_and_return():
    async with client() as c:
        r = (await c.post("/api/chat", json={"message": "Marol office to Connaught Place tomorrow, flight, one way, no hotel"})).json()
        assert ".." not in r["reply_en"] and "One way" in r["reply_en"]
        r = (await c.post("/api/chat", json={"message": SENTENCE})).json()
        assert ".." not in r["reply_en"] and "fly back on" in r["reply_en"] and "nights" in r["reply_en"]


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

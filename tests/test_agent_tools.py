import httpx

from app.main import app

AUTH = {"Authorization": "Bearer test-secret"}
SENTENCE = "I'm at Paytm's Marol office. I need to be at Connaught Place by lunch tomorrow, back on the 24th. Keep it cheap."
TOOLS = ["get_session_context", "plan_trip", "get_plan_details", "modify_plan", "send_for_approval", "get_booking_status",
         "get_trip_status", "choose_disruption_option", "request_human_help"]


def client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


def contract(r):
    for k in ("ok", "status", "say_en", "say_hi", "next_action", "missing_slots", "assumptions", "errors"):
        assert k in r, k


async def test_bad_auth_is_401():
    async with client() as c:
        for name in TOOLS:
            assert (await c.post(f"/api/agent/tools/{name}", json={})).status_code == 401
            assert (await c.post(f"/api/agent/tools/{name}", json={}, headers={"Authorization": "Bearer nope"})).status_code == 401


async def test_unknown_session_code_is_a_clean_spoken_error():
    async with client() as c:
        for name, body in [("get_session_context", {}), ("get_booking_status", {}), ("modify_plan", {"change": "fastest"}),
                           ("choose_disruption_option", {"option_id": "wait"})]:
            r = (await c.post(f"/api/agent/tools/{name}", json={"session_code": "0000", **body}, headers=AUTH)).json()
            contract(r)
            assert r["ok"] is False and r["status"] == "unknown_session" and "code" in r["say_en"]


async def test_voice_happy_path_never_books_without_screen_approval():
    async with client() as c:
        chat = (await c.post("/api/chat", json={"message": "hello, Connaught Place"})).json()
        code = chat["session_code"]
        r = (await c.post("/api/agent/tools/plan_trip", json={"session_code": code, "request_text": SENTENCE}, headers=AUTH)).json()
        contract(r)
        assert r["ok"] and r["status"] == "plan_ready" and "Total ₹" in r["say_en"] and r["missing_slots"] == []
        assert r["assumptions"] and r["rejected"]
        d = (await c.post("/api/agent/tools/get_plan_details", json={"session_code": code}, headers=AUTH)).json()
        contract(d)
        assert "flight" in d["say_en"]
        a = (await c.post("/api/agent/tools/send_for_approval", json={"session_code": code, "addons": ["cancellation cover"]},
                          headers=AUTH)).json()
        contract(a)
        assert a["status"] == "awaiting_approval" and "Paytm screen" in a["say_en"]
        b = (await c.post("/api/agent/tools/get_booking_status", json={"session_code": code}, headers=AUTH)).json()
        assert b["status"] == "awaiting_approval" and "not booked" in b["say_en"]
        snap = (await c.get(f"/api/trips/{r['trip_id']}")).json()
        assert snap["booking"] is None and snap["cart"]["status"] == "awaiting_approval"
        assert any(i["ref_id"] == "CANCEL99" for i in snap["cart"]["items"])
        await c.post(f"/api/carts/{snap['cart']['id']}/approve", headers={"Idempotency-Key": "voice-k"})
        b = (await c.post("/api/agent/tools/get_booking_status", json={"session_code": code}, headers=AUTH)).json()
        assert b["status"] == "booked" and b["say_en"].startswith("Booked")


async def test_plan_trip_without_code_creates_a_session_and_speaks_the_code():
    async with client() as c:
        r = (await c.post("/api/agent/tools/plan_trip", json={"request_text": SENTENCE}, headers=AUTH)).json()
        assert r["ok"] and r["session_code"] and "Raahi code is" in r["say_en"]
        assert (await c.get(f"/api/sessions/{r['session_code']}")).json()["trip_id"] == r["trip_id"]


async def test_sensitive_data_is_refused():
    async with client() as c:
        r = (await c.post("/api/agent/tools/plan_trip", json={"request_text": "my card is 4111 1111 1111 1111"}, headers=AUTH)).json()
        assert r["ok"] is False and r["errors"] == ["sensitive_data_refused"]


async def test_human_help_opens_a_case():
    async with client() as c:
        r = (await c.post("/api/agent/tools/request_human_help", json={"reason": "refund dispute"}, headers=AUTH)).json()
        contract(r)
        assert r["status"] == "escalated" and r["case_no"].startswith("RAAHI-")
        assert (await c.get("/api/support/cases")).json()[0]["case_no"] == r["case_no"]


async def test_addons_accepted_as_plain_text_from_sarvam():
    async with client() as c:
        r = (await c.post("/api/agent/tools/plan_trip", json={"request_text": SENTENCE}, headers=AUTH)).json()
        a = (await c.post("/api/agent/tools/send_for_approval", json={"session_code": r["session_code"], "addons": "cancellation cover and insurance",
                                                                       "plan_id": ""}, headers=AUTH)).json()
        assert a["status"] == "awaiting_approval" and a["ok"]
        snap = (await c.get(f"/api/trips/{r['trip_id']}")).json()
        assert {"CANCEL99", "INSURANCE149"} <= {i["ref_id"] for i in snap["cart"]["items"]}


async def test_secret_formatting_slips_are_tolerated():
    async with client() as c:
        for h in ("Bearer Bearer test-secret", "Bearer  test-secret ", 'Bearer "test-secret"', "bearer test-secret"):
            r = await c.post("/api/agent/tools/get_session_context", json={"session_code": "0000"}, headers={"Authorization": h})
            assert r.status_code == 200, h
        await c.post("/api/agent/tools/get_session_context", json={}, headers={"Authorization": "Bearer nope"})
        f = (await c.get("/healthz")).json()["last_tool_auth_failure"]
        assert f["token_len"] == 4 and f["expected_len"] == len("test-secret") and "nope" not in str(f)

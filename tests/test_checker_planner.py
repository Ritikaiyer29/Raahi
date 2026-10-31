from dataclasses import replace
from datetime import timedelta

from app.checker import Context, run_checks
from app.checker import rules as R
from app.checker.config import CONFIG
from app.db import SessionLocal
from app.domain import Plan, Request
from app.planner import plan_trip
from app.scouts import find_place, load_inventory
from app.timeutil import today_ist

DEP = today_ist() + timedelta(days=1)
RET = DEP + timedelta(days=2)


async def _inventory(ret=True):
    async with SessionLocal() as s:
        o, d = await find_place(s, "Paytm Marol office"), await find_place(s, "Connaught Place")
        inv = await load_inventory(s, o, d, DEP, RET if ret else None)
    req = Request("Paytm Marol office", "Connaught Place", DEP.isoformat(), RET.isoformat() if ret else None, 1, "economical", arrive_by="13:00")
    return inv, req


def _by_label(ps, label):
    return next(c for c in [*ps.valid, *ps.rejected] if c.plan.label.startswith(label))


async def test_demo_sentence_gives_valid_plans_and_the_0600_rejection():
    inv, req = await _inventory()
    ps = plan_trip(inv, req)
    assert len(ps.valid) >= 2
    assert ps.triage == "AUTO"
    assert ps.valid[0].plan.label.startswith("08:30")  # cheapest valid
    prices = [c.plan.total_price for c in ps.valid]
    assert prices == sorted(prices)
    rej = _by_label(ps, "06:00")
    assert not rej.valid
    assert rej.rejection.rule_id == "first_last_metro"
    assert "06:30" in rej.rejection.message_en


async def test_every_valid_plan_is_door_to_door_with_return_and_hotel():
    inv, req = await _inventory()
    for c in plan_trip(inv, req).valid:
        modes = [l.mode for l in c.plan.outbound()]
        assert modes[:3] == ["walk", "metro", "flight"] and "hotel" in modes
        assert any(l.mode == "flight" for l in c.plan.returning())
        assert all(r.passed or r.severity != "block" for r in c.checks)


async def test_economical_vs_fastest_priority():
    inv, req = await _inventory()
    cheap = plan_trip(inv, req).valid[0].plan.total_price
    fast = plan_trip(inv, replace(req, priority="fastest")).valid[0]
    assert fast.plan.total_price >= cheap


async def test_missing_return_leg_is_blocked():
    inv, req = await _inventory()
    c = plan_trip(inv, req).valid[0]
    c.plan.legs = [l for l in c.plan.legs if l.direction == "outbound"]
    res = {r.rule_id: r for r in run_checks(c.plan, Context(metro_hours=inv.hours))}
    assert res["return_leg_present"].blocking


async def test_terminal_mismatch_blocked():
    inv, req = await _inventory()
    c = plan_trip(inv, req).valid[0]
    next(l for l in c.plan.outbound() if l.mode == "metro").details["serves_terminal"] = "T2"
    assert R.terminal_match(c.plan, Context()).blocking


async def test_airport_buffer_and_arrive_by_and_budget():
    inv, req = await _inventory()
    c = plan_trip(inv, req).valid[0]
    flight = next(l for l in c.plan.outbound() if l.mode == "flight")
    metro = c.plan.outbound()[1]
    metro.end = flight.start - timedelta(minutes=20)
    assert R.airport_buffer(c.plan, Context()).blocking
    c.plan.request = replace(c.plan.request, arrive_by="09:00", budget=1000)
    assert R.arrive_by(c.plan, Context()).blocking
    assert R.budget(c.plan, Context()).blocking


async def test_waitlist_is_ask_not_block_and_price_drift_asks():
    inv, req = await _inventory()
    c = plan_trip(inv, req).valid[0]
    c.plan.outbound()[2].details["availability"] = "WL 12"
    r = R.availability(c.plan, Context())
    assert not r.passed and r.severity == "warn"
    leg = c.plan.outbound()[2]
    drift = R.price_drift(c.plan, Context(current_prices={leg.details["ref_id"]: int(leg.price * 1.2)}))
    assert not drift.passed and drift.severity == "warn"
    assert R.price_drift(c.plan, Context()).passed


async def test_sold_out_flight_is_blocked():
    inv, req = await _inventory()
    c = plan_trip(inv, req).valid[0]
    c.plan.outbound()[2].details["seats_left"] = 0
    assert R.availability(c.plan, Context()).blocking


async def test_thresholds_live_in_config():
    assert CONFIG.airport_buffer_min == 60

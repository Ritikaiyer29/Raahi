"""Concierge + Planner orchestration: one chat turn in, persisted state and a reply out.
The LLM may propose slots (docs/LLM.md); the backend validates everything and owns the truth."""
import asyncio
import random
import uuid
from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import models as m
from .domain import Request
from .events import add_trip_event, agent_step, log_agent
from .intent import (ParsedRequest, apply_defaults, apply_preference_defaults, assumptions, blocking_slots, next_question,
                     parse_intent, preference_question)
from .planner import Candidate, PlanSet, explanations, main_leg, plan_trip
from .scouts import find_place, load_inventory
from .timeutil import hhmm, ist, today_ist

def _now_utc():
    """Messages get a microsecond timestamp from code, so two turns in the same second still sort correctly."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


WAIT = "Checking Paytm flights and metro timings…"


async def get_or_create_conversation(s: AsyncSession, conversation_id: uuid.UUID | None = None, session_code: str | None = None) -> m.Conversation:
    conv = None
    if conversation_id:
        conv = await s.get(m.Conversation, conversation_id)
    elif session_code:
        conv = (await s.execute(select(m.Conversation).where(m.Conversation.session_code == session_code)
                                .order_by(m.Conversation.created_at.desc()))).scalars().first()
    if conv:
        return conv
    user = (await s.execute(select(m.User).where(m.User.name == "Anika"))).scalars().first()
    if not user:
        user = m.User(id=uuid.uuid4(), name="Anika", preferred_language="en")
        s.add(user)
    code = f"{random.randint(1000, 9999)}"
    while (await s.execute(select(m.Conversation.id).where(m.Conversation.session_code == code))).first():
        code = f"{random.randint(1000, 9999)}"
    conv = m.Conversation(id=uuid.uuid4(), user_id=user.id, session_code=code)
    s.add(conv)
    return conv


def _to_parsed(r: m.TripRequest) -> ParsedRequest:
    return ParsedRequest(origin=r.origin, destination=r.destination, depart_date=r.depart_date, return_date=r.return_date, party_size=r.party_size,
                         priority=r.priority, time_preference=r.time_preference, arrive_by=r.arrive_by, budget=r.budget,
                         services=list(r.requested_services or []), language=_last_lang(r),
                         mode=(r.preferences or {}).get("mode"), hotel=(r.preferences or {}).get("hotel"),
                         trip_type=(r.preferences or {}).get("trip_type"))


def _last_lang(r: m.TripRequest) -> str:
    from .intent import detect_language
    return detect_language(r.raw_text or "")


def _to_domain(p: ParsedRequest) -> Request:
    return Request(p.origin, p.destination, p.depart_date, p.return_date, p.party_size, p.priority, p.time_preference, p.arrive_by, p.budget,
                   list(p.services), mode=p.mode or "flight", hotel=p.hotel)


def slots_dict(p: ParsedRequest) -> dict:
    return dict(origin=p.origin, destination=p.destination, depart_date=p.depart_date, return_date=p.return_date, party_size=p.party_size,
                priority=p.priority, arrive_by=p.arrive_by)


def prefs_dict(p: ParsedRequest, asked: list[str] | None = None) -> dict:
    return dict(mode=p.mode, hotel=p.hotel, trip_type=p.trip_type, asked=asked or [])


def _when(dt) -> tuple[str, str]:
    """'tonight' / 'tomorrow' / 'on 03 Nov', as a person would say it."""
    d = ist(dt).date()
    days = (d - today_ist()).days
    if days == 0:
        h = ist(dt).hour
        return ("tonight", "आज रात") if h >= 19 else ("this evening", "आज शाम") if h >= 16 else ("today", "आज")
    if days == 1:
        return "tomorrow", "कल"
    return f"on {d:%d %b}", f"{d:%d %b} को"


def read_back(c: Candidate, req: Request) -> tuple[str, str]:
    """Short, speakable summary built only from checked plan data."""
    out = c.plan.outbound()
    m = main_leg(c.plan)
    i = c.plan.legs.index(m)
    metro1, metro2 = c.plan.legs[i - 1], c.plan.legs[i + 1]
    hotel = next((l for l in out if l.mode == "hotel"), None)
    dest_leg = next(l for l in out if l.details.get("is_destination"))
    when_en, when_hi = _when(m.start)
    if m.mode == "flight":
        main_en = f"the {hhmm(m.start)} {m.details['airline']} flight {when_en}"
        main_hi = f"{when_hi} {hhmm(m.start)} की {m.details['airline']} फ्लाइट"
    else:
        main_en = f"the {hhmm(m.start)} Rajdhani from {m.from_label} {when_en}, {m.details['travel_class']}, reaching {m.to_label} at {hhmm(m.end)}"
        main_hi = f"{when_hi} {hhmm(m.start)} की राजधानी ({m.details['travel_class']}), {hhmm(m.end)} पर {m.to_label}"
    en = (f"Here's what I've got: {metro1.details['line_name']} to {metro1.to_label}, {main_en}, then {metro2.details['line_name']} "
          f"to {metro2.to_label} and a short walk, so you're at {req.destination} by {hhmm(dest_leg.end)}.")
    hi = f"प्लान तैयार है: {metro1.details['line_name']} से {metro1.to_label}, {main_hi}, फिर {metro2.details['line_name']} से {metro2.to_label}।"
    en_parts, hi_parts = [], []
    if hotel:
        n = hotel.details["nights"]
        en_parts.append(f"you stay at {hotel.details['hotel']} for {n} night{'s' if n != 1 else ''}")
        hi_parts.append(f"आप {hotel.details['hotel']} में {n} रात रुकेंगे")
    ret = main_leg(c.plan, "return")
    if req.return_date and ret:
        how = "fly back" if ret.mode == "flight" else "take the train back"
        en_parts.append(f"{how} on {date.fromisoformat(req.return_date):%d %b} at {hhmm(ret.start)}")
        hi_parts.append(f"{date.fromisoformat(req.return_date):%d %b} को {hhmm(ret.start)} पर वापसी")
    if en_parts:
        en += " Then " + " and ".join(en_parts) + "."
        hi += " " + ", ".join(hi_parts) + "।"
    elif not req.return_date:
        en += " One way."
        hi += " सिर्फ़ एक तरफ़ा।"
    en += f" All in, ₹{c.plan.total_price:,}. Shall I send it to your Paytm screen to approve?"
    hi += f" कुल ₹{c.plan.total_price:,}। क्या मैं इसे आपकी Paytm स्क्रीन पर अप्रूवल के लिए भेजूँ?"
    return en, hi


async def persist_plans(s: AsyncSession, request_row: m.TripRequest, trip: m.Trip, ps: PlanSet, req: Request) -> list[m.TripPlan]:
    old = (await s.execute(select(m.TripPlan.id).where(m.TripPlan.trip_id == trip.id))).scalars().all()
    if old:
        await s.execute(delete(m.PlanLeg).where(m.PlanLeg.plan_id.in_(old)))
        await s.execute(delete(m.CheckResultRow).where(m.CheckResultRow.plan_id.in_(old)))
        await s.execute(delete(m.TripPlan).where(m.TripPlan.id.in_(old)))
    rows = []
    for rank, (c, status) in enumerate([(c, "proposed") for c in ps.valid] + [(c, "rejected") for c in ps.rejected], start=1):
        en, hi = explanations(c, req, pick=(rank == 1 and status == "proposed"))
        if status == "rejected":
            en, hi = f"Rejected: {c.plan.label}. {c.rejection.message_en}", f"अस्वीकृत: {c.plan.label}। {c.rejection.message_hi}"
        plan = m.TripPlan(id=uuid.uuid4(), request_id=request_row.id, trip_id=trip.id, rank=rank, status=status, total_price=c.plan.total_price,
                          total_duration=c.out_duration, explanation_en=en, explanation_hi=hi, is_pick=(rank == 1 and status == "proposed"))
        s.add(plan)
        for l in c.plan.legs:
            s.add(m.PlanLeg(plan_id=plan.id, seq=l.seq, direction=l.direction, mode=l.mode, from_label=l.from_label, to_label=l.to_label,
                            start_at=l.start, end_at=l.end, price=l.price, details=l.details))
        for r in c.checks:
            s.add(m.CheckResultRow(plan_id=plan.id, rule_id=r.rule_id, passed=r.passed, severity=r.severity, message_en=r.message_en,
                                   message_hi=r.message_hi, evidence=r.evidence))
        rows.append(plan)
    return rows  # written in one batch at commit


async def run_planning(s: AsyncSession, conv: m.Conversation, parsed: ParsedRequest, request_row: m.TripRequest) -> dict:
    """Scouts -> Planner -> Checker -> persist. Returns reply fields. Used by chat and by the Sarvam plan_trip tool."""
    req = _to_domain(parsed)
    async with agent_step(s, "Scouts", "search_inventory", request_id=request_row.id, trip_id=conv.trip_id, inp=f"{req.origin} → {req.destination} {req.depart_date}") as st:
        o, d = await find_place(s, req.origin), await find_place(s, req.destination)
        if not o or not d:
            st["out"] = "place not in Paytm catalogue"
            return dict(status="unknown_place", say_en="I can only plan trips between places in Paytm's catalogue for this demo. "
                        "Try Paytm's Marol office to Connaught Place.", say_hi="इस डेमो में मैं सिर्फ़ Paytm कैटलॉग के स्थानों के बीच प्लान बना सकता हूँ।")
        inv = await load_inventory(s, o, d, date.fromisoformat(req.depart_date), date.fromisoformat(req.return_date) if req.return_date else None)
        st["out"] = f"{len(inv.flights_out)} outbound flights, {len(inv.flights_ret)} return, {len(inv.hotels)} hotels"
    async with agent_step(s, "Planner", "build_door_to_door", request_id=request_row.id, trip_id=conv.trip_id, inp=f"priority={req.priority}") as st:
        ps = plan_trip(inv, req)
        st["out"] = f"{len(ps.valid)} candidate plans, triage {ps.triage}"
    async with agent_step(s, "Checker", "validate_plans", request_id=request_row.id, trip_id=conv.trip_id, inp=f"{len(ps.valid) + len(ps.rejected)} plans") as st:
        st["out"] = f"{len(ps.valid)} passed, {len(ps.rejected)} rejected" + (f" ({ps.rejected[0].rejection.rule_id})" if ps.rejected else "")

    trip = await s.get(m.Trip, conv.trip_id) if conv.trip_id else None
    if not trip:
        trip = m.Trip(id=uuid.uuid4(), user_id=conv.user_id, request_id=request_row.id, status="planned", revision=0)
        s.add(trip)
        conv.trip_id = trip.id
    trip.request_id = request_row.id
    if ps.triage == "ESCALATE":
        await add_trip_event(s, trip, "plan.none_valid", {})
        return dict(status="escalate", trip=trip, say_en="I couldn't find a valid plan for that. I'll get a human teammate to help.",
                    say_hi="मुझे इसके लिए कोई सही प्लान नहीं मिला। मैं किसी साथी से मदद दिलाता हूँ।", triage="ESCALATE")
    plans = await persist_plans(s, request_row, trip, ps, req)
    await add_trip_event(s, trip, "plans.ready", {"plan_ids": [str(p.id) for p in plans], "triage": ps.triage})
    en, hi = read_back(ps.valid[0], req)
    if ps.triage == "ASK":
        en, hi = ps.question, ps.question_hi
    return dict(status="plan_ready" if ps.triage == "AUTO" else "ask", trip=trip, plans=plans, triage=ps.triage, say_en=en, say_hi=hi,
                rejected=[dict(label=c.plan.label, rule_id=c.rejection.rule_id, message_en=c.rejection.message_en) for c in ps.rejected])


PLAN_BUDGET_S = __import__("app.config", fromlist=["get_settings"]).get_settings().plan_budget_s
OVERRIDABLE = {"origin", "destination", "depart_date", "return_date", "party_size", "priority", "arrive_by", "budget", "mode", "hotel"}


def apply_overrides(p: ParsedRequest, overrides: dict | None) -> list[str]:
    """Slots set explicitly by a chip edit or the voice agent. Validated here, never trusted blindly."""
    changed = []
    for k, v in (overrides or {}).items():
        if k not in OVERRIDABLE:
            continue
        if k in ("depart_date", "return_date") and v:
            v = date.fromisoformat(str(v)).isoformat()
        if k == "priority" and v not in ("economical", "fastest", "comfort"):
            continue
        if k == "mode" and v not in ("flight", "train", "any"):
            continue
        if k == "hotel":
            v = bool(v)
        if k == "return_date":
            p.trip_type = "round_trip" if v else "one_way"
        if k == "party_size":
            v = max(1, min(9, int(v)))
        setattr(p, k, v)
        changed.append(k)
    return changed


async def converse(s: AsyncSession, conv: m.Conversation, text: str | None, overrides: dict | None = None, channel: str = "chat") -> dict:
    """One Concierge turn: parse (or apply chip edits), fill defaults, plan within the budget, persist, reply.
    Shared by /api/chat, assumption-chip edits and the Sarvam tools."""
    request_id = conv.trip_request_id or uuid.uuid4()
    async with agent_step(s, "Concierge", "understand_request" if text else "edit_assumption", inp=text or str(overrides),
                          request_id=request_id, trip_id=conv.trip_id) as st:
        request_row = await s.get(m.TripRequest, conv.trip_request_id) if conv.trip_request_id else None
        previous = _to_parsed(request_row) if request_row else None
        pending = list((request_row.preferences or {}).get("asked", [])) if request_row else []
        parsed = parse_intent(text, previous=previous, pending=pending) if text else (previous or ParsedRequest())
        if not text and previous is None:
            parsed.language = "en"
        explicit = apply_overrides(parsed, overrides)
        prior_assumed = [a for a in (request_row.assumed_slots or [])] if request_row else []
        assumed = [a for a in prior_assumed if a not in explicit and getattr(parsed, a) == getattr(previous, a, None)]
        missing = blocking_slots(parsed)
        question = None
        if not missing:
            assumed = sorted(set(assumed + apply_defaults(parsed)))
            # A good travel agent asks what was not said (flight or train, return, hotel), at most two things at once.
            # Chip edits never ask: the traveller is already looking at a plan.
            question = preference_question(parsed, follow_up=bool(pending)) if text else None
            if not question:
                assumed = sorted(set(assumed + apply_preference_defaults(parsed))) if parsed.decide_for_me                     else sorted(set(assumed + [a for a in apply_preference_defaults(parsed) if a == "hotel"]))
        st["out"] = (f"asking about {', '.join(question[0])}" if question else
                     f"missing: {missing or 'none'}; assumed: {assumed or 'none'}")
    if not request_row:
        request_row = m.TripRequest(id=request_id, user_id=conv.user_id)
        s.add(request_row)
    for k, v in slots_dict(parsed).items():
        setattr(request_row, k, v)
    request_row.requested_services, request_row.missing_slots, request_row.assumed_slots = parsed.services, missing, assumed
    request_row.preferences = prefs_dict(parsed, question[0] if question else [])
    if text:
        request_row.raw_text = text
    conv.trip_request_id = request_row.id
    if text:
        s.add(m.Message(created_at=_now_utc(), conversation_id=conv.id, role="user", text=text, language=parsed.language, channel=channel))
    await s.commit()  # the request is saved even if planning times out

    if missing:
        en, hi = next_question(missing)
        result = dict(status="need_info", say_en=en, say_hi=hi, triage="ASK", next_action="ask_user")
    elif question:
        result = dict(status="need_info", say_en=question[1], say_hi=question[2], triage="ASK",
                      next_action="ask_user_then_call_plan_trip_with_the_answer", asking=question[0])
    else:
        conv_id, request_id = conv.id, request_row.id
        try:
            result = await asyncio.wait_for(run_planning(s, conv, parsed, request_row), PLAN_BUDGET_S)
            result["next_action"] = {"plan_ready": "read_back_then_send_for_approval", "escalate": "request_human_help"}.get(result["status"], "read_back")
        except asyncio.TimeoutError:
            return await _timed_out(s, conv_id, request_id, parsed)
    reply = result["say_hi"] if parsed.language == "hi" else result["say_en"]
    s.add(m.Message(created_at=_now_utc(), conversation_id=conv.id, role="assistant", text=reply, language=parsed.language, channel=channel))
    trip = result.get("trip")
    await s.commit()
    return dict(conversation_id=str(conv.id), session_code=conv.session_code, reply=reply, reply_en=result["say_en"], reply_hi=result["say_hi"],
                language=parsed.language, status=result["status"], triage=result.get("triage"), next_action=result.get("next_action"),
                slots=slots_dict(parsed), missing_slots=missing, asking=result.get("asking", []),
                assumptions=assumptions(parsed, assumed) if not (missing or result.get("asking")) else [],
                trip_id=str(trip.id) if trip else (str(conv.trip_id) if conv.trip_id else None), revision=trip.revision if trip else None,
                plan_ids=[str(p.id) for p in result.get("plans", [])], rejected=result.get("rejected", []))


async def _timed_out(s: AsyncSession, conv_id: uuid.UUID, request_id: uuid.UUID, parsed: ParsedRequest) -> dict:
    """Planning ran past the budget. The cancelled session may be unusable, so record the timeout on a fresh one."""
    try:
        await s.rollback()
    except Exception:
        pass
    from .db import SessionLocal
    async with SessionLocal() as s2:
        await log_agent(s2, "Planner", "build_door_to_door", request_id=request_id, out=f"no plan within {PLAN_BUDGET_S:.0f} s",
                        status="timeout", ms=int(PLAN_BUDGET_S * 1000))
        conv = await s2.get(m.Conversation, conv_id)
        en, hi = "Planning is taking longer than usual. Shall I try again?", "प्लान बनाने में सामान्य से ज़्यादा समय लग रहा है। क्या मैं फिर से कोशिश करूँ?"
        s2.add(m.Message(created_at=_now_utc(), conversation_id=conv_id, role="assistant", text=hi if parsed.language == "hi" else en, language=parsed.language))
        await s2.commit()
        return dict(conversation_id=str(conv_id), session_code=conv.session_code, reply=hi if parsed.language == "hi" else en, reply_en=en,
                    reply_hi=hi, language=parsed.language, status="timeout", triage=None, next_action="offer_retry", slots=slots_dict(parsed),
                    missing_slots=[], assumptions=[], trip_id=str(conv.trip_id) if conv.trip_id else None, revision=None, plan_ids=[], rejected=[])


async def handle_chat(s: AsyncSession, text: str, conversation_id: uuid.UUID | None = None, channel: str = "chat") -> dict:
    conv = await get_or_create_conversation(s, conversation_id)
    return await converse(s, conv, text, channel=channel)

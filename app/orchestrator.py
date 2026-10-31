"""Concierge + Planner orchestration: one chat turn in, persisted state and a reply out.
The LLM may propose slots (docs/LLM.md); the backend validates everything and owns the truth."""
import random
import uuid
from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import models as m
from .domain import Request
from .events import add_trip_event, agent_step
from .intent import ParsedRequest, missing_slots, next_question, parse_intent
from .planner import Candidate, PlanSet, explanations, plan_trip
from .scouts import find_place, load_inventory
from .timeutil import hhmm, ist

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
        user = m.User(name="Anika", preferred_language="en")
        s.add(user)
        await s.flush()
    conv = m.Conversation(user_id=user.id, session_code=f"{random.randint(1000, 9999)}")
    s.add(conv)
    await s.flush()
    return conv


def _to_parsed(r: m.TripRequest) -> ParsedRequest:
    return ParsedRequest(origin=r.origin, destination=r.destination, depart_date=r.depart_date, return_date=r.return_date, party_size=r.party_size,
                         priority=r.priority, time_preference=r.time_preference, arrive_by=r.arrive_by, budget=r.budget,
                         services=list(r.requested_services or []))


def _to_domain(p: ParsedRequest) -> Request:
    return Request(p.origin, p.destination, p.depart_date, p.return_date, p.party_size, p.priority, p.time_preference, p.arrive_by, p.budget,
                   list(p.services))


def slots_dict(p: ParsedRequest) -> dict:
    return dict(origin=p.origin, destination=p.destination, depart_date=p.depart_date, return_date=p.return_date, party_size=p.party_size,
                priority=p.priority, arrive_by=p.arrive_by)


def read_back(c: Candidate, req: Request) -> tuple[str, str]:
    """Short, speakable summary built only from checked plan data."""
    out = c.plan.outbound()
    metro1, fl, metro2 = out[1], out[2], out[3]
    hotel = next((l for l in out if l.mode == "hotel"), None)
    en = (f"I found a plan: {metro1.details['line_name']} to {metro1.to_label}, the {hhmm(fl.start)} {fl.details['airline']} flight, "
          f"{metro2.details['line_name']} to {metro2.to_label}, then a short walk to {req.destination}.")
    hi = (f"मुझे एक प्लान मिला: {metro1.details['line_name']} से {metro1.to_label}, {hhmm(fl.start)} की {fl.details['airline']} फ्लाइट, "
          f"फिर {metro2.details['line_name']} से {metro2.to_label}।")
    if hotel:
        en += f" You stay at {hotel.details['hotel']} for {hotel.details['nights']} nights"
        hi += f" आप {hotel.details['hotel']} में {hotel.details['nights']} रात रुकेंगे"
    if req.return_date:
        ret = next(l for l in c.plan.returning() if l.mode == "flight")
        en += f", and fly back on {date.fromisoformat(req.return_date):%d %b} at {hhmm(ret.start)}"
        hi += f", और {date.fromisoformat(req.return_date):%d %b} को {hhmm(ret.start)} पर वापस"
    en += f". Total ₹{c.plan.total_price:,}. Shall I send it to your Paytm screen to approve?"
    hi += f"। कुल ₹{c.plan.total_price:,}। क्या मैं इसे आपकी Paytm स्क्रीन पर अप्रूवल के लिए भेजूँ?"
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
        plan = m.TripPlan(request_id=request_row.id, trip_id=trip.id, rank=rank, status=status, total_price=c.plan.total_price,
                          total_duration=c.out_duration, explanation_en=en, explanation_hi=hi, is_pick=(rank == 1 and status == "proposed"))
        s.add(plan)
        await s.flush()
        for l in c.plan.legs:
            s.add(m.PlanLeg(plan_id=plan.id, seq=l.seq, direction=l.direction, mode=l.mode, from_label=l.from_label, to_label=l.to_label,
                            start_at=l.start, end_at=l.end, price=l.price, details=l.details))
        for r in c.checks:
            s.add(m.CheckResultRow(plan_id=plan.id, rule_id=r.rule_id, passed=r.passed, severity=r.severity, message_en=r.message_en,
                                   message_hi=r.message_hi, evidence=r.evidence))
        rows.append(plan)
    await s.flush()
    return rows


async def run_planning(s: AsyncSession, conv: m.Conversation, parsed: ParsedRequest, request_row: m.TripRequest) -> dict:
    """Scouts -> Planner -> Checker -> persist. Returns reply fields. Used by chat and by the Sarvam plan_trip tool."""
    req = _to_domain(parsed)
    async with agent_step(s, "Scouts", "search_inventory", request_id=request_row.id, inp=f"{req.origin} → {req.destination} {req.depart_date}") as st:
        o, d = await find_place(s, req.origin), await find_place(s, req.destination)
        if not o or not d:
            st["out"] = "place not in Paytm catalogue"
            return dict(status="unknown_place", say_en="I can only plan trips between places in Paytm's catalogue for this demo. "
                        "Try Paytm's Marol office to Connaught Place.", say_hi="इस डेमो में मैं सिर्फ़ Paytm कैटलॉग के स्थानों के बीच प्लान बना सकता हूँ।")
        inv = await load_inventory(s, o, d, date.fromisoformat(req.depart_date), date.fromisoformat(req.return_date) if req.return_date else None)
        st["out"] = f"{len(inv.flights_out)} outbound flights, {len(inv.flights_ret)} return, {len(inv.hotels)} hotels"
    async with agent_step(s, "Planner", "build_door_to_door", request_id=request_row.id, inp=f"priority={req.priority}") as st:
        ps = plan_trip(inv, req)
        st["out"] = f"{len(ps.valid)} candidate plans, triage {ps.triage}"
    async with agent_step(s, "Checker", "validate_plans", request_id=request_row.id, inp=f"{len(ps.valid) + len(ps.rejected)} plans") as st:
        st["out"] = f"{len(ps.valid)} passed, {len(ps.rejected)} rejected" + (f" ({ps.rejected[0].rejection.rule_id})" if ps.rejected else "")

    trip = await s.get(m.Trip, conv.trip_id) if conv.trip_id else None
    if not trip:
        trip = m.Trip(user_id=conv.user_id, request_id=request_row.id, status="planned", revision=0)
        s.add(trip)
        await s.flush()
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


async def handle_chat(s: AsyncSession, text: str, conversation_id: uuid.UUID | None = None, channel: str = "chat") -> dict:
    conv = await get_or_create_conversation(s, conversation_id)
    async with agent_step(s, "Concierge", "understand_request", inp=text) as st:
        request_row = await s.get(m.TripRequest, conv.trip_request_id) if conv.trip_request_id else None
        previous = _to_parsed(request_row) if request_row else None
        parsed = parse_intent(text, previous=previous)
        missing = missing_slots(parsed)
        st["out"] = f"slots filled, missing: {missing or 'none'}"
    if not request_row:
        request_row = m.TripRequest(user_id=conv.user_id)
        s.add(request_row)
    for k, v in slots_dict(parsed).items():
        setattr(request_row, k, v)
    request_row.requested_services, request_row.raw_text, request_row.missing_slots = parsed.services, text, missing
    await s.flush()
    conv.trip_request_id = request_row.id
    s.add(m.Message(conversation_id=conv.id, role="user", text=text, language=parsed.language, channel=channel))

    result: dict = {}
    if missing:
        en, hi = next_question(missing)
        result = dict(status="need_info", say_en=en, say_hi=hi, triage="ASK")
    else:
        result = await run_planning(s, conv, parsed, request_row)
    reply = result["say_hi"] if parsed.language == "hi" else result["say_en"]
    s.add(m.Message(conversation_id=conv.id, role="assistant", text=reply, language=parsed.language, channel=channel))
    trip = result.get("trip")
    await s.commit()
    return dict(conversation_id=str(conv.id), session_code=conv.session_code, reply=reply, reply_en=result["say_en"], reply_hi=result["say_hi"],
                language=parsed.language, status=result["status"], triage=result.get("triage"), slots=slots_dict(parsed), missing_slots=missing,
                trip_id=str(trip.id) if trip else (str(conv.trip_id) if conv.trip_id else None), revision=trip.revision if trip else None,
                plan_ids=[str(p.id) for p in result.get("plans", [])], rejected=result.get("rejected", []))

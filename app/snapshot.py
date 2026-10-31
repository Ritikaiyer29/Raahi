"""Full trip snapshot used by GET /api/trips/{id} and the first SSE message."""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import models as m
from .timeutil import ist


def _leg(l: m.PlanLeg) -> dict:
    return dict(id=str(l.id), seq=l.seq, direction=l.direction, mode=l.mode, from_label=l.from_label, to_label=l.to_label,
                start=ist(l.start_at).isoformat(), end=ist(l.end_at).isoformat(), price=l.price, details=l.details)


async def trip_snapshot(s: AsyncSession, trip_id: uuid.UUID) -> dict | None:
    trip = await s.get(m.Trip, trip_id)
    if not trip:
        return None
    req = await s.get(m.TripRequest, trip.request_id) if trip.request_id else None
    plans = (await s.execute(select(m.TripPlan).where(m.TripPlan.trip_id == trip_id).order_by(m.TripPlan.rank))).scalars().all()
    out_plans = []
    for p in plans:
        legs = (await s.execute(select(m.PlanLeg).where(m.PlanLeg.plan_id == p.id).order_by(m.PlanLeg.seq))).scalars().all()
        checks = (await s.execute(select(m.CheckResultRow).where(m.CheckResultRow.plan_id == p.id))).scalars().all()
        out_plans.append(dict(
            id=str(p.id), rank=p.rank, status=p.status, is_pick=p.is_pick, total_price=p.total_price, total_duration=p.total_duration,
            explanation_en=p.explanation_en, explanation_hi=p.explanation_hi, legs=[_leg(l) for l in legs],
            checks=[dict(rule_id=c.rule_id, passed=c.passed, severity=c.severity, message_en=c.message_en, message_hi=c.message_hi,
                         evidence=c.evidence) for c in checks]))
    cart = (await s.execute(select(m.Cart).where(m.Cart.trip_id == trip_id).order_by(m.Cart.created_at.desc()))).scalars().first()
    cart_d = None
    if cart:
        items = (await s.execute(select(m.CartItem).where(m.CartItem.cart_id == cart.id))).scalars().all()
        cart_d = dict(id=str(cart.id), status=cart.status, total=cart.total, plan_id=str(cart.plan_id),
                      items=[dict(kind=i.kind, ref_id=i.ref_id, label=i.label, price=i.price) for i in items])
    booking = (await s.execute(select(m.Booking).where(m.Booking.trip_id == trip_id))).scalars().first()
    tickets = (await s.execute(select(m.Ticket).where(m.Ticket.trip_id == trip_id).order_by(m.Ticket.valid_from))).scalars().all()
    alerts = (await s.execute(select(m.GuardianAlert).where(m.GuardianAlert.trip_id == trip_id))).scalars().all()
    return dict(
        trip=dict(id=str(trip.id), status=trip.status, revision=trip.revision, selected_plan_id=str(trip.selected_plan_id) if trip.selected_plan_id else None),
        request=dict(origin=req.origin, destination=req.destination, depart_date=req.depart_date, return_date=req.return_date,
                     party_size=req.party_size, priority=req.priority, arrive_by=req.arrive_by) if req else None,
        plans=out_plans, cart=cart_d,
        booking=dict(id=str(booking.id), status=booking.status, pnrs=booking.pnrs) if booking else None,
        tickets=[dict(id=str(t.id), type=t.type, title=t.title, ticket_no=t.ticket_no, qr_payload=t.qr_payload, status=t.status,
                      valid_from=ist(t.valid_from).isoformat() if t.valid_from else None,
                      valid_to=ist(t.valid_to).isoformat() if t.valid_to else None) for t in tickets],
        alerts=[dict(id=str(a.id), cause=a.cause, options=a.options, chosen_option=a.chosen_option, status=a.status) for a in alerts],
    )

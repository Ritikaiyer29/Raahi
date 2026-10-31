"""Checkout: one cart, one explicit approval, all legs booked atomically (mock), tickets into the wallet.
Never charges anything. Approval is idempotent: the same key returns the same result and has no second effect."""
import json
import random
import string
import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from . import models as m
from .checker.config import CONFIG
from .events import add_trip_event, agent_step, log_agent
from .scouts import current_prices

# Demo control: simulate a fare rise between search and approval (set from /demo) to show the ASK path.
DEMO_FLAGS = {"price_drift_pct": 0.0}


class CheckoutError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def _demo_id(prefix: str, n: int = 6) -> str:
    return f"DEMO-{prefix}-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=n))


async def pick_plan(s: AsyncSession, trip: m.Trip, plan_id: uuid.UUID | None) -> m.TripPlan:
    if plan_id:
        plan = await s.get(m.TripPlan, plan_id)
        if not plan or plan.trip_id != trip.id:
            raise CheckoutError("plan_not_found", "That plan is not part of this trip.")
    else:
        plan = (await s.execute(select(m.TripPlan).where(m.TripPlan.trip_id == trip.id, m.TripPlan.status != "rejected")
                                .order_by(m.TripPlan.rank))).scalars().first()
        if not plan:
            raise CheckoutError("no_plan", "There is no plan to approve yet.")
    if plan.status == "rejected":
        raise CheckoutError("plan_rejected", "That option was rejected by the Checker and cannot be booked.")
    return plan


async def _addon_rows(s: AsyncSession, codes: list[str]) -> list[m.Addon]:
    wanted = {c.upper() for c in codes or []}
    rows = (await s.execute(select(m.Addon))).scalars().all()
    keyword = {"CANCEL99": ("CANCEL", "REFUND", "99"), "INSURANCE149": ("INSUR",), "TRAVELPASS249": ("PASS", "249")}
    return [a for a in rows if a.code in wanted or any(k in w for w in wanted for k in keyword.get(a.code, ()))]


async def create_cart(s: AsyncSession, trip: m.Trip, plan_id: uuid.UUID | None = None, addons: list[str] | None = None) -> m.Cart:
    if trip.status in ("booked", "in_progress", "disrupted", "completed"):
        raise CheckoutError("already_booked", "This trip is already booked.")
    plan = await pick_plan(s, trip, plan_id)
    async with agent_step(s, "Checkout", "create_cart", trip_id=trip.id, inp=f"plan rank {plan.rank}") as st:
        await s.execute(update(m.Cart).where(m.Cart.trip_id == trip.id, m.Cart.status == "awaiting_approval").values(status="superseded"))
        await s.execute(update(m.TripPlan).where(m.TripPlan.trip_id == trip.id, m.TripPlan.status == "selected").values(status="proposed"))
        cart = m.Cart(id=uuid.uuid4(), trip_id=trip.id, plan_id=plan.id, status="awaiting_approval", total=0)
        s.add(cart)
        legs = (await s.execute(select(m.PlanLeg).where(m.PlanLeg.plan_id == plan.id).order_by(m.PlanLeg.seq))).scalars().all()
        items = [m.CartItem(cart_id=cart.id, kind="leg", ref_id=str(l.id), label=_leg_label(l), price=l.price,
                            search_price=l.details.get("search_price", l.price)) for l in legs if l.price > 0]
        items += [m.CartItem(cart_id=cart.id, kind="addon", ref_id=a.code, label=a.name, price=a.price, search_price=a.price)
                  for a in await _addon_rows(s, addons or [])]
        s.add_all(items)
        cart.total = sum(i.price for i in items)
        plan.status = "selected"
        trip.selected_plan_id = plan.id
        await add_trip_event(s, trip, "approval.requested", {"cart_id": str(cart.id), "total": cart.total})
        st["out"] = f"cart ₹{cart.total:,}, waiting for approval on screen"
    return cart


async def set_addons(s: AsyncSession, cart: m.Cart, codes: list[str]) -> m.Cart:
    if cart.status != "awaiting_approval":
        raise CheckoutError("cart_closed", "This cart can no longer be changed.")
    for item in (await s.execute(select(m.CartItem).where(m.CartItem.cart_id == cart.id, m.CartItem.kind == "addon"))).scalars():
        await s.delete(item)
    for a in await _addon_rows(s, codes):
        s.add(m.CartItem(cart_id=cart.id, kind="addon", ref_id=a.code, label=a.name, price=a.price, search_price=a.price))
    await s.flush()
    cart.total = await _cart_total(s, cart.id)
    trip = await s.get(m.Trip, cart.trip_id)
    await add_trip_event(s, trip, "cart.updated", {"cart_id": str(cart.id), "total": cart.total, "addons": codes})
    return cart


async def _cart_total(s: AsyncSession, cart_id: uuid.UUID) -> int:
    return sum(i.price for i in (await s.execute(select(m.CartItem).where(m.CartItem.cart_id == cart_id))).scalars())


def _leg_label(l: m.PlanLeg) -> str:
    d = l.details or {}
    if l.mode == "flight":
        return f"{d.get('airline')} {d.get('flight_no')} · {l.from_label} → {l.to_label}"
    if l.mode == "hotel":
        return f"{d.get('hotel')} · {d.get('nights')} night(s) · {d.get('partner')}"
    if l.mode == "metro":
        return f"{d.get('line_name')} · {l.from_label} → {l.to_label}"
    return f"{l.mode.title()} · {l.from_label} → {l.to_label}"


async def _drift_pct(s: AsyncSession, legs: list[m.PlanLeg]) -> tuple[float, str | None]:
    """Compare each priced leg's current price with its price at search (the price_drift rule, at checkout)."""
    refs = [l.details.get("ref_id") for l in legs if l.mode in ("flight", "hotel")]
    now = await current_prices(s, refs)
    worst, label = 0.0, None
    for l in legs:
        ref = l.details.get("ref_id")
        if ref not in now:
            continue
        unit = now[ref] * (1 + DEMO_FLAGS["price_drift_pct"] / 100 if l.mode == "flight" else 1)
        current = unit * l.details.get("qty", 1)
        searched = l.details.get("search_price", l.price) or 1
        pct = (current - searched) / searched * 100
        if pct > worst:
            worst, label = pct, _leg_label(l)
    return worst, label


async def approve(s: AsyncSession, cart_id: uuid.UUID, idempotency_key: str, approved_by: str = "Anika", channel: str = "app",
                  accept_new_price: bool = False) -> dict:
    """The only path that books. Requires an explicit approval from the app; voice can never call this."""
    if not idempotency_key or len(idempotency_key) > 64:
        raise CheckoutError("bad_idempotency_key", "An idempotency key is required.")
    seen = (await s.execute(select(m.IdempotencyKey).where(m.IdempotencyKey.key == idempotency_key))).scalars().first()
    if seen and seen.response:
        return seen.response
    cart = await s.get(m.Cart, cart_id)
    if not cart:
        raise CheckoutError("cart_not_found", "Cart not found.")
    if cart.status == "booked":
        booking = (await s.execute(select(m.Booking).where(m.Booking.cart_id == cart.id))).scalars().first()
        return {"status": "booked", "booking_id": str(booking.id), "pnrs": booking.pnrs, "total": cart.total}
    if cart.status != "awaiting_approval":
        raise CheckoutError("cart_closed", "This cart is no longer open. Please reselect the plan.")
    trip = await s.get(m.Trip, cart.trip_id)
    legs = (await s.execute(select(m.PlanLeg).where(m.PlanLeg.plan_id == cart.plan_id).order_by(m.PlanLeg.seq))).scalars().all()

    async with agent_step(s, "Checker", "price_drift_at_checkout", trip_id=trip.id) as st:
        drift, label = await _drift_pct(s, legs)
        st["out"] = f"max drift {drift:.1f}%"
    if drift > CONFIG.price_drift_ask_pct and not accept_new_price:
        await s.commit()
        return {"status": "ask", "reason": "price_drift", "drift_pct": round(drift, 1),
                "say_en": f"The price of {label} went up {drift:.0f}% since we searched. Approve at the new price, or pick another option?",
                "say_hi": f"{label} की कीमत सर्च के बाद {drift:.0f}% बढ़ गई है। नई कीमत पर अप्रूव करें या दूसरा विकल्प चुनें?"}

    trip_id = trip.id
    try:
        async with agent_step(s, "Checkout", "book_all_legs", trip_id=trip.id, inp=f"cart ₹{cart.total:,}") as st:
            s.add(m.Approval(cart_id=cart.id, approved_by=approved_by, channel=channel, idempotency_key=idempotency_key))
            booking = m.Booking(id=uuid.uuid4(), cart_id=cart.id, trip_id=trip.id, status="pending", pnrs={})
            s.add(booking)
            pnrs, tickets = {}, []
            for l in legs:
                t = _ticket_for(l, booking, trip)
                if t:
                    tickets.append(t)
                    if l.mode in ("flight", "hotel"):
                        pnrs[str(l.id)] = t.ticket_no
            for item in (await s.execute(select(m.CartItem).where(m.CartItem.cart_id == cart.id, m.CartItem.kind == "addon"))).scalars():
                tickets.append(m.Ticket(booking_id=booking.id, trip_id=trip.id, type="addon", title=item.label, ticket_no=_demo_id("POL"),
                                        qr_payload=json.dumps({"demo": True, "policy": item.ref_id})))
            s.add_all(tickets)
            booking.status, booking.pnrs = "confirmed", pnrs
            cart.status = "booked"
            trip.status = "booked"
            await add_trip_event(s, trip, "trip.booked", {"booking_id": str(booking.id), "tickets": len(tickets), "total": cart.total})
            st["out"] = f"{len(tickets)} tickets issued (mock), ₹{cart.total:,}"
        response = {"status": "booked", "booking_id": str(booking.id), "pnrs": pnrs, "total": cart.total, "tickets": len(tickets)}
        s.add(m.IdempotencyKey(key=idempotency_key, endpoint="approve", response=response))
        await s.commit()
        return response
    except Exception:
        await s.rollback()  # all legs or none
        await log_agent(s, "Checkout", "book_all_legs", trip_id=trip_id, out="rolled back, nothing booked", status="error")
        await s.commit()
        raise


def _ticket_for(l: m.PlanLeg, booking: m.Booking, trip: m.Trip) -> m.Ticket | None:
    d = l.details or {}
    base = dict(booking_id=booking.id, trip_id=trip.id, leg_id=l.id, valid_from=l.start_at, valid_to=l.end_at)
    if l.mode == "metro":
        no = _demo_id("MQR", 8)
        return m.Ticket(type="metro_qr", title=f"{d.get('line_name')} · {l.from_label} → {l.to_label}", ticket_no=no,
                        qr_payload=json.dumps({"demo": True, "t": no, "from": l.from_label, "to": l.to_label}), **base)
    if l.mode == "flight":
        pnr = _demo_id("PNR")
        return m.Ticket(type="flight", title=f"{d.get('airline')} {d.get('flight_no')} · {l.from_label} → {l.to_label}", ticket_no=pnr,
                        qr_payload=json.dumps({"demo": True, "pnr": pnr, "flight": d.get("flight_no")}), **base)
    if l.mode == "hotel":
        v = _demo_id("HTL")
        return m.Ticket(type="hotel", title=f"{d.get('hotel')} · {d.get('nights')} night(s)", ticket_no=v,
                        qr_payload=json.dumps({"demo": True, "voucher": v, "partner": d.get("partner")}), **base)
    return None

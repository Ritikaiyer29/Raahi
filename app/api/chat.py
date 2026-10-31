import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models as m
from ..db import get_session
from ..orchestrator import handle_chat
from ..ratelimit import limiter
from ..snapshot import trip_snapshot

router = APIRouter(prefix="/api")


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    conversation_id: uuid.UUID | None = None
    channel: str = "chat"


@router.post("/chat", dependencies=[Depends(limiter(30))])
async def chat(body: ChatIn, s: AsyncSession = Depends(get_session)):
    return await handle_chat(s, body.message, body.conversation_id, body.channel)


@router.get("/trips/{trip_id}")
async def get_trip(trip_id: uuid.UUID, s: AsyncSession = Depends(get_session)):
    snap = await trip_snapshot(s, trip_id)
    if not snap:
        raise HTTPException(404, "trip not found")
    return snap


@router.get("/agent-events")
async def agent_events(after: int = 0, limit: int = 100, s: AsyncSession = Depends(get_session)):
    """Polling feed for the Agent activity panel (SSE variant arrives with the trip stream)."""
    rows = (await s.execute(select(m.AgentEvent).where(m.AgentEvent.seq > after).order_by(m.AgentEvent.seq).limit(limit))).scalars().all()
    return [dict(seq=r.seq, agent=r.agent, action=r.action, input=r.input_summary, output=r.output_summary, status=r.status,
                 duration_ms=r.duration_ms, trip_id=str(r.trip_id) if r.trip_id else None) for r in rows]


# ---------- plan-first chips, sessions, checkout, support ----------
from ..checkout import CheckoutError, approve as approve_cart, create_cart, set_addons  # noqa: E402
from ..orchestrator import converse  # noqa: E402
from ..support import open_case  # noqa: E402
from fastapi import Header  # noqa: E402


class AssumptionEdit(BaseModel):
    overrides: dict


@router.post("/conversations/{conversation_id}/assumptions")
async def edit_assumptions(conversation_id: uuid.UUID, body: AssumptionEdit, s: AsyncSession = Depends(get_session)):
    """Tapping a chip re-plans and re-checks in place, with no chat turn."""
    conv = await s.get(m.Conversation, conversation_id)
    if not conv:
        raise HTTPException(404, "conversation not found")
    try:
        return await converse(s, conv, None, body.overrides)
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/sessions/{code}")
async def session_by_code(code: str, s: AsyncSession = Depends(get_session)):
    """Lets the app open a session that a phone call started ("Your Raahi code is 4821")."""
    conv = (await s.execute(select(m.Conversation).where(m.Conversation.session_code == code)
                            .order_by(m.Conversation.created_at.desc()))).scalars().first()
    if not conv:
        raise HTTPException(404, "unknown code")
    return dict(conversation_id=str(conv.id), session_code=conv.session_code, trip_id=str(conv.trip_id) if conv.trip_id else None)


def _checkout_error(e: CheckoutError):
    return HTTPException(409, {"code": e.code, "message": e.message})


class SelectIn(BaseModel):
    addons: list[str] = []


@router.post("/plans/{plan_id}/select")
async def select_plan(plan_id: uuid.UUID, body: SelectIn, s: AsyncSession = Depends(get_session)):
    plan = await s.get(m.TripPlan, plan_id)
    trip = await s.get(m.Trip, plan.trip_id) if plan else None
    if not trip:
        raise HTTPException(404, "plan not found")
    try:
        cart = await create_cart(s, trip, plan_id, body.addons)
    except CheckoutError as e:
        raise _checkout_error(e)
    await s.commit()
    return dict(cart_id=str(cart.id), total=cart.total, trip_id=str(trip.id), revision=trip.revision)


class AddonsIn(BaseModel):
    codes: list[str]


@router.post("/carts/{cart_id}/addons")
async def cart_addons(cart_id: uuid.UUID, body: AddonsIn, s: AsyncSession = Depends(get_session)):
    cart = await s.get(m.Cart, cart_id)
    if not cart:
        raise HTTPException(404, "cart not found")
    try:
        cart = await set_addons(s, cart, body.codes)
    except CheckoutError as e:
        raise _checkout_error(e)
    await s.commit()
    return dict(cart_id=str(cart.id), total=cart.total)


class ApproveIn(BaseModel):
    accept_new_price: bool = False


@router.post("/carts/{cart_id}/approve")
async def cart_approve(cart_id: uuid.UUID, body: ApproveIn | None = None, idempotency_key: str | None = Header(None),
                       s: AsyncSession = Depends(get_session)):
    """Simulated UPI approval. Requires an Idempotency-Key header; double taps never double-book."""
    if not idempotency_key:
        raise HTTPException(400, "Idempotency-Key header is required")
    try:
        return await approve_cart(s, cart_id, idempotency_key, accept_new_price=bool(body and body.accept_new_price))
    except CheckoutError as e:
        raise _checkout_error(e)


class CaseIn(BaseModel):
    reason: str = Field(min_length=3, max_length=300)
    trip_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None


@router.post("/support/cases")
async def support_case(body: CaseIn, s: AsyncSession = Depends(get_session)):
    case = await open_case(s, body.reason, body.trip_id, body.conversation_id)
    await s.commit()
    return dict(case_no=case.case_no, id=str(case.id), status=case.status)


@router.get("/support/cases")
async def support_cases(s: AsyncSession = Depends(get_session)):
    rows = (await s.execute(select(m.SupportCase).order_by(m.SupportCase.created_at.desc()).limit(50))).scalars()
    return [dict(id=str(c.id), case_no=c.case_no, reason=c.reason, summary=c.summary, status=c.status, assignee=c.assignee,
                 trip_id=str(c.trip_id) if c.trip_id else None, timeline=c.timeline) for c in rows]

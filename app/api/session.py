"""Sessions: the app opens one, shows its Raahi code, and follows it live. Phone calls and app chat attach to the
same session, so whatever the voice agent does appears on screen.

Realtime model: the stream sends the whole session state whenever it changes (trip revision, a new message or a new
agent event). A reconnect therefore never misses anything: the first message is always the current state. Clients
ignore a state whose `version` is older than the one they hold. Heartbeat every 15 s keeps proxies from closing it."""
import asyncio
import hashlib
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import case, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models as m
from ..db import SessionLocal, get_session
from ..intent import assumptions
from ..orchestrator import _to_parsed, get_or_create_conversation
from ..snapshot import trip_snapshot
from ..timeutil import ist

router = APIRouter(prefix="/api")
POLL_S = 1.0
HEARTBEAT_S = 15.0


@router.post("/sessions")
async def new_session(s: AsyncSession = Depends(get_session)):
    conv = await get_or_create_conversation(s)
    await s.commit()
    return dict(conversation_id=str(conv.id), session_code=conv.session_code)


async def session_state(s: AsyncSession, conv_id: uuid.UUID) -> dict | None:
    conv = await s.get(m.Conversation, conv_id)
    if not conv:
        return None
    req = await s.get(m.TripRequest, conv.trip_request_id) if conv.trip_request_id else None
    user_first = case((m.Message.role == "user", 0), else_=1)
    msgs = (await s.execute(select(m.Message).where(m.Message.conversation_id == conv.id)
                            .order_by(m.Message.created_at.desc(), user_first.desc()).limit(40))).scalars().all()
    trip = await trip_snapshot(s, conv.trip_id) if conv.trip_id else None
    scope = [m.AgentEvent.request_id == conv.trip_request_id] if conv.trip_request_id else []
    if conv.trip_id:
        scope.append(m.AgentEvent.trip_id == conv.trip_id)
    events = []
    if scope:
        rows = (await s.execute(select(m.AgentEvent).where(or_(*scope)).order_by(m.AgentEvent.seq.desc()).limit(60))).scalars().all()
        events = [dict(seq=e.seq, agent=e.agent, action=e.action, input=e.input_summary, output=e.output_summary, status=e.status,
                       duration_ms=e.duration_ms, at=ist(e.created_at).strftime("%H:%M:%S") if e.created_at else None) for e in reversed(rows)]
    chips = []
    if req and not (req.missing_slots or []):
        chips = assumptions(_to_parsed(req), list(req.assumed_slots or []))
    addons = [dict(code=a.code, name=a.name, description=a.description, price=a.price)
              for a in (await s.execute(select(m.Addon).order_by(m.Addon.price))).scalars()]
    state = dict(
        conversation_id=str(conv.id), session_code=conv.session_code,
        messages=[dict(role=x.role, text=x.text, channel=x.channel, language=x.language) for x in reversed(msgs)],
        slots=dict(origin=req.origin, destination=req.destination, depart_date=req.depart_date, return_date=req.return_date,
                   party_size=req.party_size, priority=req.priority, arrive_by=req.arrive_by) if req else None,
        missing_slots=list(req.missing_slots or []) if req else [],
        assumptions=chips, trip=trip, agent_events=events, addons=addons,
    )
    state["version"] = hashlib.sha1(json.dumps(state, sort_keys=True, default=str).encode()).hexdigest()[:12]
    return state


@router.get("/sessions/{code}/state")
async def state_by_code(code: str, s: AsyncSession = Depends(get_session)):
    conv = (await s.execute(select(m.Conversation).where(m.Conversation.session_code == code)
                            .order_by(m.Conversation.created_at.desc()))).scalars().first()
    if not conv:
        raise HTTPException(404, "unknown code")
    return await session_state(s, conv.id)


@router.get("/conversations/{conversation_id}/state")
async def state(conversation_id: uuid.UUID, s: AsyncSession = Depends(get_session)):
    """Polling fallback for clients that cannot keep an SSE stream open."""
    st = await session_state(s, conversation_id)
    if not st:
        raise HTTPException(404, "conversation not found")
    return st


@router.get("/conversations/{conversation_id}/stream")
async def stream(conversation_id: uuid.UUID, request: Request, once: bool = False):
    async with SessionLocal() as s:
        if not await s.get(m.Conversation, conversation_id):
            raise HTTPException(404, "conversation not found")

    async def gen():
        last_version, n, idle = None, 0, 0.0
        while True:
            async with SessionLocal() as s:
                st = await session_state(s, conversation_id)
            if st and st["version"] != last_version:
                n += 1
                last_version = st["version"]
                yield f"id: {n}\nevent: state\ndata: {json.dumps(st, default=str)}\n\n"
                idle = 0.0
                if once:
                    return
            elif idle >= HEARTBEAT_S:
                yield ": ping\n\n"
                idle = 0.0
            if await request.is_disconnected():
                return
            await asyncio.sleep(POLL_S)
            idle += POLL_S

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"})

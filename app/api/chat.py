import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models as m
from ..db import get_session
from ..orchestrator import handle_chat
from ..snapshot import trip_snapshot

router = APIRouter(prefix="/api")


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    conversation_id: uuid.UUID | None = None
    channel: str = "chat"


@router.post("/chat")
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

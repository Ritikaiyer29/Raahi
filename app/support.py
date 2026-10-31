"""Handoff: open a support case with the full trip timeline and a conversation excerpt. Never closes a dispute itself."""
import random
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import models as m
from .events import agent_step
from .timeutil import ist


async def open_case(s: AsyncSession, reason: str, trip_id: uuid.UUID | None = None, conversation_id: uuid.UUID | None = None) -> m.SupportCase:
    async with agent_step(s, "Handoff", "open_support_case", trip_id=trip_id, inp=reason) as st:
        timeline = []
        if trip_id:
            for e in (await s.execute(select(m.TripEvent).where(m.TripEvent.trip_id == trip_id).order_by(m.TripEvent.seq))).scalars():
                timeline.append({"at": ist(e.created_at).isoformat() if e.created_at else None, "type": e.type, "revision": e.revision})
        excerpt = []
        if conversation_id:
            msgs = (await s.execute(select(m.Message).where(m.Message.conversation_id == conversation_id)
                                    .order_by(m.Message.created_at.desc()).limit(6))).scalars().all()
            excerpt = [{"role": x.role, "text": x.text, "channel": x.channel} for x in reversed(msgs)]
        case = m.SupportCase(trip_id=trip_id, case_no=f"RAAHI-{random.randint(10000, 99999)}", reason=reason[:200],
                             summary=f"{reason[:200]}. {len(timeline)} trip events, {len(excerpt)} recent messages attached.",
                             timeline=timeline + [{"type": "conversation_excerpt", "messages": excerpt}], status="open")
        s.add(case)
        st["out"] = f"case {case.case_no} opened for a human"
    return case

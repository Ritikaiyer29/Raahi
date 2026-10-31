"""Agent events (the Agent activity timeline) and trip events (append-only; SSE reads these)."""
import time
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from . import models as m


class StaleRevision(Exception):
    pass


async def log_agent(s: AsyncSession, agent: str, action: str, *, trip_id=None, request_id=None, inp: str | None = None,
                    out: str | None = None, status: str = "ok", ms: int = 0) -> m.AgentEvent:
    ev = m.AgentEvent(agent=agent, action=action, trip_id=trip_id, request_id=request_id, input_summary=(inp or "")[:300],
                      output_summary=(out or "")[:300], status=status, duration_ms=ms)
    s.add(ev)
    await s.flush()
    return ev


@asynccontextmanager
async def agent_step(s: AsyncSession, agent: str, action: str, *, trip_id=None, request_id=None, inp: str | None = None):
    """Time a block and write one agent event. The block may set `step['out']`; an exception records status=error."""
    step: dict = {"out": None}
    t0 = time.perf_counter()
    try:
        yield step
    except Exception as e:
        await log_agent(s, agent, action, trip_id=trip_id, request_id=request_id, inp=inp, out=f"{type(e).__name__}", status="error",
                        ms=int((time.perf_counter() - t0) * 1000))
        raise
    await log_agent(s, agent, action, trip_id=trip_id, request_id=request_id, inp=inp, out=step["out"], ms=int((time.perf_counter() - t0) * 1000))


async def add_trip_event(s: AsyncSession, trip: m.Trip, type_: str, payload: dict | None = None, expected_revision: int | None = None) -> m.TripEvent:
    """Every state change bumps trips.revision and appends a trip_event in the same transaction."""
    if expected_revision is not None and trip.revision != expected_revision:
        raise StaleRevision(f"trip is at revision {trip.revision}, caller had {expected_revision}")
    trip.revision += 1
    ev = m.TripEvent(trip_id=trip.id, revision=trip.revision, type=type_, payload=payload or {})
    s.add(ev)
    await s.flush()
    return ev

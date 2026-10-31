"""Scouts: read-only searches over Paytm's (mock) catalogue. Nothing outside the inventory tables is ever returned."""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import models as m
from .timeutil import at, ist

# Inventory is small and read-mostly. A 60 s in-memory cache keeps planning fast over a slow DB link (Render Oregon to
# Supabase Paris). Re-seeding clears it.
CACHE_TTL_S = 600.0  # inventory only changes on re-seed, which clears the cache
_cache: dict = {}


def clear_cache() -> None:
    _cache.clear()


async def _cached(key, loader):
    import time
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_TTL_S:
        return hit[1]
    value = await loader()
    _cache[key] = (time.monotonic(), value)
    return value


@dataclass
class Inventory:
    origin: dict | None = None
    destination: dict | None = None
    lines: dict[str, dict] = field(default_factory=dict)
    stations: dict[str, dict] = field(default_factory=dict)
    hours: dict[str, tuple[str, str]] = field(default_factory=dict)
    flights_out: list[dict] = field(default_factory=list)
    flights_ret: list[dict] = field(default_factory=list)
    hotels: list[dict] = field(default_factory=list)
    addons: dict[str, dict] = field(default_factory=dict)


def _place(p: m.Place) -> dict:
    return dict(id=str(p.id), name=p.name, name_hi=p.name_hi, city=p.city_code, station=p.nearest_station_code, walk=p.walk_minutes)


def _flight(f: m.Flight) -> dict:
    return dict(id=str(f.id), airline=f.airline, flight_no=f.flight_no, budget=f.is_budget, from_airport=f.from_airport,
                from_terminal=f.from_terminal, to_airport=f.to_airport, to_terminal=f.to_terminal, dep=ist(f.dep_at),
                arr=ist(f.arr_at), fare=f.fare, seats=f.seats_left, baggage=f.baggage)


async def find_place(s: AsyncSession, text: str | None) -> dict | None:
    if not text:
        return None
    t = text.strip().lower()

    async def load():
        return [(_place(p), [p.name.lower(), *[x.lower() for x in (p.aliases or [])]]) for p in (await s.execute(select(m.Place))).scalars()]
    best = None
    for place, aliases in await _cached("places", load):
        for a in aliases:
            if a == t or (len(a) > 3 and a in t) or (len(t) > 3 and t in a):
                if best is None or len(a) > best[0]:
                    best = (len(a), place)
    return dict(best[1]) if best else None


async def search_flights(s: AsyncSession, frm: str, to: str, day: date) -> list[dict]:
    return [dict(f) for f in await _cached(("flights", frm, to, day), lambda: _search_flights(s, frm, to, day))]


async def _search_flights(s: AsyncSession, frm: str, to: str, day: date) -> list[dict]:
    lo, hi = at(day, "00:00"), at(day + timedelta(days=1), "00:00")
    q = select(m.Flight).where(m.Flight.from_airport == frm, m.Flight.to_airport == to, m.Flight.dep_at >= lo,
                               m.Flight.dep_at < hi).order_by(m.Flight.dep_at)
    return [_flight(f) for f in (await s.execute(q)).scalars().all()]


async def search_hotels(s: AsyncSession, city: str) -> list[dict]:
    return [dict(h) for h in await _cached(("hotels", city), lambda: _search_hotels(s, city))]


async def _search_hotels(s: AsyncSession, city: str) -> list[dict]:
    rows = (await s.execute(select(m.Hotel).where(m.Hotel.city_code == city).order_by(m.Hotel.price_per_night))).scalars().all()
    return [dict(id=str(h.id), name=h.name, area=h.area, price=h.price_per_night, rating=h.rating, walk=h.walk_min_from_cp,
                 check_in=h.check_in, check_out=h.check_out, partner=h.partner) for h in rows]


async def load_inventory(s: AsyncSession, origin: dict, destination: dict, depart: date, ret: date | None) -> Inventory:
    inv = Inventory(origin=origin, destination=destination)
    static = await _cached("static", lambda: _load_static(s))
    inv.lines, inv.stations, inv.hours, inv.addons = static
    inv.flights_out = await search_flights(s, origin["city"], destination["city"], depart)
    if ret:
        inv.flights_ret = await search_flights(s, destination["city"], origin["city"], ret)
    inv.hotels = await search_hotels(s, destination["city"])
    return inv


async def _load_static(s: AsyncSession):
    lines, stations, hours, addons = {}, {}, {}, {}
    for l in (await s.execute(select(m.MetroLine))).scalars():
        lines[l.code] = dict(code=l.code, name=l.name, headway=l.headway_min, mps=l.minutes_per_stop, base=l.fare_base,
                             per_stop=l.fare_per_stop, cap=l.fare_cap)
    for st in (await s.execute(select(m.MetroStation))).scalars():
        stations[st.code] = dict(code=st.code, name=st.name, line=st.line_code, seq=st.seq, airport=st.airport_code, terminal=st.terminal)
    for h in (await s.execute(select(m.MetroServiceHours))).scalars():
        hours[h.line_code] = (h.first_train, h.last_train)
    for a in (await s.execute(select(m.Addon))).scalars():
        addons[a.code] = dict(id=str(a.id), code=a.code, name=a.name, description=a.description, price=a.price)
    return lines, stations, hours, addons


async def current_prices(s: AsyncSession, ids: list[str]) -> dict[str, int]:
    """Live price lookup used by the price_drift rule at checkout."""
    import uuid
    out: dict[str, int] = {}
    uids = [uuid.UUID(i) for i in ids if i]
    for f in (await s.execute(select(m.Flight).where(m.Flight.id.in_(uids)))).scalars():
        out[str(f.id)] = f.fare
    for h in (await s.execute(select(m.Hotel).where(m.Hotel.id.in_(uids)))).scalars():
        out[str(h.id)] = h.price_per_night
    return out

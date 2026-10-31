from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models as m
from ..db import get_session
from ..timeutil import ist

router = APIRouter(prefix="/api/inventory")


@router.get("/flights")
async def flights(frm: str = "BOM", to: str = "DEL", limit: int = 40, s: AsyncSession = Depends(get_session)):
    q = select(m.Flight).where(m.Flight.from_airport == frm, m.Flight.to_airport == to).order_by(m.Flight.dep_at).limit(limit)
    return [dict(id=str(f.id), airline=f.airline, flight_no=f.flight_no, from_terminal=f.from_terminal, to_terminal=f.to_terminal,
                 dep=ist(f.dep_at).isoformat(), arr=ist(f.arr_at).isoformat(), fare=f.fare, seats_left=f.seats_left, baggage=f.baggage,
                 is_demo=f.is_demo) for f in (await s.execute(q)).scalars()]


@router.get("/trains")
async def trains(s: AsyncSession = Depends(get_session)):
    rows = (await s.execute(select(m.Train).order_by(m.Train.dep_at).limit(20))).scalars()
    return [dict(id=str(t.id), number=t.number, name=t.name, from_station=t.from_station, to_station=t.to_station, dep=ist(t.dep_at).isoformat(),
                 arr=ist(t.arr_at).isoformat(), classes=t.classes) for t in rows]


@router.get("/buses")
async def buses(s: AsyncSession = Depends(get_session)):
    rows = (await s.execute(select(m.Bus).order_by(m.Bus.dep_at).limit(20))).scalars()
    return [dict(id=str(b.id), operator=b.operator, from_city=b.from_city, to_city=b.to_city, dep=ist(b.dep_at).isoformat(),
                 arr=ist(b.arr_at).isoformat(), fare=b.fare, live_tracking=b.live_tracking) for b in rows]


@router.get("/hotels")
async def hotels(city: str = "DEL", s: AsyncSession = Depends(get_session)):
    rows = (await s.execute(select(m.Hotel).where(m.Hotel.city_code == city).order_by(m.Hotel.price_per_night))).scalars()
    return [dict(id=str(h.id), name=h.name, area=h.area, price_per_night=h.price_per_night, rating=h.rating, check_in=h.check_in,
                 check_out=h.check_out, partner=h.partner) for h in rows]


@router.get("/metro")
async def metro(city: str = "BOM", s: AsyncSession = Depends(get_session)):
    lines = (await s.execute(select(m.MetroLine).where(m.MetroLine.city_code == city))).scalars().all()
    if not lines:
        raise HTTPException(404, "no metro for that city")
    hours = {h.line_code: h for h in (await s.execute(select(m.MetroServiceHours))).scalars()}
    out = []
    for l in lines:
        sts = (await s.execute(select(m.MetroStation).where(m.MetroStation.line_code == l.code).order_by(m.MetroStation.seq))).scalars()
        h = hours.get(l.code)
        out.append(dict(code=l.code, name=l.name, first_train=h.first_train if h else None, last_train=h.last_train if h else None,
                        fare_base=l.fare_base, fare_per_stop=l.fare_per_stop, stations=[dict(code=x.code, name=x.name, terminal=x.terminal) for x in sts]))
    return out


@router.get("/addons")
async def addons(s: AsyncSession = Depends(get_session)):
    return [dict(code=a.code, name=a.name, description=a.description, price=a.price) for a in (await s.execute(select(m.Addon))).scalars()]

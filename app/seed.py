"""Idempotent demo seed: `python -m app.seed`. Every row is fictional demo data (is_demo = true).

Metro lines, stations, headways and service hours are DEMO ASSUMPTIONS (station order follows the
real Mumbai Aqua Line / Delhi Airport Express layout as best known; fares and hours are not official).
Flights, trains, buses, hotels and add-on prices are fictional.
"""
import asyncio
from datetime import timedelta

from sqlalchemy import delete

from . import models as m
from .db import SessionLocal, engine
from .timeutil import at, today_ist

INVENTORY = [m.City, m.Place, m.Airport, m.Station, m.BusStand, m.MetroLine, m.MetroStation, m.MetroServiceHours,
             m.Flight, m.Train, m.Bus, m.Hotel, m.Addon]

# (airline, code, is_budget, terminal at BOM)
CARRIERS = {
    "SH": ("SkyHop", True, "T1"),
    "BK": ("BlueKite", True, "T1"),
    "MA": ("Maharaja Air", False, "T2"),
    "TA": ("Tarang Airways", False, "T2"),
}
# (dep HH:MM, carrier, base fare)
BOM_DEL = [("06:00", "SH", 3900), ("08:00", "SH", 5200), ("08:30", "BK", 4200), ("09:15", "MA", 6200), ("10:40", "TA", 6900),
           ("12:10", "SH", 3700), ("14:30", "BK", 4100), ("17:45", "MA", 5600), ("19:30", "SH", 3500), ("21:05", "TA", 5900)]
DEL_BOM = [("06:30", "BK", 3800), ("08:00", "SH", 3600), ("11:15", "TA", 6300), ("15:20", "MA", 5800), ("17:30", "BK", 4400),
           ("18:40", "SH", 3900), ("19:55", "MA", 6100), ("21:10", "BK", 3700), ("22:30", "TA", 5200)]
FLIGHT_MIN = 130
DAYS = 10


def metro(code, name, city, line, seq, interchange=None, airport=None, terminal=None):
    return m.MetroStation(code=code, name=name, city_code=city, line_code=line, seq=seq, interchange=interchange or [],
                          airport_code=airport, terminal=terminal)


def build() -> list:
    rows: list = []
    rows += [m.City(code="BOM", name="Mumbai", name_hi="मुंबई"), m.City(code="DEL", name="Delhi", name_hi="दिल्ली"),
             m.City(code="PNQ", name="Pune", name_hi="पुणे"), m.City(code="JAI", name="Jaipur", name_hi="जयपुर")]
    rows += [m.Airport(code="BOM", name="Chhatrapati Shivaji Maharaj Intl (CSMIA)", city_code="BOM", terminals=["T1", "T2"]),
             m.Airport(code="DEL", name="Indira Gandhi Intl (IGI)", city_code="DEL", terminals=["T1", "T3"])]
    rows += [m.Station(code="BCT", name="Mumbai Central", city_code="BOM"), m.Station(code="NDLS", name="New Delhi", city_code="DEL")]
    rows += [m.BusStand(name="Dadar Bus Stand", city_code="BOM"), m.BusStand(name="Kashmere Gate ISBT", city_code="DEL")]

    rows += [
        m.MetroLine(code="MUM-A3", city_code="BOM", name="Aqua Line", headway_min=10, minutes_per_stop=3.0, fare_base=10, fare_per_stop=10, fare_cap=70),
        m.MetroLine(code="MUM-L1", city_code="BOM", name="Line 1 (Blue)", headway_min=5, minutes_per_stop=2.5, fare_base=10, fare_per_stop=10, fare_cap=40),
        m.MetroLine(code="DEL-AEL", city_code="DEL", name="Airport Express", headway_min=15, minutes_per_stop=5.0, fare_base=10, fare_per_stop=15, fare_cap=60),
        m.MetroLine(code="DEL-YL", city_code="DEL", name="Yellow Line", headway_min=4, minutes_per_stop=2.0, fare_base=10, fare_per_stop=5, fare_cap=60),
    ]
    # Demo assumptions: first/last train per line.
    rows += [m.MetroServiceHours(line_code="MUM-A3", first_train="06:30", last_train="23:00"),
             m.MetroServiceHours(line_code="MUM-L1", first_train="05:30", last_train="23:30"),
             m.MetroServiceHours(line_code="DEL-AEL", first_train="05:00", last_train="23:30"),
             m.MetroServiceHours(line_code="DEL-YL", first_train="05:30", last_train="23:30")]
    rows += [
        metro("MUM-MAROL", "Marol Naka", "BOM", "MUM-A3", 1, ["MUM-L1"]),
        metro("MUM-T2", "CSMIA T2", "BOM", "MUM-A3", 2, airport="BOM", terminal="T2"),
        metro("MUM-SAHAR", "Sahar Road", "BOM", "MUM-A3", 3),
        metro("MUM-T1", "CSMIA T1", "BOM", "MUM-A3", 4, airport="BOM", terminal="T1"),
        metro("MUM-SANTA", "Santacruz Metro", "BOM", "MUM-A3", 5),
        metro("MUM-BCOL", "Bandra Colony", "BOM", "MUM-A3", 6),
        metro("MUM-BKC", "BKC", "BOM", "MUM-A3", 7),
        metro("MUM-DHARAVI", "Dharavi", "BOM", "MUM-A3", 8),
        metro("MUM-DADAR", "Dadar", "BOM", "MUM-A3", 9),
        metro("MUM-WORLI", "Worli", "BOM", "MUM-A3", 10),
        metro("MUM-MAHALAXMI", "Mahalaxmi", "BOM", "MUM-A3", 11),
        # airport_code doubles as the transit hub a station serves: an airport (BOM, DEL) or a railway station (BCT, NDLS)
        metro("MUM-CENTRAL", "Mumbai Central", "BOM", "MUM-A3", 12, airport="BCT"),
        metro("MUM-L1-VER", "Versova", "BOM", "MUM-L1", 1),
        metro("MUM-L1-AND", "Andheri", "BOM", "MUM-L1", 2),
        metro("MUM-L1-MAROL", "Marol Naka", "BOM", "MUM-L1", 3, ["MUM-A3"]),
        metro("MUM-L1-GHA", "Ghatkopar", "BOM", "MUM-L1", 4),
        metro("DEL-ND", "New Delhi", "DEL", "DEL-AEL", 1, ["DEL-YL"], airport="NDLS"),
        metro("DEL-SHIV", "Shivaji Stadium", "DEL", "DEL-AEL", 2),
        metro("DEL-DHQ", "Dhaula Kuan", "DEL", "DEL-AEL", 3),
        metro("DEL-AERO", "Delhi Aerocity", "DEL", "DEL-AEL", 4),
        metro("DEL-T3", "IGI Airport T3", "DEL", "DEL-AEL", 5, airport="DEL", terminal="T3"),
        metro("DEL-YL-RC", "Rajiv Chowk", "DEL", "DEL-YL", 1),
        metro("DEL-YL-PAT", "Patel Chowk", "DEL", "DEL-YL", 2),
    ]
    rows += [
        m.Place(name="Paytm Marol office", name_hi="पेटीएम मरोल ऑफ़िस", city_code="BOM", lat=19.1176, lng=72.8836,
                nearest_station_code="MUM-MAROL", walk_minutes=8, aliases=["paytm marol office", "marol office", "paytm office", "marol", "मरोल"]),
        m.Place(name="BKC", name_hi="बीकेसी", city_code="BOM", lat=19.0690, lng=72.8697, nearest_station_code="MUM-BKC", walk_minutes=6,
                aliases=["bkc", "bandra kurla complex"]),
        m.Place(name="Connaught Place", name_hi="कनॉट प्लेस", city_code="DEL", lat=28.6315, lng=77.2167,
                nearest_station_code="DEL-SHIV", walk_minutes=14, aliases=["connaught place", "cp", "कनॉट प्लेस", "कनाट प्लेस"]),
    ]

    today = today_ist()
    for d in range(DAYS):
        day = today + timedelta(days=d)
        for route, slots, fa, ta, tterm_fn in (("BOM-DEL", BOM_DEL, "BOM", "DEL", None), ("DEL-BOM", DEL_BOM, "DEL", "BOM", None)):
            for i, (hm, cr, base) in enumerate(slots):
                name, budget, bom_term = CARRIERS[cr]
                dep = at(day, hm)
                fare = int(round(base * (1 + 0.03 * (d % 3)) / 10) * 10)
                sold_out = d == 1 and route == "BOM-DEL" and hm == "12:10"
                rows.append(m.Flight(
                    airline=name, flight_no=f"{cr} {100 + i * 7 + (0 if route == 'BOM-DEL' else 1)}", is_budget=budget,
                    from_airport=fa, from_terminal=bom_term if fa == "BOM" else "T3",
                    to_airport=ta, to_terminal=bom_term if ta == "BOM" else "T3",
                    dep_at=dep, arr_at=dep + timedelta(minutes=FLIGHT_MIN + (5 if route == "DEL-BOM" else 0)),
                    fare=fare, seats_left=0 if sold_out else 4 + (i * 3 + d) % 20,
                    baggage="7 kg cabin" if budget else "7 kg cabin + 15 kg check-in"))
        rows.append(m.Train(number="99001", name="Mumbai–Delhi Rajdhani (demo)", from_station="BCT", to_station="NDLS",
                            dep_at=at(day, "16:55"), arr_at=at(day + timedelta(days=1), "08:15"),
                            classes=[{"class": "3A", "fare": 3150, "availability": "AVL 42"},
                                     {"class": "2A", "fare": 4320, "availability": "RAC 6"},
                                     {"class": "1A", "fare": 7100, "availability": "WL 12"}]))
        rows.append(m.Train(number="99003", name="Delhi–Mumbai Rajdhani (demo)", from_station="NDLS", to_station="BCT",
                            dep_at=at(day, "16:30"), arr_at=at(day + timedelta(days=1), "08:35"),
                            classes=[{"class": "3A", "fare": 3200, "availability": "AVL 30"},
                                     {"class": "2A", "fare": 4400, "availability": "AVL 9"}]))
        rows.append(m.Bus(operator="MSRTC Shivneri (demo)", from_city="BOM", to_city="PNQ", dep_at=at(day, "07:00"),
                          arr_at=at(day, "10:30"), fare=520, live_tracking=True))
        rows.append(m.Bus(operator="RSRTC Volvo (demo)", from_city="DEL", to_city="JAI", dep_at=at(day, "06:30"),
                          arr_at=at(day, "11:30"), fare=640, live_tracking=True))

    rows += [
        m.Hotel(name="Hotel Janpath Residency", city_code="DEL", area="Connaught Place", lat=28.6279, lng=77.2189, walk_min_from_cp=6, price_per_night=2400, rating=3.6),
        m.Hotel(name="CP Budget Inn", city_code="DEL", area="Connaught Place", lat=28.6330, lng=77.2200, walk_min_from_cp=8, price_per_night=1800, rating=3.4),
        m.Hotel(name="Metro View Stay", city_code="DEL", area="Barakhamba Road", lat=28.6301, lng=77.2245, walk_min_from_cp=9, price_per_night=3100, rating=4.0),
        m.Hotel(name="The Barakhamba Suites", city_code="DEL", area="Connaught Place", lat=28.6296, lng=77.2236, walk_min_from_cp=4, price_per_night=4200, rating=4.2),
        m.Hotel(name="Kanishka Grand", city_code="DEL", area="Connaught Place", lat=28.6322, lng=77.2181, walk_min_from_cp=3, price_per_night=6800, rating=4.5),
        m.Hotel(name="Aerocity Airport Hotel", city_code="DEL", area="Aerocity", lat=28.5497, lng=77.1210, walk_min_from_cp=45, price_per_night=5200, rating=4.3),
    ]
    rows += [
        m.Addon(code="CANCEL99", name="Flight cancellation cover", price=99,
                description="₹99 add-on: full refund if you cancel your flight (demo terms)."),
        m.Addon(code="TRAVELPASS249", name="Travel Pass", price=249, description="₹249 Travel Pass: savings on travel bookings (demo terms)."),
        m.Addon(code="INSURANCE149", name="Travel insurance", price=149, description="Trip cover for delay, baggage and medical (demo terms)."),
    ]
    return rows


async def seed() -> dict:
    async with SessionLocal() as s:
        for model in INVENTORY:
            await s.execute(delete(model))
        rows = build()
        s.add_all(rows)
        await ensure_demo_user(s)
        await s.commit()
    from .scouts import clear_cache
    clear_cache()
    return {"rows": len(rows)}


async def ensure_demo_user(s) -> None:
    from sqlalchemy import select
    if not (await s.execute(select(m.User).where(m.User.name == "Anika"))).scalars().first():
        s.add(m.User(name="Anika", preferred_language="en", phone=None))


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(m.Base.metadata.create_all)


if __name__ == "__main__":
    async def _main():
        await init_db()
        print(await seed())
        await engine.dispose()
    asyncio.run(_main())

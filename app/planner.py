"""Planner: deterministic door-to-door candidate generator. Flights are chosen from inventory, timelines are built
backwards from departure and forwards from arrival, then every candidate goes through the Checker.
The LLM (if any) only writes explanations; it never chooses options."""
import math
from dataclasses import dataclass, field
from datetime import date, timedelta

from .checker import Context, is_valid, needs_ask, run_checks
from .checker.config import CONFIG
from .checker import rules as R
from .domain import CheckResult, Leg, Plan, Request
from .scouts import Inventory
from .timeutil import at, hhmm, ist, minutes

EXIT_MIN = 35  # land, deplane, collect bags, walk to the metro platform (demo assumption)
PLATFORM_BUFFER = 3
RETURN_NOT_BEFORE = "14:00"  # after hotel check-out (demo assumption)


@dataclass
class Candidate:
    plan: Plan
    checks: list[CheckResult]
    valid: bool
    asks: list[CheckResult] = field(default_factory=list)
    out_duration: int = 0

    @property
    def rejection(self) -> CheckResult | None:
        return next((c for c in self.checks if c.blocking), None)


@dataclass
class PlanSet:
    valid: list[Candidate]
    rejected: list[Candidate]
    triage: str  # AUTO / ASK / ESCALATE
    question: str | None = None
    question_hi: str | None = None


def ride(inv: Inventory, a_code: str, b_code: str) -> tuple[dict, int, int, int]:
    """(line, stops, minutes, fare) for a same-line metro ride."""
    a, b = inv.stations[a_code], inv.stations[b_code]
    line = inv.lines[a["line"]]
    stops = abs(a["seq"] - b["seq"])
    return line, stops, math.ceil(stops * line["mps"]), min(line["cap"], line["base"] + line["per_stop"] * stops)


def _airport_station(inv: Inventory, airport: str, terminal: str) -> str:
    return next(c for c, s in inv.stations.items() if s["airport"] == airport and s["terminal"] == terminal)


def _metro_leg(inv, seq, direction, a_code, b_code, start, party, **extra) -> Leg:
    line, stops, mins, fare = ride(inv, a_code, b_code)
    sa, sb = inv.stations[a_code], inv.stations[b_code]
    d = dict(line_code=line["code"], line_name=line["name"], stops=stops, ref_id=f"metro:{a_code}:{b_code}", search_price=fare * party,
             from_station=sa["name"], to_station=sb["name"], **extra)
    return Leg(seq, direction, "metro", sa["name"], sb["name"], start, start + timedelta(minutes=mins), fare * party, d)


def _flight_leg(seq, direction, f, party) -> Leg:
    return Leg(seq, direction, "flight", f"{f['from_airport']} {f['from_terminal']}", f"{f['to_airport']} {f['to_terminal']}", f["dep"],
               f["arr"], f["fare"] * party,
               dict(ref_id=f["id"], search_price=f["fare"] * party, qty=party, flight_no=f["flight_no"], airline=f["airline"], budget=f["budget"],
                    from_terminal=f["from_terminal"], to_terminal=f["to_terminal"], seats_left=f["seats"], baggage=f["baggage"]))


def build_outbound(inv: Inventory, req: Request, f: dict, hotel: dict | None, nights: int) -> list[Leg]:
    party, o, d = req.party_size, inv.origin, inv.destination
    buf = timedelta(minutes=CONFIG.planner_target_buffer_min)
    dep_station = _airport_station(inv, f["from_airport"], f["from_terminal"])
    _, _, ride_min, _ = ride(inv, o["station"], dep_station)
    metro_end = f["dep"] - buf
    metro_start = metro_end - timedelta(minutes=ride_min)
    walk_min = o["walk"]
    legs = [Leg(1, "outbound", "walk", o["name"], inv.stations[o["station"]]["name"], metro_start - timedelta(minutes=PLATFORM_BUFFER + walk_min),
                metro_start - timedelta(minutes=PLATFORM_BUFFER), 0, dict(minutes=walk_min))]
    legs.append(_metro_leg(inv, 2, "outbound", o["station"], dep_station, metro_start, party,
                           serves_terminal=f["from_terminal"], for_flight=f["flight_no"]))
    legs.append(_flight_leg(3, "outbound", f, party))
    arr_station = _airport_station(inv, f["to_airport"], f["to_terminal"])
    m2_start = f["arr"] + timedelta(minutes=EXIT_MIN)
    legs.append(_metro_leg(inv, 4, "outbound", arr_station, d["station"], m2_start, party, serves_terminal=f["to_terminal"]))
    dest_station = inv.stations[d["station"]]["name"]
    legs.append(Leg(5, "outbound", "walk", dest_station, d["name"], legs[-1].end, legs[-1].end + timedelta(minutes=d["walk"]), 0,
                    dict(minutes=d["walk"], is_destination=True)))
    if hotel:
        check_in = max(at(ist(legs[-1].end).date(), hotel["check_in"]), legs[-1].end)
        legs.append(Leg(6, "outbound", "hotel", d["name"], hotel["name"], check_in,
                        at(date.fromisoformat(req.return_date), hotel["check_out"]) if req.return_date else check_in + timedelta(days=1),
                        hotel["price"] * nights * math.ceil(party / 2),
                        dict(ref_id=hotel["id"], search_price=hotel["price"] * nights * math.ceil(party / 2), qty=nights * math.ceil(party / 2), hotel=hotel["name"], area=hotel["area"],
                             nights=nights, check_in_time=hotel["check_in"], check_out_time=hotel["check_out"], partner=hotel["partner"],
                             price_per_night=hotel["price"])))
    return legs


def build_return(inv: Inventory, req: Request, f: dict, hotel: dict | None, start_seq: int) -> list[Leg]:
    party, o, d = req.party_size, inv.origin, inv.destination
    buf = timedelta(minutes=CONFIG.planner_target_buffer_min)
    dep_station = _airport_station(inv, f["from_airport"], f["from_terminal"])
    _, _, ride_min, _ = ride(inv, d["station"], dep_station)
    metro_end = f["dep"] - buf
    metro_start = metro_end - timedelta(minutes=ride_min)
    walk = d["walk"] + (hotel["walk"] if hotel else 0)
    legs = [Leg(start_seq, "return", "walk", hotel["name"] if hotel else d["name"], inv.stations[d["station"]]["name"],
                metro_start - timedelta(minutes=PLATFORM_BUFFER + walk), metro_start - timedelta(minutes=PLATFORM_BUFFER), 0, dict(minutes=walk))]
    legs.append(_metro_leg(inv, start_seq + 1, "return", d["station"], dep_station, metro_start, party, serves_terminal=f["from_terminal"]))
    legs.append(_flight_leg(start_seq + 2, "return", f, party))
    arr_station = _airport_station(inv, f["to_airport"], f["to_terminal"])
    m_start = f["arr"] + timedelta(minutes=EXIT_MIN)
    legs.append(_metro_leg(inv, start_seq + 3, "return", arr_station, o["station"], m_start, party, serves_terminal=f["to_terminal"]))
    legs.append(Leg(start_seq + 4, "return", "walk", inv.stations[o["station"]]["name"], o["name"], legs[-1].end,
                    legs[-1].end + timedelta(minutes=o["walk"]), 0, dict(minutes=o["walk"])))
    return legs


def _return_half_ok(legs: list[Leg], req: Request, ctx: Context) -> bool:
    p = Plan(legs, req)
    return all(not r(p, ctx).blocking for r in (R.airport_buffer, R.first_last_metro, R.connection_time, R.terminal_match, R.availability))


def _pick_hotel(inv: Inventory, req: Request) -> dict | None:
    ok = [h for h in inv.hotels if h["rating"] >= CONFIG.min_hotel_rating and h["walk"] <= 20]
    if not ok:
        return None
    key = (lambda h: -h["rating"]) if req.priority == "comfort" else (lambda h: h["price"])
    return sorted(ok, key=key)[0]


def _explain(c: Candidate, req: Request, pick: bool) -> tuple[str, str]:
    fl = next(l for l in c.plan.outbound() if l.mode == "flight")
    t = f"{hhmm(fl.start)} {fl.details['airline']} {fl.details['flight_no']}"
    en = f"{t}, total ₹{c.plan.total_price:,}, reaches {req.destination} at {hhmm(next(l for l in c.plan.outbound() if l.details.get('is_destination')).end)}."
    hi = f"{t}, कुल ₹{c.plan.total_price:,}।"
    if pick:
        why = {"economical": "cheapest option that passes every check", "fastest": "shortest door-to-door time that passes every check",
               "comfort": "most comfortable option that passes every check"}[req.priority]
        en = f"Raahi's pick: {en} It is the {why}."
        hi = f"राही की पसंद: {hi} यह सभी जाँचें पास करने वाला सबसे किफ़ायती विकल्प है।"
    return en, hi


def plan_trip(inv: Inventory, req: Request, ctx: Context | None = None) -> PlanSet:
    ctx = ctx or Context(metro_hours=inv.hours)
    if not ctx.metro_hours:
        ctx.metro_hours = inv.hours
    nights = (date.fromisoformat(req.return_date) - date.fromisoformat(req.depart_date)).days if req.return_date else 0
    hotel = _pick_hotel(inv, req) if ("hotel" in req.services or nights > 0 or not req.services) else None
    returns = [f for f in inv.flights_ret if hhmm(f["dep"]) >= RETURN_NOT_BEFORE]
    cands: list[Candidate] = []
    for f in inv.flights_out:
        out = build_outbound(inv, req, f, hotel if nights else None, nights)
        best_ret: list[Leg] | None = None
        pool = sorted(returns, key=lambda r: r["fare"])
        for r in pool:
            legs = build_return(inv, req, r, hotel, len(out) + 1)
            if _return_half_ok(legs, req, ctx):
                best_ret = legs
                break
        if best_ret is None and pool:
            best_ret = build_return(inv, req, pool[0], hotel, len(out) + 1)
        plan = Plan(out + (best_ret or []), req, label=f"{hhmm(f['dep'])} {f['flight_no']}", nights=nights)
        checks = run_checks(plan, ctx)
        flight_leg = next(l for l in out if l.mode == "flight")
        end_dest = next(l for l in out if l.details.get("is_destination"))
        cands.append(Candidate(plan, checks, is_valid(checks), needs_ask(checks),
                               minutes(out[0].start, end_dest.end) if out else 0))
        cands[-1].plan.label = f"{hhmm(flight_leg.start)} {flight_leg.details['flight_no']}"

    valid = [c for c in cands if c.valid]
    rejected = [c for c in cands if not c.valid]
    if req.priority == "fastest":
        valid.sort(key=lambda c: (c.out_duration, c.plan.total_price))
    elif req.priority == "comfort":
        valid.sort(key=lambda c: (c.plan.outbound()[2].details.get("budget", True), c.plan.total_price))
    else:
        valid.sort(key=lambda c: c.plan.total_price)
    valid = valid[:3]
    # Show the most instructive rejections: the cheapest ones (the tempting-but-impossible options).
    # Timing rejections (first metro, buffers) are the instructive ones; show those before plain "too late" ones.
    timing = {"first_last_metro": 0, "airport_buffer": 0, "terminal_match": 0, "connection_time": 0}
    rejected.sort(key=lambda c: (timing.get(c.rejection.rule_id, 1), c.plan.total_price))
    rejected = rejected[:2]

    if not valid:
        return PlanSet(valid, rejected, "ESCALATE")
    # Plan first (v2): a near-tie is not a question; both options are shown and the cheaper is Raahi's pick.
    # ASK is reserved for warnings on the picked plan (waitlist, price drift), which surface at checkout.
    top = valid[0]
    if top.asks:
        return PlanSet(valid, rejected, "ASK", top.asks[0].message_en, top.asks[0].message_hi)
    return PlanSet(valid, rejected, "AUTO")


def explanations(c: Candidate, req: Request, pick: bool) -> tuple[str, str]:
    return _explain(c, req, pick)

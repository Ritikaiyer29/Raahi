"""Planner: deterministic door-to-door candidate generator. Flights and trains are chosen from inventory, timelines are
built backwards from departure and forwards from arrival, then every candidate goes through the Checker.
The LLM (if any) only writes explanations; it never chooses options."""
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from .checker import Context, is_valid, needs_ask, run_checks
from .checker.config import CONFIG
from .checker import rules as R
from .domain import CheckResult, Leg, Plan, Request
from .scouts import Inventory
from .timeutil import at, hhmm, ist, minutes, now_ist

EXIT_MIN = 35  # land, deplane, collect bags, walk to the metro platform (demo assumption)
PLATFORM_BUFFER = 3
RETURN_NOT_BEFORE = "14:00"  # after hotel check-out (demo assumption)
TRAIN_BUFFER_MIN = 30  # be on the platform this long before a long-distance train (demo assumption)
TRAIN_EXIT_MIN = 15  # step off, walk to the metro


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


def _hub_station(inv: Inventory, hub: str, term: str | None) -> str | None:
    """Metro station serving an airport terminal (BOM T1) or a railway station (BCT). airport_code holds the hub code."""
    return next((c for c, s in inv.stations.items() if s["airport"] == hub and s["terminal"] == term), None)


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


def _train_class(t: dict, priority: str) -> dict:
    """Economical: cheapest class with a confirmed seat. Comfort: the best confirmed class. Waitlist only if nothing else."""
    confirmed = [c for c in t["classes"] if not str(c["availability"]).startswith("WL")]
    pool = confirmed or t["classes"]
    return max(pool, key=lambda c: c["fare"]) if priority == "comfort" else min(pool, key=lambda c: c["fare"])


RAIL_NAMES = {"BCT": "Mumbai Central", "NDLS": "New Delhi"}


def _train_leg(seq, direction, t, cls, party) -> Leg:
    return Leg(seq, direction, "train", RAIL_NAMES.get(t["from_station"], t["from_station"]), RAIL_NAMES.get(t["to_station"], t["to_station"]), t["dep"], t["arr"], cls["fare"] * party,
               dict(ref_id=f"train:{t['id']}:{cls['class']}", search_price=cls["fare"] * party, qty=party, train_no=t["number"],
                    train_name=t["name"], travel_class=cls["class"], availability=cls["availability"], budget=cls["class"] == "3A"))


# A trunk is the long-distance leg (flight or train) plus how long to arrive before it and to leave after it.
def _flight_trunk(f: dict) -> dict:
    return dict(kind="flight", ref=f, dep=f["dep"], arr=f["arr"], fare=f["fare"], from_hub=f["from_airport"], from_term=f["from_terminal"],
                to_hub=f["to_airport"], to_term=f["to_terminal"], buffer=CONFIG.planner_target_buffer_min, exit=EXIT_MIN,
                label=f"{hhmm(f['dep'])} {f['flight_no']}")


def _train_trunk(t: dict, priority: str) -> dict:
    cls = _train_class(t, priority)
    return dict(kind="train", ref=t, cls=cls, dep=t["dep"], arr=t["arr"], fare=cls["fare"], from_hub=t["from_station"], from_term=None,
                to_hub=t["to_station"], to_term=None, buffer=TRAIN_BUFFER_MIN, exit=TRAIN_EXIT_MIN,
                label=f"{hhmm(t['dep'])} {t['number']} {cls['class']}")


def _trunk_leg(seq, direction, tr: dict, party: int) -> Leg:
    return _flight_leg(seq, direction, tr["ref"], party) if tr["kind"] == "flight" else _train_leg(seq, direction, tr["ref"], tr["cls"], party)


def build_outbound(inv: Inventory, req: Request, tr: dict, hotel: dict | None, nights: int) -> list[Leg] | None:
    party, o, d = req.party_size, inv.origin, inv.destination
    dep_station, arr_station = _hub_station(inv, tr["from_hub"], tr["from_term"]), _hub_station(inv, tr["to_hub"], tr["to_term"])
    if not dep_station or not arr_station:
        return None  # this hub is not reachable by metro in the demo data
    _, _, ride_min, _ = ride(inv, o["station"], dep_station)
    metro_end = tr["dep"] - timedelta(minutes=tr["buffer"])
    metro_start = metro_end - timedelta(minutes=ride_min)
    walk_min = o["walk"]
    legs = [Leg(1, "outbound", "walk", o["name"], inv.stations[o["station"]]["name"], metro_start - timedelta(minutes=PLATFORM_BUFFER + walk_min),
                metro_start - timedelta(minutes=PLATFORM_BUFFER), 0, dict(minutes=walk_min))]
    legs.append(_metro_leg(inv, 2, "outbound", o["station"], dep_station, metro_start, party, serves_terminal=tr["from_term"],
                           for_trunk=tr["label"]))
    legs.append(_trunk_leg(3, "outbound", tr, party))
    m2_start = tr["arr"] + timedelta(minutes=tr["exit"])
    legs.append(_metro_leg(inv, 4, "outbound", arr_station, d["station"], m2_start, party, serves_terminal=tr["to_term"]))
    dest_station = inv.stations[d["station"]]["name"]
    legs.append(Leg(5, "outbound", "walk", dest_station, d["name"], legs[-1].end, legs[-1].end + timedelta(minutes=d["walk"]), 0,
                    dict(minutes=d["walk"], is_destination=True)))
    if hotel:
        stay = nights or 1
        rooms = math.ceil(party / 2)
        check_in = max(at(ist(legs[-1].end).date(), hotel["check_in"]), legs[-1].end)
        check_out = (at(date.fromisoformat(req.return_date), hotel["check_out"]) if req.return_date
                     else at(ist(check_in).date() + timedelta(days=1), hotel["check_out"]))
        legs.append(Leg(6, "outbound", "hotel", d["name"], hotel["name"], check_in, check_out, hotel["price"] * stay * rooms,
                        dict(ref_id=hotel["id"], search_price=hotel["price"] * stay * rooms, qty=stay * rooms, hotel=hotel["name"],
                             area=hotel["area"], nights=stay, check_in_time=hotel["check_in"], check_out_time=hotel["check_out"],
                             partner=hotel["partner"], price_per_night=hotel["price"])))
    return legs


def build_return(inv: Inventory, req: Request, tr: dict, hotel: dict | None, start_seq: int) -> list[Leg] | None:
    party, o, d = req.party_size, inv.origin, inv.destination
    dep_station, arr_station = _hub_station(inv, tr["from_hub"], tr["from_term"]), _hub_station(inv, tr["to_hub"], tr["to_term"])
    if not dep_station or not arr_station:
        return None
    _, _, ride_min, _ = ride(inv, d["station"], dep_station)
    metro_end = tr["dep"] - timedelta(minutes=tr["buffer"])
    metro_start = metro_end - timedelta(minutes=ride_min)
    walk = d["walk"] + (hotel["walk"] if hotel else 0)
    legs = [Leg(start_seq, "return", "walk", hotel["name"] if hotel else d["name"], inv.stations[d["station"]]["name"],
                metro_start - timedelta(minutes=PLATFORM_BUFFER + walk), metro_start - timedelta(minutes=PLATFORM_BUFFER), 0, dict(minutes=walk))]
    legs.append(_metro_leg(inv, start_seq + 1, "return", d["station"], dep_station, metro_start, party, serves_terminal=tr["from_term"]))
    legs.append(_trunk_leg(start_seq + 2, "return", tr, party))
    m_start = tr["arr"] + timedelta(minutes=tr["exit"])
    legs.append(_metro_leg(inv, start_seq + 3, "return", arr_station, o["station"], m_start, party, serves_terminal=tr["to_term"]))
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


def main_leg(plan: Plan, direction: str = "outbound") -> Leg | None:
    return next((l for l in plan.legs if l.direction == direction and l.mode in ("flight", "train")), None)


def leg_name(l: Leg) -> str:
    d = l.details
    return f"{d['airline']} {d['flight_no']}" if l.mode == "flight" else f"{d['train_name']} {d['train_no']} ({d['travel_class']})"


def _explain(c: Candidate, req: Request, pick: bool) -> tuple[str, str]:
    m = main_leg(c.plan)
    t = f"{hhmm(m.start)} {leg_name(m)}"
    dest = next(l for l in c.plan.outbound() if l.details.get("is_destination"))
    en = f"{t}, total ₹{c.plan.total_price:,}, reaches {req.destination} at {hhmm(dest.end)}."
    hi = f"{t}, कुल ₹{c.plan.total_price:,}।"
    if pick:
        why = {"economical": "cheapest option that passes every check", "fastest": "shortest door-to-door time that passes every check",
               "comfort": "most comfortable option that passes every check"}[req.priority]
        en = f"Raahi's pick: {en} It is the {why}."
        hi = f"राही की पसंद: {hi} यह सभी जाँचें पास करने वाला सबसे किफ़ायती विकल्प है।"
    return en, hi


def plan_trip(inv: Inventory, req: Request, ctx: Context | None = None, now: datetime | None = None) -> PlanSet:
    ctx = ctx or Context(metro_hours=inv.hours)
    if not ctx.metro_hours:
        ctx.metro_hours = inv.hours
    cutoff = (now or now_ist()) + timedelta(minutes=30)  # never offer something that has already left
    nights = (date.fromisoformat(req.return_date) - date.fromisoformat(req.depart_date)).days if req.return_date else 0
    want_hotel = req.hotel if req.hotel is not None else nights > 0
    hotel = _pick_hotel(inv, req) if want_hotel else None
    modes = {"flight": ["flight"], "train": ["train"]}.get(req.mode, ["flight", "train"])
    outs = ([_flight_trunk(f) for f in inv.flights_out] if "flight" in modes else []) + \
           ([_train_trunk(t, req.priority) for t in inv.trains_out] if "train" in modes else [])
    rets = ([_flight_trunk(f) for f in inv.flights_ret if hhmm(f["dep"]) >= RETURN_NOT_BEFORE] if "flight" in modes else []) + \
           ([_train_trunk(t, req.priority) for t in inv.trains_ret] if "train" in modes else [])
    outs = [o for o in outs if o["dep"] >= cutoff]
    cands: list[Candidate] = []
    for tr in outs:
        out = build_outbound(inv, req, tr, hotel, nights)
        if out is None:
            continue
        best_ret: list[Leg] | None = None
        pool = sorted(rets, key=lambda r: (r["kind"] != tr["kind"], r["fare"]))  # same mode back, cheapest first
        for r in pool:
            legs = build_return(inv, req, r, hotel, len(out) + 1)
            if legs and _return_half_ok(legs, req, ctx):
                best_ret = legs
                break
        if best_ret is None and pool and req.return_date:
            best_ret = build_return(inv, req, pool[0], hotel, len(out) + 1)
        plan = Plan(out + (best_ret or []), req, label=tr["label"], nights=nights)
        checks = run_checks(plan, ctx)
        end_dest = next(l for l in out if l.details.get("is_destination"))
        cands.append(Candidate(plan, checks, is_valid(checks), needs_ask(checks), minutes(out[0].start, end_dest.end)))

    valid = [c for c in cands if c.valid]
    rejected = [c for c in cands if not c.valid]
    if req.priority == "fastest":
        valid.sort(key=lambda c: (c.out_duration, c.plan.total_price))
    elif req.priority == "comfort":
        valid.sort(key=lambda c: (main_leg(c.plan).details.get("budget", True), c.plan.total_price))
    else:
        valid.sort(key=lambda c: c.plan.total_price)
    valid = valid[:3]
    # Timing rejections (first metro, buffers) are the instructive ones; show those before plain "too late" ones.
    timing = {"first_last_metro": 0, "airport_buffer": 0, "terminal_match": 0, "connection_time": 0}
    rejected.sort(key=lambda c: (timing.get(c.rejection.rule_id, 1), c.plan.total_price))
    rejected = rejected[:2]

    if not valid:
        return PlanSet(valid, rejected, "ESCALATE")
    # A near-tie is not a question; both options are shown and the cheaper is Raahi's pick.
    # ASK is reserved for warnings on the picked plan (waitlist, price drift), which surface at checkout.
    top = valid[0]
    if top.asks:
        return PlanSet(valid, rejected, "ASK", top.asks[0].message_en, top.asks[0].message_hi)
    return PlanSet(valid, rejected, "AUTO")


def explanations(c: Candidate, req: Request, pick: bool) -> tuple[str, str]:
    return _explain(c, req, pick)

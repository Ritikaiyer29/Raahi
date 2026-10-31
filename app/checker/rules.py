"""Deterministic Checker. Pure functions, no LLM, no I/O. Each rule returns a CheckResult."""
from datetime import date
from typing import Callable

from ..domain import CheckResult, Plan
from ..timeutil import at, hhmm, ist, minutes
from .config import CONFIG, CheckerConfig


class Context:
    """Facts the rules need that are not part of the plan: metro service hours and current prices."""

    def __init__(self, metro_hours: dict[str, tuple[str, str]] | None = None, current_prices: dict[str, int] | None = None,
                 cfg: CheckerConfig = CONFIG):
        self.metro_hours = metro_hours or {}
        self.current_prices = current_prices or {}
        self.cfg = cfg


def _r(rule_id, passed, severity, en, hi, **evidence) -> CheckResult:
    return CheckResult(rule_id, passed, severity, en, hi, evidence)


def airport_buffer(plan: Plan, ctx: Context) -> CheckResult:
    for i, leg in enumerate(plan.legs):
        if leg.mode != "flight" or i == 0:
            continue
        gap = minutes(plan.legs[i - 1].end, leg.start)
        if gap < ctx.cfg.airport_buffer_min:
            fn = leg.details.get("flight_no")
            return _r("airport_buffer", False, "block",
                      f"Only {gap} min at the airport before flight {fn}; need {ctx.cfg.airport_buffer_min}.",
                      f"फ्लाइट {fn} से पहले एयरपोर्ट पर सिर्फ़ {gap} मिनट हैं; {ctx.cfg.airport_buffer_min} चाहिए।",
                      gap=gap, needed=ctx.cfg.airport_buffer_min, flight=fn)
    return _r("airport_buffer", True, "info", f"At least {ctx.cfg.airport_buffer_min} min at the airport before each flight.",
              f"हर फ्लाइट से पहले एयरपोर्ट पर कम से कम {ctx.cfg.airport_buffer_min} मिनट।")


def first_last_metro(plan: Plan, ctx: Context) -> CheckResult:
    for leg in plan.legs:
        if leg.mode != "metro":
            continue
        line = leg.details.get("line_code")
        hours = ctx.metro_hours.get(line)
        if not hours:
            continue
        name = leg.details.get("line_name", line)
        d = ist(leg.start).date()
        first, last = at(d, hours[0]), at(d, hours[1])
        if ist(leg.start) < first:
            return _r("first_last_metro", False, "block",
                      f"The first {name} train is at {hours[0]}; this ride starts at {hhmm(leg.start)}.",
                      f"{name} की पहली ट्रेन {hours[0]} बजे है; यह सफ़र {hhmm(leg.start)} पर शुरू होता है।",
                      line=line, first_train=hours[0], starts=hhmm(leg.start), flight=leg.details.get("for_flight"))
        if ist(leg.end) > last:
            return _r("first_last_metro", False, "block",
                      f"The last {name} train is at {hours[1]}; this ride ends at {hhmm(leg.end)}.",
                      f"{name} की आख़िरी ट्रेन {hours[1]} बजे है; यह सफ़र {hhmm(leg.end)} पर ख़त्म होता है।",
                      line=line, last_train=hours[1], ends=hhmm(leg.end))
    return _r("first_last_metro", True, "info", "All metro rides fall within service hours.", "सभी मेट्रो सफ़र सेवा समय के भीतर हैं।")


def connection_time(plan: Plan, ctx: Context) -> CheckResult:
    for legs in (plan.outbound(), plan.returning()):
        for a, b in zip(legs, legs[1:]):
            gap = minutes(a.end, b.start)
            need = 0 if b.mode == "flight" else ctx.cfg.min_transfer_min.get(b.mode, 0)  # flights use airport_buffer
            if gap < 0 or gap < need:
                return _r("connection_time", False, "block",
                          f"{a.mode.title()} ends at {hhmm(a.end)} but {b.mode} starts at {hhmm(b.start)}.",
                          f"{a.mode} {hhmm(a.end)} पर ख़त्म होता है पर {b.mode} {hhmm(b.start)} पर शुरू।", gap=gap, needed=need)
    return _r("connection_time", True, "info", "Every connection has enough time.", "हर कनेक्शन में पर्याप्त समय है।")


def terminal_match(plan: Plan, ctx: Context) -> CheckResult:
    for i, leg in enumerate(plan.legs):
        if leg.mode != "flight":
            continue
        prev = plan.legs[i - 1] if i else None
        nxt = plan.legs[i + 1] if i + 1 < len(plan.legs) else None
        if prev and prev.mode == "metro" and prev.direction == leg.direction \
                and prev.details.get("serves_terminal") != leg.details.get("from_terminal"):
            return _r("terminal_match", False, "block",
                      f"Flight leaves from {leg.details.get('from_terminal')} but the metro goes to {prev.details.get('serves_terminal')}.",
                      f"फ्लाइट {leg.details.get('from_terminal')} से जाती है पर मेट्रो {prev.details.get('serves_terminal')} जाती है।")
        if nxt and nxt.mode == "metro" and nxt.direction == leg.direction \
                and nxt.details.get("serves_terminal") != leg.details.get("to_terminal"):
            return _r("terminal_match", False, "block",
                      f"Flight lands at {leg.details.get('to_terminal')} but the metro starts at {nxt.details.get('serves_terminal')}.",
                      f"फ्लाइट {leg.details.get('to_terminal')} पर उतरती है पर मेट्रो {nxt.details.get('serves_terminal')} से चलती है।")
    return _r("terminal_match", True, "info", "Metro and flight terminals match.", "मेट्रो और फ्लाइट के टर्मिनल मेल खाते हैं।")


def arrive_by(plan: Plan, ctx: Context) -> CheckResult:
    deadline = plan.request.arrive_by or ctx.cfg.default_arrive_by_lunch
    out = [l for l in plan.outbound() if l.mode != "hotel"]
    if not out:
        return _r("arrive_by", False, "block", "No outbound journey.", "कोई जाने का सफ़र नहीं।")
    dest = next((l for l in out if l.details.get("is_destination")), out[-1])
    ok = ist(dest.end) <= at(ist(dest.end).date(), deadline)
    arr = hhmm(dest.end)
    return _r("arrive_by", ok, "block",
              f"Reach {dest.to_label} at {arr}, before {deadline}." if ok else f"Arrives {arr}, after the {deadline} deadline.",
              f"{arr} तक पहुँचेंगे, {deadline} से पहले।" if ok else f"{arr} पर पहुँचेंगे, {deadline} के बाद।",
              arrival=arr, deadline=deadline)


def budget(plan: Plan, ctx: Context) -> CheckResult:
    b = plan.request.budget
    if b is None:
        return _r("budget", True, "info", "No budget set.", "कोई बजट तय नहीं।")
    return _r("budget", plan.total_price <= b, "block", f"Total ₹{plan.total_price:,} vs budget ₹{b:,}.",
              f"कुल ₹{plan.total_price:,} बनाम बजट ₹{b:,}।", total=plan.total_price, budget=b)


def return_leg_present(plan: Plan, ctx: Context) -> CheckResult:
    if not plan.request.return_date:
        return _r("return_leg_present", True, "info", "One-way trip.", "सिर्फ़ जाने का सफ़र।")
    ok = any(l.mode in ("flight", "train", "bus") for l in plan.returning())
    return _r("return_leg_present", ok, "block",
              "Return journey included." if ok else "A return date was given but the plan has no return.",
              "वापसी का सफ़र शामिल है।" if ok else "वापसी की तारीख़ दी गई थी पर प्लान में वापसी नहीं है।")


def hotel_window(plan: Plan, ctx: Context) -> CheckResult:
    hotels = [l for l in plan.legs if l.mode == "hotel"]
    if not hotels:
        return _r("hotel_window", True, "info", "No hotel in this plan.", "इस प्लान में होटल नहीं है।")
    h, req = hotels[0], plan.request
    before = [l for l in plan.outbound() if l.mode != "hotel"]
    arrival = ist(before[-1].end).date()
    check_in = ist(h.start).date()
    nights = h.details.get("nights", 0)
    expected = (date.fromisoformat(req.return_date) - date.fromisoformat(req.depart_date)).days if req.return_date and req.depart_date else 0
    ok = check_in == arrival and (expected == 0 or nights == expected)
    return _r("hotel_window", ok, "block",
              f"{nights} night(s) from {check_in:%d %b}, check-in {h.details.get('check_in_time')}." if ok
              else f"Hotel dates don't match: check-in {check_in}, {nights} night(s), expected {expected}.",
              f"{nights} रात, {check_in:%d %b} से।" if ok else f"होटल की तारीख़ें मेल नहीं खातीं: {nights} रात, अपेक्षित {expected}।",
              nights=nights, expected=expected)


def availability(plan: Plan, ctx: Context) -> CheckResult:
    for l in plan.legs:
        if l.details.get("seats_left") == 0 or l.details.get("availability") == "SOLD_OUT":
            return _r("availability", False, "block", f"{l.from_label} → {l.to_label} is sold out.",
                      f"{l.from_label} → {l.to_label} सोल्ड आउट है।")
    for l in plan.legs:
        if str(l.details.get("availability", "")).startswith("WL"):
            return _r("availability", False, "warn", f"Train is waitlisted ({l.details['availability']}). Ask the traveller.",
                      f"ट्रेन वेटलिस्ट में है ({l.details['availability']})।")
    return _r("availability", True, "info", "All legs have seats.", "सभी सफ़रों में सीटें उपलब्ध हैं।")


def price_drift(plan: Plan, ctx: Context) -> CheckResult:
    worst = 0.0
    for l in plan.legs:
        now = ctx.current_prices.get(l.details.get("ref_id"))
        searched = l.details.get("search_price", l.price)
        if now is not None and searched:
            worst = max(worst, (now - searched) / searched * 100)
    if worst > ctx.cfg.price_drift_ask_pct:
        return _r("price_drift", False, "warn", f"A price rose {worst:.0f}% since search. Ask before booking.",
                  f"सर्च के बाद कीमत {worst:.0f}% बढ़ी है।", drift_pct=round(worst, 1))
    return _r("price_drift", True, "info", "Prices unchanged since search.", "सर्च के बाद कीमतें नहीं बदलीं।")


RULES: list[Callable[[Plan, Context], CheckResult]] = [
    airport_buffer, first_last_metro, connection_time, terminal_match, arrive_by,
    budget, return_leg_present, hotel_window, availability, price_drift,
]


def run_checks(plan: Plan, ctx: Context | None = None) -> list[CheckResult]:
    ctx = ctx or Context()
    return [rule(plan, ctx) for rule in RULES]


def is_valid(results: list[CheckResult]) -> bool:
    return not any(r.blocking for r in results)


def needs_ask(results: list[CheckResult]) -> list[CheckResult]:
    return [r for r in results if (not r.passed) and r.severity == "warn"]

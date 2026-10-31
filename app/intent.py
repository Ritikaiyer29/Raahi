"""Intent parsing. Rules-based fallback that handles English, Hindi and Hinglish; an LLM may propose slots first
(see docs/LLM.md) but the backend always validates and owns the result."""
import re
from datetime import date, timedelta

from pydantic import BaseModel, Field

from .checker.config import CONFIG
from .timeutil import today_ist

ORIGIN_ALIASES = ["paytm marol office", "paytm's marol office", "marol office", "paytm office", "marol", "मरोल", "bkc"]
DEST_ALIASES = {"connaught place": "Connaught Place", "कनॉट प्लेस": "Connaught Place", "कनाट प्लेस": "Connaught Place",
                "connaught": "Connaught Place", "cp": "Connaught Place"}
ORIGIN_CANON = {"bkc": "BKC", "marol": "Paytm Marol office", "मरोल": "Paytm Marol office", "paytm": "Paytm Marol office"}

REQUIRED = ["origin", "destination", "depart_date"]
DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


class ParsedRequest(BaseModel):
    """Schema the LLM must return (validated by Pydantic) and the fallback fills."""
    origin: str | None = None
    destination: str | None = None
    depart_date: str | None = None
    return_date: str | None = None
    party_size: int = Field(1, ge=1, le=9)
    priority: str = "economical"
    time_preference: str | None = None
    arrive_by: str | None = None
    budget: int | None = Field(None, ge=0)
    services: list[str] = []
    language: str = "en"
    # Travel-agent preferences, asked naturally when not stated (see preference_question)
    mode: str | None = None  # flight / train / any
    hotel: bool | None = None
    trip_type: str | None = None  # one_way / round_trip
    decide_for_me: bool = False


def detect_language(text: str) -> str:
    if re.search(r"[ऀ-ॿ]", text):
        return "hi"
    if re.search(r"\b(kal|parso|jaana|jana|chahiye|wapas|vapas|mujhe|hai|sasta|kahan|kahaan|tak|ko|se)\b", text.lower()):
        return "hinglish"
    return "en"


def _ordinal_day(t: str) -> int | None:
    m = re.search(r"(?:back|return(?:ing|s)?|wapas|vapas|वापस)[^.\d]{0,25}?(?:on|by)?\s*(?:the\s*)?(\d{1,2})(?:st|nd|rd|th)?", t)
    if not m:
        m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s*(?:ko|को|तारीख|तारीख़)?\s*(?:ko\s*|को\s*)?(?:wapas|vapas|वापस)", t)
    if not m:
        m = re.search(r"(?:वापस|wapas|vapas)\D{0,12}(\d{1,2})", t)
    return int(m.group(1)) if m else None


MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
          "जनवरी": 1, "फरवरी": 2, "मार्च": 3, "अप्रैल": 4, "मई": 5, "जून": 6, "जुलाई": 7, "अगस्त": 8, "सितंबर": 9, "अक्टूबर": 10,
          "नवंबर": 11, "नवम्बर": 11, "दिसंबर": 12}
_MONTH_RE = "|".join(sorted((re.escape(k) for k in MONTHS), key=len, reverse=True))


def _next_occurrence(day: int, month: int, today: date) -> date | None:
    """'5th November' -> the next 5 Nov on or after today in IST. The year is never asked."""
    for year in (today.year, today.year + 1):
        try:
            d = date(year, month, day)
        except ValueError:
            return None
        if d >= today:
            return d
    return None


def _dates_with_month(t: str, today: date) -> list[date]:
    found: list[tuple[int, date]] = []
    for m in re.finditer(rf"(\d{{1,2}})(?:st|nd|rd|th)?\s*(?:of\s+)?({_MONTH_RE})[a-z]*", t):
        d = _next_occurrence(int(m.group(1)), MONTHS[m.group(2)], today)
        if d:
            found.append((m.start(), d))
    for m in re.finditer(rf"({_MONTH_RE})[a-z]*\s+(\d{{1,2}})(?:st|nd|rd|th)?\b", t):
        d = _next_occurrence(int(m.group(2)), MONTHS[m.group(1)], today)
        if d and all(abs(pos - m.start()) > 3 for pos, _ in found):
            found.append((m.start(), d))
    return [d for _, d in sorted(found)]


def parse_intent(text: str, today: date | None = None, previous: ParsedRequest | None = None,
                 pending: list[str] | None = None) -> ParsedRequest:
    today = today or today_ist()
    t = text.translate(DEVANAGARI_DIGITS).lower().replace("’", "'")
    out = previous.model_copy(deep=True) if previous else ParsedRequest()
    out.language = detect_language(text)

    # origin / destination
    for alias in ORIGIN_ALIASES:
        if alias in t:
            out.origin = ORIGIN_CANON.get(alias, "Paytm Marol office")
            break
    for alias, canon in DEST_ALIASES.items():
        if re.search(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", t):
            out.destination = canon
            break
    if out.destination == out.origin:
        out.destination = None

    # depart date
    dated = _dates_with_month(t, today)
    if dated:
        out.depart_date = dated[0].isoformat()
    elif re.search(r"\b(day after tomorrow|parso)\b|परसों", t):
        out.depart_date = (today + timedelta(days=2)).isoformat()
    elif re.search(r"\b(tomorrow|kal)\b|कल", t):
        out.depart_date = (today + timedelta(days=1)).isoformat()
    elif re.search(r"\b(today|aaj)\b|आज", t):
        out.depart_date = today.isoformat()

    # return date: "back on the 24th" - if that date is not after departure, use depart + offset (demo-configurable)
    if len(dated) > 1 and dated[1] > dated[0]:
        out.return_date = dated[1].isoformat()
    elif re.search(r"\b(back|return|returns|returning|wapas|vapas|round[- ]trip)\b|वापस", t) and out.depart_date:
        day = _ordinal_day(t)
        dep = date.fromisoformat(out.depart_date)
        ret = None
        if day:
            try:
                ret = date(dep.year, dep.month, day)
            except ValueError:
                ret = None
            if ret is None or ret <= dep or ret > dep + timedelta(days=9):
                ret = dep + timedelta(days=CONFIG.return_offset_days_if_date_passed)
        out.return_date = ret.isoformat() if ret else out.return_date

    # arrive-by
    if re.search(r"\blunch\b|लंच|दोपहर के खाने", t):
        out.arrive_by = CONFIG.default_arrive_by_lunch
    m = re.search(r"by\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", t)
    if m:
        h, mi = int(m.group(1)), int(m.group(2) or 0)
        if m.group(3) == "pm" and h < 12:
            h += 12
        out.arrive_by = f"{h:02d}:{mi:02d}"

    # priority
    if re.search(r"\b(cheap|cheapest|economical|sasta|sastha|budget)\b|सस्ता|किफ़ायती|किफायती", t):
        out.priority = "economical"
    elif re.search(r"\b(fast|fastest|quick|jaldi)\b|जल्दी|सबसे तेज़", t):
        out.priority = "fastest"
    elif re.search(r"\b(comfort|comfortable|aaram)\b|आराम", t):
        out.priority = "comfort"

    m = re.search(r"(\d+)\s*(?:people|persons|travell?ers|log|लोग)", t)
    if m:
        out.party_size = max(1, min(9, int(m.group(1))))
    m = re.search(r"(?:under|budget(?: of)?|within)\s*(?:rs\.?|₹)?\s*(\d[\d,]*)", t)
    if m:
        out.budget = int(m.group(1).replace(",", ""))
    if re.search(r"\binsurance\b|बीमा", t) and "insurance" not in out.services:
        out.services.append("insurance")
    _parse_preferences(t, out, pending or [])
    return out


WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
YES = r"\b(yes|yeah|yep|sure|please|ok|okay|haan|han|ha|ji|bilkul|zaroor)\b|हाँ|हां|जी"
NO = r"\b(no|nope|nah|nahi|nahin|na)\b|नहीं"


def _parse_preferences(t: str, out: ParsedRequest, pending: list[str]) -> None:
    """Mode, hotel and trip type from free text, plus a bare yes/no when exactly that question was asked."""
    if re.search(r"\b(you decide|you choose|your call|up to you|just plan|plan it|anything works|whatever works|surprise me|"
                 r"don'?t ask|no more questions|koi bhi chalega|kuch bhi chalega|aap dekh lo|tum dekh lo)\b|आप देख लो|कुछ भी चलेगा", t):
        out.decide_for_me = True

    flight = re.search(r"\b(flight|flights|fly|flying|plane|aeroplane|airplane|by air)\b|फ्लाइट|हवाई", t)
    train = re.search(r"\b(train|trains|rajdhani|rail|railway|by rail)\b|ट्रेन|रेल|राजधानी", t)
    either = re.search(r"\b(either|any|whichever|no preference|doesn'?t matter|koi bhi)\b|कोई भी", t)
    if flight and not train:
        out.mode = "flight"
    elif train and not flight:
        out.mode = "train"
    elif (flight and train) or (either and "mode" in pending):
        out.mode = "any"

    no_hotel = re.search(r"\b(no|don'?t|do not|without|nahi|nahin|skip)\b[^.,]{0,25}\b(hotel|stay|room|accommodation)\b|"
                         r"\bstaying (with|at) (a |my )?(friend|friends|family|relatives?|cousins?|home|place)|\bday trip\b|"
                         r"\b(have|got) (a )?(place|stay) (to stay|sorted)|होटल नहीं|होटल की ज़रूरत नहीं", t)
    if no_hotel:
        out.hotel = False
    elif re.search(r"\b(hotel|stay|room|accommodation)\b|होटल", t):
        out.hotel = True
    elif "hotel" in pending and out.hotel is None:
        if re.search(NO, t):
            out.hotel = False
        elif re.search(YES, t):
            out.hotel = True

    if re.search(r"\bone[- ]way\b|\bnot (coming|going) back\b|\bno return\b|\bek taraf|एक तरफ़ा|एक तरफा", t):
        out.trip_type, out.return_date = "one_way", None
    elif out.return_date or re.search(r"\bround[- ]trip\b|\b(return|returning|coming back|back)\b|wapas|vapas|वापस", t):
        out.trip_type = "round_trip"
    elif "trip_type" in pending and re.search(NO, t):
        out.trip_type = "one_way"

    # "for 3 days", "2 nights", "back on Tuesday": return dates a traveller actually says
    if out.depart_date and not out.return_date and out.trip_type != "one_way":
        dep = date.fromisoformat(out.depart_date)
        m = re.search(r"\b(?:for\s+)?(\d{1,2})\s+(day|days|night|nights)\b", t)
        w = re.search(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", t)
        if m:
            n = int(m.group(1))
            out.return_date, out.trip_type = (dep + timedelta(days=n)).isoformat(), "round_trip"
        elif w and ("return_date" in pending or out.trip_type == "round_trip"):
            ahead = (WEEKDAYS[w.group(1)] - dep.weekday()) % 7 or 7
            out.return_date, out.trip_type = (dep + timedelta(days=ahead)).isoformat(), "round_trip"


def _pick(options: list[str], seed: str) -> str:
    """Varied but stable wording: the same request gets the same sentence, different requests sound different."""
    return options[sum(map(ord, seed)) % len(options)]


def preference_question(p: ParsedRequest, follow_up: bool = False) -> tuple[list[str], str, str] | None:
    """What a good travel agent would still ask: at most two things, in one natural sentence.
    Returns (slots asked, English, Hindi), or None when there is enough to plan."""
    if p.decide_for_me:
        return None
    asks: list[str] = []
    if p.mode is None:
        asks.append("mode")
    if p.trip_type is None and not p.return_date:
        asks.append("trip_type")
    elif p.trip_type == "round_trip" and not p.return_date:
        asks.append("return_date")
    if p.hotel is None and len(asks) < 2 and "trip_type" not in asks:
        asks.append("hotel")
    asks = asks[:2]
    if not asks:
        return None

    dest = p.destination or "there"
    nights = 0
    if p.return_date and p.depart_date:
        nights = (date.fromisoformat(p.return_date) - date.fromisoformat(p.depart_date)).days
    when = ""
    if p.depart_date:
        days = (date.fromisoformat(p.depart_date) - today_ist()).days
        when = {0: "today", 1: "tomorrow"}.get(days, f"on {date.fromisoformat(p.depart_date):%a %d %b}")
    by = " by lunch" if p.arrive_by == CONFIG.default_arrive_by_lunch else (f" by {p.arrive_by}" if p.arrive_by else "")
    seed = f"{p.origin}{dest}{p.depart_date}{''.join(asks)}"
    ack = _pick([f"{dest}{by} {when}, got it.", f"Okay, {dest}{by} {when}.", f"Sure, {dest}{by} {when}."], seed).replace("  ", " ")
    if follow_up:
        # Acknowledge the answer just given, like a person would, instead of repeating the request.
        bits = []
        if p.mode:
            bits.append({"train": "Train it is", "flight": "Flying it is", "any": "I'll compare flights and trains"}[p.mode])
        if p.return_date:
            bits.append(f"back on {date.fromisoformat(p.return_date):%a %d %b}")
        elif p.trip_type == "one_way":
            bits.append("one way")
        ack = (", ".join(bits) + ".") if bits else _pick(["Got it.", "Perfect.", "Okay."], seed)

    en_q = {
        "mode": ["Would you like to fly, or is the overnight Rajdhani okay?", "Flight or train for this one?",
                 "Shall I look at flights, or would you prefer the train?"],
        "trip_type": ["Are you coming back, or is it one way?", "Is this one way, or should I plan the return too?"],
        "return_date": ["When are you coming back?", "Which day should I plan the return for?"],
        "hotel": [f"Shall I book you a stay near {dest}" + (f" for the {nights} night{'s' if nights != 1 else ''}?" if nights else "?"),
                  f"Do you need a hotel near {dest}, or is the stay sorted?"],
    }
    hi_q = {
        "mode": ["फ्लाइट से जाना है, या रात की राजधानी ट्रेन चलेगी?", "फ्लाइट या ट्रेन?"],
        "trip_type": ["वापस भी आना है, या सिर्फ़ एक तरफ़ा?"],
        "return_date": ["वापस कब आना है?"],
        "hotel": [f"{dest} के पास होटल भी बुक कर दूँ?"],
    }
    first = _pick(en_q[asks[0]], seed)
    en = f"{ack} {first}"
    if len(asks) > 1:
        second = _pick(en_q[asks[1]], seed + "2")
        en += " And " + second[0].lower() + second[1:]
    hi = f"{dest}, समझ गया। " + " ".join(_pick(hi_q[a], seed) for a in asks)
    return asks, en, hi


def apply_preference_defaults(p: ParsedRequest) -> list[str]:
    """When the traveller says 'you decide': compare flights and trains, stay over if there are nights, one way if no return."""
    assumed = []
    if p.mode is None:
        p.mode = "any"
        assumed.append("mode")
    if p.trip_type is None:
        p.trip_type = "round_trip" if p.return_date else "one_way"
        assumed.append("trip_type")
    if p.hotel is None:
        p.hotel = bool(p.return_date)
        assumed.append("hotel")
    return assumed


def missing_slots(p: ParsedRequest) -> list[str]:
    return [k for k in REQUIRED if not getattr(p, k)]


# Plan first (v2): only a missing destination blocks planning. Everything else gets a default shown as a chip.
BLOCKING = ["destination"]
DEFAULT_BASE = "Paytm Marol office"  # demo user's saved base; a real build reads it from the user's profile


def blocking_slots(p: ParsedRequest) -> list[str]:
    return [k for k in BLOCKING if not getattr(p, k)]


def apply_defaults(p: ParsedRequest, today: date | None = None) -> list[str]:
    """Fill origin and date with defaults. Returns the slots that were assumed rather than stated."""
    today = today or today_ist()
    assumed = []
    if not p.origin:
        p.origin = DEFAULT_BASE
        assumed.append("origin")
    if not p.depart_date:
        p.depart_date = (today + timedelta(days=1)).isoformat()
        assumed.append("depart_date")
    return assumed


PRIORITY_LABELS = {"economical": ("Cheapest", "सबसे सस्ता"), "fastest": ("Fastest", "सबसे तेज़"), "comfort": ("Most comfortable", "सबसे आरामदायक")}


def assumptions(p: ParsedRequest, assumed: list[str]) -> list[dict]:
    """Editable chips. Stated values are chips too, so every default and choice can be changed in one tap."""
    def chip(slot, value, en, hi, was_assumed=True):
        return dict(slot=slot, value=value, label_en=en, label_hi=hi, editable=True, assumed=was_assumed)

    out = []
    if p.origin:
        out.append(chip("origin", p.origin, f"From {p.origin}", f"{p.origin} से", "origin" in assumed))
    if p.depart_date:
        d = date.fromisoformat(p.depart_date)
        out.append(chip("depart_date", p.depart_date, f"{d:%a %d %b}", f"{d:%d/%m}", "depart_date" in assumed))
    out.append(chip("party_size", p.party_size, f"{p.party_size} traveller" + ("s" if p.party_size > 1 else ""), f"{p.party_size} यात्री",
                    p.party_size == 1))
    en, hi = PRIORITY_LABELS.get(p.priority, PRIORITY_LABELS["economical"])
    out.append(chip("priority", p.priority, en, hi))
    mode_labels = {"flight": ("Flight", "फ्लाइट"), "train": ("Train", "ट्रेन"), "any": ("Flight or train", "फ्लाइट या ट्रेन")}
    m_en, m_hi = mode_labels.get(p.mode or "any", mode_labels["any"])
    out.append(chip("mode", p.mode or "any", m_en, m_hi, "mode" in assumed))
    if p.hotel is not None:
        out.append(chip("hotel", p.hotel, "Hotel stay" if p.hotel else "No hotel", "होटल" if p.hotel else "होटल नहीं", "hotel" in assumed))
    out.append(chip("cabin", "economy", "Economy", "इकॉनमी"))
    if p.return_date:
        r = date.fromisoformat(p.return_date)
        out.append(chip("return_date", p.return_date, f"Return {r:%a %d %b}", f"वापसी {r:%d/%m}", False))
    else:
        out.append(chip("return_date", None, "One-way", "एक तरफ़ा"))
    if p.arrive_by:
        out.append(chip("arrive_by", p.arrive_by, f"Arrive by {p.arrive_by}", f"{p.arrive_by} तक पहुँचें", False))
    else:
        out.append(chip("arrive_by", None, "Arrive any time", "कभी भी पहुँचें", True))
    out.append(chip("baggage", "cabin_only", "Cabin bag only", "सिर्फ़ केबिन बैग"))
    return out


QUESTIONS = {
    "origin": ("Where are you starting from?", "आप कहाँ से शुरू कर रहे हैं?"),
    "destination": ("Where do you need to get to?", "आपको कहाँ पहुँचना है?"),
    "depart_date": ("Which day do you want to travel?", "आप किस दिन यात्रा करना चाहते हैं?"),
}


def next_question(missing: list[str]) -> tuple[str, str] | None:
    """Exactly one question at a time."""
    return QUESTIONS[missing[0]] if missing else None

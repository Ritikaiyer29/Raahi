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


def detect_language(text: str) -> str:
    if re.search(r"[ऀ-ॿ]", text):
        return "hi"
    if re.search(r"\b(kal|parso|jaana|jana|chahiye|wapas|vapas|mujhe|hai|sasta|kahan|kahaan|tak|ko|se)\b", text.lower()):
        return "hinglish"
    return "en"


def _ordinal_day(t: str) -> int | None:
    m = re.search(r"(?:back|return|wapas|vapas|वापस)[^.\d]{0,25}?(?:on|by)?\s*(?:the\s*)?(\d{1,2})(?:st|nd|rd|th)?", t)
    if not m:
        m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s*(?:ko|को|तारीख|तारीख़)?\s*(?:ko\s*|को\s*)?(?:wapas|vapas|वापस)", t)
    if not m:
        m = re.search(r"(?:वापस|wapas|vapas)\D{0,12}(\d{1,2})", t)
    return int(m.group(1)) if m else None


def parse_intent(text: str, today: date | None = None, previous: ParsedRequest | None = None) -> ParsedRequest:
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
    if re.search(r"\b(day after tomorrow|parso)\b|परसों", t):
        out.depart_date = (today + timedelta(days=2)).isoformat()
    elif re.search(r"\b(tomorrow|kal)\b|कल", t):
        out.depart_date = (today + timedelta(days=1)).isoformat()
    elif re.search(r"\b(today|aaj)\b|आज", t):
        out.depart_date = today.isoformat()

    # return date: "back on the 24th" - if that date is not after departure, use depart + offset (demo-configurable)
    if re.search(r"\b(back|return|wapas|vapas)\b|वापस", t) and out.depart_date:
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
    return out


def missing_slots(p: ParsedRequest) -> list[str]:
    return [k for k in REQUIRED if not getattr(p, k)]


QUESTIONS = {
    "origin": ("Where are you starting from?", "आप कहाँ से शुरू कर रहे हैं?"),
    "destination": ("Where do you need to get to?", "आपको कहाँ पहुँचना है?"),
    "depart_date": ("Which day do you want to travel?", "आप किस दिन यात्रा करना चाहते हैं?"),
}


def next_question(missing: list[str]) -> tuple[str, str] | None:
    """Exactly one question at a time."""
    return QUESTIONS[missing[0]] if missing else None

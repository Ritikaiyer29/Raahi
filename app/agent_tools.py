"""Sarvam voice agent tools: POST /api/agent/tools/<name>.

- Auth: `Authorization: Bearer <AGENT_TOOL_SECRET>` (stored as a credential in the Sarvam console).
- Identity: a 4-digit session code shown on the app screen. With no code, a new session is created and its code is
  spoken, so the caller can open it on screen. The model never passes a trip or user id it chose.
- Every response is short and speakable: ok, status, say_en, say_hi, missing_slots, assumptions, next_action, errors.
  HTTP 200 even for business errors, so the agent reads our say_en instead of a generic failure line.
- No tool accepts or stores payment secrets or ID numbers. send_for_approval never charges."""
import hmac
import re
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import models as m
from .checkout import CheckoutError, create_cart
from .config import get_settings
from .db import get_session
from .events import log_agent
from .orchestrator import converse, get_or_create_conversation
from .ratelimit import limiter
from .support import open_case
from .timeutil import hhmm


# Last auth failure, as lengths and flags only (never the value), shown on /healthz to debug the Sarvam credential.
LAST_AUTH_FAILURE: dict = {}


def _clean_token(value: str) -> tuple[str, int]:
    """Strip whitespace, quotes and any number of 'Bearer ' prefixes (a secret saved as 'Bearer xyz' is sent twice)."""
    v, prefixes = value.strip().strip('"').strip("'").strip(), 0
    while v.lower().startswith("bearer "):
        v, prefixes = v[7:].strip(), prefixes + 1
    return v.strip('"').strip("'").strip(), prefixes


def require_tool_secret(authorization: str | None = Header(None)):
    secret, _ = _clean_token(get_settings().agent_tool_secret or "")
    if not secret:
        raise HTTPException(503, "Tool secret not configured on the server.")
    token, prefixes = _clean_token(authorization or "")
    if not hmac.compare_digest(token.encode(), secret.encode()):
        LAST_AUTH_FAILURE.update(at=__import__("time").strftime("%H:%M:%S"), header_present=bool(authorization),
                                 bearer_prefixes=prefixes, token_len=len(token), expected_len=len(secret),
                                 same_first_char=bool(token) and token[:1] == secret[:1])
        raise HTTPException(401, "Invalid or missing bearer token.")


router = APIRouter(prefix="/api/agent/tools", dependencies=[Depends(require_tool_secret), Depends(limiter(60))])

# Refuse anything that looks like a payment secret or an ID number before it reaches the database.
_SENSITIVE = re.compile(r"\b(\d{4}\s?\d{4}\s?\d{4}(\s?\d{4})?|[A-Z]{5}\d{4}[A-Z])\b|\b(otp|upi pin|cvv|aadhaar|aadhar|passport no)\b", re.I)


class SessionIn(BaseModel):
    session_code: str | None = Field(None, description="4-digit code shown on the Raahi screen")

    @field_validator("session_code", mode="before")
    @classmethod
    def digits_only(cls, v):
        if v is None:
            return None
        v = re.sub(r"\D", "", str(v))
        return v or None


class PlanTripIn(SessionIn):
    request_text: str = Field("", max_length=600, description="What the caller asked for, in their words")
    origin: str | None = None
    destination: str | None = None
    depart_date: str | None = Field(None, description="YYYY-MM-DD if known")
    return_date: str | None = None
    party_size: int | None = None
    priority: str | None = None
    arrive_by: str | None = None


class PlanIn(SessionIn):
    plan_id: uuid.UUID | None = None


class ModifyIn(SessionIn):
    change: str = Field(..., max_length=300, description="The change in the caller's words, e.g. 'fastest', 'add insurance'")


class ApprovalIn(SessionIn):
    plan_id: uuid.UUID | None = None
    addons: list[str] = []

    @field_validator("addons", mode="before")
    @classmethod
    def addons_from_text(cls, v):
        """Sarvam sends tool fields as text ("cancellation cover, insurance"); accept that as well as a list."""
        if v is None or v == "":
            return []
        if isinstance(v, str):
            return [x.strip() for x in re.split(r"[,;]| and ", v) if x.strip()]
        return v

    @field_validator("plan_id", mode="before")
    @classmethod
    def blank_plan_id(cls, v):
        return None if v in ("", None) else v


class ChoiceIn(SessionIn):
    alert_id: uuid.UUID | None = None
    option_id: str

    @field_validator("alert_id", mode="before")
    @classmethod
    def blank_alert_id(cls, v):
        return None if v in ("", None) else v


class HelpIn(SessionIn):
    reason: str = Field("Caller asked for a person", max_length=300)


def reply(ok: bool, status: str, say_en: str, say_hi: str, next_action: str, **kw) -> dict:
    return dict(ok=ok, status=status, say_en=say_en, say_hi=say_hi, next_action=next_action, missing_slots=kw.pop("missing_slots", []),
                assumptions=kw.pop("assumptions", []), errors=kw.pop("errors", []), **kw)


UNKNOWN_CODE = reply(False, "unknown_session", "I could not find that Raahi code. Please read the four digit code on the Raahi screen.",
                     "मुझे वह राही कोड नहीं मिला। कृपया राही स्क्रीन पर दिखा चार अंकों का कोड बताइए।", "ask_for_session_code",
                     errors=["unknown_session_code"])


async def _conv(s: AsyncSession, code: str | None, create: bool = False) -> m.Conversation | None:
    if code:
        return (await s.execute(select(m.Conversation).where(m.Conversation.session_code == code)
                                .order_by(m.Conversation.created_at.desc()))).scalars().first()
    return await get_or_create_conversation(s) if create else None


async def _log(s, name, conv, out, status="ok"):
    await log_agent(s, "Concierge", f"voice_tool:{name}", trip_id=conv.trip_id if conv else None, out=out, status=status)
    await s.commit()


def _spell(code: str) -> str:
    return " ".join(code.replace("DEMO-", "").replace("-", " "))


@router.post("/get_session_context")
async def get_session_context(body: SessionIn, s: AsyncSession = Depends(get_session)):
    conv = await _conv(s, body.session_code)
    if not conv:
        return UNKNOWN_CODE
    user = await s.get(m.User, conv.user_id)
    trip = await s.get(m.Trip, conv.trip_id) if conv.trip_id else None
    await _log(s, "get_session_context", conv, f"session {conv.session_code}")
    return reply(True, "ok", f"Connected to {user.name}'s Raahi session." + (f" The trip is {trip.status}." if trip else ""),
                 f"{user.name} का राही सेशन जुड़ गया।", "ask_where_to_go" if not trip else "continue",
                 user_name=user.name, language=user.preferred_language, trip_id=str(trip.id) if trip else None,
                 session_code=conv.session_code)


@router.post("/plan_trip")
async def plan_trip(body: PlanTripIn, s: AsyncSession = Depends(get_session)):
    if _SENSITIVE.search(body.request_text or ""):
        return reply(False, "refused", "For your safety I never take card, OTP, PIN or ID numbers on a call. Just tell me where you want to go.",
                     "आपकी सुरक्षा के लिए मैं कॉल पर कार्ड, OTP, PIN या ID नंबर नहीं लेता। बस बताइए कहाँ जाना है।", "ask_where_to_go",
                     errors=["sensitive_data_refused"])
    conv = await _conv(s, body.session_code, create=body.session_code is None)
    if not conv:
        return UNKNOWN_CODE
    overrides = {k: v for k, v in body.model_dump(exclude={"session_code", "request_text"}).items() if v not in (None, "")}
    for k in ("depart_date", "return_date"):
        if k in overrides:
            try:
                date.fromisoformat(overrides[k])
            except ValueError:
                overrides.pop(k)  # let the parser read the date from the words instead
    try:
        r = await converse(s, conv, body.request_text or None, overrides, channel="voice")
    except Exception as e:
        await s.rollback()
        await _log(s, "plan_trip", conv, type(e).__name__, "error")
        return reply(False, "error", "Something went wrong while planning. I can try again, or connect you to a person.",
                     "प्लान बनाते समय कुछ गड़बड़ हुई। मैं फिर से कोशिश कर सकता हूँ या किसी व्यक्ति से जोड़ सकता हूँ।", "offer_retry_or_human",
                     errors=[type(e).__name__])
    say_en, say_hi = r["reply_en"], r["reply_hi"]
    if body.session_code is None and r["status"] in ("plan_ready", "ask"):
        say_en += f" Your Raahi code is {_spell(conv.session_code)}. Enter it on the Raahi screen to see the plan."
        say_hi += f" आपका राही कोड {_spell(conv.session_code)} है।"
    await _log(s, "plan_trip", conv, f"{r['status']}, {len(r['plan_ids'])} plans")
    return reply(r["status"] in ("plan_ready", "ask", "need_info"), r["status"], say_en, say_hi, r.get("next_action") or "read_back",
                 missing_slots=r["missing_slots"], assumptions=r["assumptions"], trip_id=r["trip_id"], revision=r["revision"],
                 session_code=conv.session_code, plan_id=r["plan_ids"][0] if r["plan_ids"] else None,
                 rejected=[x["message_en"] for x in r["rejected"]][:1])


@router.post("/get_plan_details")
async def get_plan_details(body: PlanIn, s: AsyncSession = Depends(get_session)):
    conv = await _conv(s, body.session_code)
    if not conv:
        return UNKNOWN_CODE
    if not conv.trip_id:
        return reply(False, "no_plan", "There is no plan yet. Where would you like to go?", "अभी कोई प्लान नहीं है। आप कहाँ जाना चाहेंगे?",
                     "ask_where_to_go", errors=["no_plan"])
    q = select(m.TripPlan).where(m.TripPlan.trip_id == conv.trip_id, m.TripPlan.status != "rejected").order_by(m.TripPlan.rank)
    plan = await s.get(m.TripPlan, body.plan_id) if body.plan_id else (await s.execute(q)).scalars().first()
    if not plan or plan.trip_id != conv.trip_id:
        return reply(False, "no_plan", "I could not find that plan.", "मुझे वह प्लान नहीं मिला।", "read_back", errors=["plan_not_found"])
    legs = (await s.execute(select(m.PlanLeg).where(m.PlanLeg.plan_id == plan.id, m.PlanLeg.direction == "outbound")
                            .order_by(m.PlanLeg.seq))).scalars().all()
    parts = []
    for l in legs:
        if l.mode == "walk":
            parts.append(f"walk {l.details.get('minutes')} minutes to {l.to_label}")
        elif l.mode == "metro":
            parts.append(f"{l.details.get('line_name')} from {l.from_label} at {hhmm(l.start_at)}")
        elif l.mode == "flight":
            parts.append(f"{l.details.get('airline')} flight at {hhmm(l.start_at)}, landing {hhmm(l.end_at)}")
        elif l.mode == "hotel":
            parts.append(f"check in at {l.details.get('hotel')}")
    await _log(s, "get_plan_details", conv, f"plan rank {plan.rank}")
    return reply(True, "ok", "Here is the plan: " + ", then ".join(parts) + f". Total ₹{plan.total_price:,}.",
                 f"प्लान: कुल ₹{plan.total_price:,}।", "ask_user_to_approve_on_screen", plan_id=str(plan.id), total=plan.total_price)


@router.post("/modify_plan")
async def modify_plan(body: ModifyIn, s: AsyncSession = Depends(get_session)):
    conv = await _conv(s, body.session_code)
    if not conv:
        return UNKNOWN_CODE
    r = await converse(s, conv, body.change, channel="voice")
    await _log(s, "modify_plan", conv, r["status"])
    return reply(r["status"] in ("plan_ready", "ask"), r["status"], r["reply_en"], r["reply_hi"], r.get("next_action") or "read_back",
                 missing_slots=r["missing_slots"], assumptions=r["assumptions"], trip_id=r["trip_id"], revision=r["revision"])


@router.post("/send_for_approval")
async def send_for_approval(body: ApprovalIn, s: AsyncSession = Depends(get_session)):
    conv = await _conv(s, body.session_code)
    if not conv:
        return UNKNOWN_CODE
    trip = await s.get(m.Trip, conv.trip_id) if conv.trip_id else None
    if not trip:
        return reply(False, "no_plan", "There is no plan to approve yet.", "अभी अप्रूव करने के लिए कोई प्लान नहीं है।", "ask_where_to_go",
                     errors=["no_plan"])
    try:
        cart = await create_cart(s, trip, body.plan_id, body.addons)
        await s.commit()
    except CheckoutError as e:
        await s.rollback()
        return reply(False, e.code, e.message, e.message, "read_back", errors=[e.code])
    await _log(s, "send_for_approval", conv, f"cart ₹{cart.total:,}")
    return reply(True, "awaiting_approval", f"I've sent it to your Paytm screen to approve. The total is ₹{cart.total:,}. "
                 "Nothing is charged until you approve it there.",
                 f"मैंने इसे आपकी Paytm स्क्रीन पर अप्रूवल के लिए भेज दिया है। कुल ₹{cart.total:,}। वहाँ अप्रूव करने तक कुछ नहीं कटेगा।",
                 "wait_for_on_screen_approval", cart_id=str(cart.id), total=cart.total, trip_id=str(trip.id), revision=trip.revision)


@router.post("/get_booking_status")
async def get_booking_status(body: SessionIn, s: AsyncSession = Depends(get_session)):
    conv = await _conv(s, body.session_code)
    if not conv:
        return UNKNOWN_CODE
    booking = (await s.execute(select(m.Booking).where(m.Booking.trip_id == conv.trip_id))).scalars().first() if conv.trip_id else None
    if not booking or booking.status != "confirmed":
        cart = (await s.execute(select(m.Cart).where(m.Cart.trip_id == conv.trip_id, m.Cart.status == "awaiting_approval"))).scalars().first() \
            if conv.trip_id else None
        await _log(s, "get_booking_status", conv, "not booked")
        if cart:
            return reply(True, "awaiting_approval", "It is not booked yet. It is waiting for your approval on the Paytm screen.",
                         "अभी बुक नहीं हुआ है। यह Paytm स्क्रीन पर आपके अप्रूवल का इंतज़ार कर रहा है।", "wait_for_on_screen_approval")
        return reply(True, "not_booked", "Nothing is booked yet.", "अभी कुछ बुक नहीं हुआ है।", "read_back")
    flight = (await s.execute(select(m.Ticket).where(m.Ticket.booking_id == booking.id, m.Ticket.type == "flight")
                              .order_by(m.Ticket.valid_from))).scalars().first()
    count = len((await s.execute(select(m.Ticket.id).where(m.Ticket.booking_id == booking.id))).all())
    await _log(s, "get_booking_status", conv, "confirmed")
    pnr = f" Your flight reference is {_spell(flight.ticket_no)}." if flight else ""
    return reply(True, "booked", f"Booked. {count} tickets are in your trip wallet.{pnr} These are demo bookings.",
                 f"बुक हो गया। {count} टिकट आपके ट्रिप वॉलेट में हैं। ये डेमो बुकिंग हैं।", "close_or_help", tickets=count)


@router.post("/get_trip_status")
async def get_trip_status(body: SessionIn, s: AsyncSession = Depends(get_session)):
    conv = await _conv(s, body.session_code)
    if not conv:
        return UNKNOWN_CODE
    trip = await s.get(m.Trip, conv.trip_id) if conv.trip_id else None
    if not trip:
        return reply(True, "no_trip", "There is no trip yet.", "अभी कोई ट्रिप नहीं है।", "ask_where_to_go")
    alert = (await s.execute(select(m.GuardianAlert).where(m.GuardianAlert.trip_id == trip.id, m.GuardianAlert.status == "open")
                             .order_by(m.GuardianAlert.created_at.desc()))).scalars().first()
    await _log(s, "get_trip_status", conv, f"{trip.status}, alert={'yes' if alert else 'no'}")
    if alert:
        opts = "; ".join(f"{o.get('label_en')}" for o in alert.options)
        return reply(True, "disrupted", f"{alert.cause} Your options: {opts}. Which one would you like?",
                     f"{alert.cause} आपके विकल्प: {'; '.join(o.get('label_hi', '') for o in alert.options)}।", "ask_disruption_choice",
                     alert_id=str(alert.id), options=[{"option_id": o["id"], "label": o["label_en"]} for o in alert.options])
    return reply(True, trip.status, f"Your trip is {trip.status}. Everything is on time.", f"आपकी ट्रिप {trip.status} है। सब समय पर है।",
                 "close_or_help")


@router.post("/choose_disruption_option")
async def choose_disruption_option(body: ChoiceIn, s: AsyncSession = Depends(get_session)):
    conv = await _conv(s, body.session_code)
    if not conv:
        return UNKNOWN_CODE
    try:
        from . import guardian  # built in step 4
    except ImportError:
        guardian = None
    if guardian is None:
        return reply(False, "not_available", "I can't change the trip from the call yet. Please use the Raahi screen.",
                     "अभी मैं कॉल से ट्रिप नहीं बदल सकता। कृपया राही स्क्रीन का उपयोग करें।", "close_or_help", errors=["not_built"])
    return await guardian.apply_choice_for_voice(s, conv, body.alert_id, body.option_id)


@router.post("/request_human_help")
async def request_human_help(body: HelpIn, s: AsyncSession = Depends(get_session)):
    conv = await _conv(s, body.session_code, create=body.session_code is None)
    if not conv:
        return UNKNOWN_CODE
    case = await open_case(s, body.reason, conv.trip_id, conv.id)
    await _log(s, "request_human_help", conv, case.case_no)
    return reply(True, "escalated", f"I've asked a person from our team to help. Your case number is {_spell(case.case_no)}.",
                 f"मैंने हमारी टीम के एक व्यक्ति से मदद माँगी है। आपका केस नंबर {_spell(case.case_no)} है।", "close", case_no=case.case_no)

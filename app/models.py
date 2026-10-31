"""SQLAlchemy models. Source of truth for supabase/migrations/0001_init.sql (see app/gen_sql.py)."""
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

JSONType = sa.JSON().with_variant(JSONB(), "postgresql")
TS = sa.DateTime(timezone=True)


class Base(DeclarativeBase):
    pass


class Row:
    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(TS, server_default=sa.func.now())
    updated_at: Mapped[datetime] = mapped_column(TS, server_default=sa.func.now(), onupdate=sa.func.now())


def uref(table: str, **kw):
    # Deferred: checked at commit, so one batched flush may insert children before parents (no ORM relationships here).
    return mapped_column(sa.Uuid, sa.ForeignKey(f"{table}.id", ondelete="CASCADE", deferrable=True, initially="DEFERRED"), **kw)


def S(n=None, **kw):
    return mapped_column(sa.String(n) if n else sa.Text, **kw)


# ---------- reference & inventory (all seeded rows are demo data) ----------
class City(Row, Base):
    __tablename__ = "cities"
    code: Mapped[str] = S(8, unique=True)
    name: Mapped[str] = S()
    name_hi: Mapped[str] = S(nullable=True)
    is_demo: Mapped[bool] = mapped_column(default=True)


class Place(Row, Base):
    __tablename__ = "places"
    name: Mapped[str] = S()
    name_hi: Mapped[str] = S(nullable=True)
    city_code: Mapped[str] = S(8, index=True)
    lat: Mapped[float] = mapped_column(sa.Float)
    lng: Mapped[float] = mapped_column(sa.Float)
    nearest_station_code: Mapped[str] = S(16)
    walk_minutes: Mapped[int] = mapped_column(sa.Integer)
    aliases: Mapped[list] = mapped_column(JSONType, default=list)
    is_demo: Mapped[bool] = mapped_column(default=True)


class Airport(Row, Base):
    __tablename__ = "airports"
    code: Mapped[str] = S(8, unique=True)
    name: Mapped[str] = S()
    city_code: Mapped[str] = S(8)
    terminals: Mapped[list] = mapped_column(JSONType, default=list)
    is_demo: Mapped[bool] = mapped_column(default=True)


class Station(Row, Base):
    __tablename__ = "stations"
    code: Mapped[str] = S(8, unique=True)
    name: Mapped[str] = S()
    city_code: Mapped[str] = S(8)
    is_demo: Mapped[bool] = mapped_column(default=True)


class BusStand(Row, Base):
    __tablename__ = "bus_stands"
    name: Mapped[str] = S()
    city_code: Mapped[str] = S(8)
    is_demo: Mapped[bool] = mapped_column(default=True)


class MetroLine(Row, Base):
    __tablename__ = "metro_lines"
    code: Mapped[str] = S(16, unique=True)
    city_code: Mapped[str] = S(8, index=True)
    name: Mapped[str] = S()
    headway_min: Mapped[int] = mapped_column(sa.Integer, default=10)
    minutes_per_stop: Mapped[float] = mapped_column(sa.Float, default=2.5)
    fare_base: Mapped[int] = mapped_column(sa.Integer, default=10)  # fare rule: base + per_stop * stops
    fare_per_stop: Mapped[int] = mapped_column(sa.Integer, default=5)
    fare_cap: Mapped[int] = mapped_column(sa.Integer, default=70)
    is_demo: Mapped[bool] = mapped_column(default=True)


class MetroStation(Row, Base):
    __tablename__ = "metro_stations"
    code: Mapped[str] = S(16, unique=True)
    name: Mapped[str] = S()
    city_code: Mapped[str] = S(8, index=True)
    line_code: Mapped[str] = S(16, index=True)
    seq: Mapped[int] = mapped_column(sa.Integer)
    interchange: Mapped[list] = mapped_column(JSONType, default=list)  # other line codes
    airport_code: Mapped[str] = S(8, nullable=True)
    terminal: Mapped[str] = S(8, nullable=True)
    is_demo: Mapped[bool] = mapped_column(default=True)


class MetroServiceHours(Row, Base):
    __tablename__ = "metro_service_hours"
    line_code: Mapped[str] = S(16, unique=True)
    first_train: Mapped[str] = S(5)  # HH:MM, demo assumption
    last_train: Mapped[str] = S(5)
    is_demo: Mapped[bool] = mapped_column(default=True)


class Flight(Row, Base):
    __tablename__ = "flights"
    airline: Mapped[str] = S()
    flight_no: Mapped[str] = S(12, index=True)
    is_budget: Mapped[bool] = mapped_column(default=True)
    from_airport: Mapped[str] = S(8, index=True)
    from_terminal: Mapped[str] = S(8)
    to_airport: Mapped[str] = S(8)
    to_terminal: Mapped[str] = S(8)
    dep_at: Mapped[datetime] = mapped_column(TS, index=True)
    arr_at: Mapped[datetime] = mapped_column(TS)
    fare: Mapped[int] = mapped_column(sa.Integer)
    seats_left: Mapped[int] = mapped_column(sa.Integer)
    baggage: Mapped[str] = S(nullable=True)
    is_demo: Mapped[bool] = mapped_column(default=True)


class Train(Row, Base):
    __tablename__ = "trains"
    number: Mapped[str] = S(8)
    name: Mapped[str] = S()
    from_station: Mapped[str] = S(8)
    to_station: Mapped[str] = S(8)
    dep_at: Mapped[datetime] = mapped_column(TS, index=True)
    arr_at: Mapped[datetime] = mapped_column(TS)
    classes: Mapped[list] = mapped_column(JSONType, default=list)  # [{class,fare,availability}]
    is_demo: Mapped[bool] = mapped_column(default=True)


class Bus(Row, Base):
    __tablename__ = "buses"
    operator: Mapped[str] = S()
    from_city: Mapped[str] = S(8)
    to_city: Mapped[str] = S(8)
    dep_at: Mapped[datetime] = mapped_column(TS)
    arr_at: Mapped[datetime] = mapped_column(TS)
    fare: Mapped[int] = mapped_column(sa.Integer)
    live_tracking: Mapped[bool] = mapped_column(default=False)
    is_demo: Mapped[bool] = mapped_column(default=True)


class Hotel(Row, Base):
    __tablename__ = "hotels"
    name: Mapped[str] = S()
    city_code: Mapped[str] = S(8, index=True)
    area: Mapped[str] = S()
    lat: Mapped[float] = mapped_column(sa.Float)
    lng: Mapped[float] = mapped_column(sa.Float)
    walk_min_from_cp: Mapped[int] = mapped_column(sa.Integer, default=0)
    price_per_night: Mapped[int] = mapped_column(sa.Integer)
    rating: Mapped[float] = mapped_column(sa.Float)
    check_in: Mapped[str] = S(5, default="14:00")
    check_out: Mapped[str] = S(5, default="11:00")
    partner: Mapped[str] = S(default="Agoda")
    is_demo: Mapped[bool] = mapped_column(default=True)


class Addon(Row, Base):
    __tablename__ = "addons"
    code: Mapped[str] = S(32, unique=True)
    name: Mapped[str] = S()
    description: Mapped[str] = S()
    price: Mapped[int] = mapped_column(sa.Integer)
    is_demo: Mapped[bool] = mapped_column(default=True)


# ---------- trip lifecycle ----------
class User(Row, Base):
    __tablename__ = "users"
    name: Mapped[str] = S()
    preferred_language: Mapped[str] = S(8, default="en")
    phone: Mapped[str] = S(nullable=True)
    is_demo: Mapped[bool] = mapped_column(default=True)


class Conversation(Row, Base):
    __tablename__ = "conversations"
    user_id: Mapped[uuid.UUID] = uref("users")
    session_code: Mapped[str] = S(8, index=True)
    trip_request_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=True)
    trip_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=True)


class Message(Row, Base):
    __tablename__ = "messages"
    conversation_id: Mapped[uuid.UUID] = uref("conversations", index=True)
    role: Mapped[str] = S(12)
    text: Mapped[str] = S()
    language: Mapped[str] = S(8, nullable=True)
    channel: Mapped[str] = S(8, default="chat")


class TripRequest(Row, Base):
    __tablename__ = "trip_requests"
    user_id: Mapped[uuid.UUID] = uref("users")
    origin: Mapped[str] = S(nullable=True)
    destination: Mapped[str] = S(nullable=True)
    depart_date: Mapped[str] = S(10, nullable=True)
    return_date: Mapped[str] = S(10, nullable=True)
    party_size: Mapped[int] = mapped_column(sa.Integer, default=1)
    priority: Mapped[str] = S(12, default="economical")
    time_preference: Mapped[str] = S(nullable=True)
    arrive_by: Mapped[str] = S(5, nullable=True)
    budget: Mapped[int] = mapped_column(sa.Integer, nullable=True)
    requested_services: Mapped[list] = mapped_column(JSONType, default=list)
    raw_text: Mapped[str] = S(nullable=True)
    missing_slots: Mapped[list] = mapped_column(JSONType, default=list)
    assumed_slots: Mapped[list] = mapped_column(JSONType, default=list)  # filled by defaults, shown as chips
    plan_type: Mapped[str] = S(12, default="intercity")  # intercity / commute / day_plan


class Trip(Row, Base):
    __tablename__ = "trips"
    user_id: Mapped[uuid.UUID] = uref("users")
    request_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=True)
    status: Mapped[str] = S(16, default="planned")
    plan_type: Mapped[str] = S(12, default="intercity")
    revision: Mapped[int] = mapped_column(sa.Integer, default=0)
    selected_plan_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=True)


class TripPlan(Row, Base):
    __tablename__ = "trip_plans"
    request_id: Mapped[uuid.UUID] = uref("trip_requests", index=True)
    trip_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, index=True, nullable=True)
    rank: Mapped[int] = mapped_column(sa.Integer)
    status: Mapped[str] = S(12, default="proposed")  # proposed/rejected/selected
    total_price: Mapped[int] = mapped_column(sa.Integer)
    total_duration: Mapped[int] = mapped_column(sa.Integer)  # outbound door-to-door minutes
    explanation_en: Mapped[str] = S(nullable=True)
    explanation_hi: Mapped[str] = S(nullable=True)
    is_pick: Mapped[bool] = mapped_column(default=False)


class PlanLeg(Row, Base):
    __tablename__ = "plan_legs"
    plan_id: Mapped[uuid.UUID] = uref("trip_plans", index=True)
    seq: Mapped[int] = mapped_column(sa.Integer)
    direction: Mapped[str] = S(8)
    mode: Mapped[str] = S(8)
    from_label: Mapped[str] = S()
    to_label: Mapped[str] = S()
    start_at: Mapped[datetime] = mapped_column(TS)
    end_at: Mapped[datetime] = mapped_column(TS)
    price: Mapped[int] = mapped_column(sa.Integer, default=0)
    details: Mapped[dict] = mapped_column(JSONType, default=dict)


class CheckResultRow(Row, Base):
    __tablename__ = "check_results"
    plan_id: Mapped[uuid.UUID] = uref("trip_plans", index=True)
    rule_id: Mapped[str] = S(32)
    passed: Mapped[bool] = mapped_column()
    severity: Mapped[str] = S(8)
    message_en: Mapped[str] = S()
    message_hi: Mapped[str] = S()
    evidence: Mapped[dict] = mapped_column(JSONType, default=dict)


class Cart(Row, Base):
    __tablename__ = "carts"
    trip_id: Mapped[uuid.UUID] = uref("trips", index=True)
    plan_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid)
    status: Mapped[str] = S(20, default="open")  # open / awaiting_approval / superseded / booked
    total: Mapped[int] = mapped_column(sa.Integer, default=0)


class CartItem(Row, Base):
    __tablename__ = "cart_items"
    cart_id: Mapped[uuid.UUID] = uref("carts", index=True)
    kind: Mapped[str] = S(8)  # leg / addon
    ref_id: Mapped[str] = S()
    label: Mapped[str] = S()
    price: Mapped[int] = mapped_column(sa.Integer)
    search_price: Mapped[int] = mapped_column(sa.Integer)


class Approval(Row, Base):
    __tablename__ = "approvals"
    cart_id: Mapped[uuid.UUID] = uref("carts", index=True)
    approved_by: Mapped[str] = S()
    channel: Mapped[str] = S(8)
    idempotency_key: Mapped[str] = S(64, unique=True)


class Booking(Row, Base):
    __tablename__ = "bookings"
    cart_id: Mapped[uuid.UUID] = uref("carts", index=True)
    trip_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, index=True)
    status: Mapped[str] = S(12, default="pending")
    pnrs: Mapped[dict] = mapped_column(JSONType, default=dict)


class Ticket(Row, Base):
    __tablename__ = "tickets"
    booking_id: Mapped[uuid.UUID] = uref("bookings", index=True)
    trip_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, index=True)
    leg_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=True)
    type: Mapped[str] = S(12)
    title: Mapped[str] = S()
    ticket_no: Mapped[str] = S()
    qr_payload: Mapped[str] = S()
    valid_from: Mapped[datetime] = mapped_column(TS, nullable=True)
    valid_to: Mapped[datetime] = mapped_column(TS, nullable=True)
    status: Mapped[str] = S(12, default="active")


class TripEvent(Row, Base):
    """Append-only; SSE and the activity timeline read from here."""
    __tablename__ = "trip_events"
    trip_id: Mapped[uuid.UUID] = uref("trips", index=True)
    seq: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), unique=True)
    revision: Mapped[int] = mapped_column(sa.Integer)
    type: Mapped[str] = S(32)
    payload: Mapped[dict] = mapped_column(JSONType, default=dict)


class AgentEvent(Row, Base):
    __tablename__ = "agent_events"
    seq: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), unique=True)
    agent: Mapped[str] = S(16)
    action: Mapped[str] = S()
    trip_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=True, index=True)
    request_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=True)
    input_summary: Mapped[str] = S(nullable=True)
    output_summary: Mapped[str] = S(nullable=True)
    status: Mapped[str] = S(10, default="ok")
    duration_ms: Mapped[int] = mapped_column(sa.Integer, default=0)


class StatusFeed(Row, Base):
    __tablename__ = "status_feed"
    trip_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, index=True)
    leg_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid)
    status: Mapped[str] = S(12)  # on_time/delayed/cancelled
    delay_minutes: Mapped[int] = mapped_column(sa.Integer, default=0)
    source: Mapped[str] = S(12, default="simulated")
    processed: Mapped[bool] = mapped_column(default=False)


class GuardianAlert(Row, Base):
    __tablename__ = "guardian_alerts"
    trip_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, index=True)
    cause: Mapped[str] = S()
    options: Mapped[list] = mapped_column(JSONType, default=list)
    chosen_option: Mapped[str] = S(32, nullable=True)
    status: Mapped[str] = S(10, default="open")


class SupportCase(Row, Base):
    __tablename__ = "support_cases"
    trip_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=True)
    case_no: Mapped[str] = S(16, unique=True)
    reason: Mapped[str] = S()
    summary: Mapped[str] = S()
    timeline: Mapped[list] = mapped_column(JSONType, default=list)
    status: Mapped[str] = S(12, default="open")
    assignee: Mapped[str] = S(nullable=True)


class IdempotencyKey(Row, Base):
    __tablename__ = "idempotency_keys"
    key: Mapped[str] = S(64, unique=True)
    endpoint: Mapped[str] = S()
    response_hash: Mapped[str] = S(64, nullable=True)
    response: Mapped[dict] = mapped_column(JSONType, nullable=True)


def _sqlite_seq(model):
    """Postgres assigns `seq` from an identity column; SQLite (local dev/tests) cannot, so emulate it."""
    @sa.event.listens_for(model, "before_insert")
    def _assign(mapper, connection, target):
        if connection.dialect.name == "sqlite" and target.seq is None:
            db_max = connection.execute(sa.select(sa.func.coalesce(sa.func.max(model.seq), 0))).scalar()
            key = f"seq:{model.__tablename__}"
            target.seq = max(db_max, connection.info.get(key, 0)) + 1  # rows in one batch are not in the table yet
            connection.info[key] = target.seq


_sqlite_seq(TripEvent)
_sqlite_seq(AgentEvent)

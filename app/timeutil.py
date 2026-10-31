from datetime import date, datetime, time, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30), "IST")


def now_ist() -> datetime:
    return datetime.now(IST)


def today_ist() -> date:
    return now_ist().date()


def ist(dt: datetime) -> datetime:
    """Normalise DB datetimes (SQLite returns naive; Postgres returns UTC-aware) to IST."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=IST)
    return dt.astimezone(IST)


def at(d: date, hhmm: str) -> datetime:
    h, m = map(int, hhmm.split(":"))
    return datetime.combine(d, time(h, m), tzinfo=IST)


def hhmm(dt: datetime) -> str:
    return ist(dt).strftime("%H:%M")


def minutes(a: datetime, b: datetime) -> int:
    return int((b - a).total_seconds() // 60)

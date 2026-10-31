"""Plain dataclasses used by the Planner and Checker (no DB, so rules stay pure and testable)."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Leg:
    seq: int
    direction: str  # outbound / return
    mode: str  # metro / flight / train / bus / walk / hotel
    from_label: str
    to_label: str
    start: datetime
    end: datetime
    price: int = 0
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class Request:
    origin: str | None = None
    destination: str | None = None
    depart_date: str | None = None  # YYYY-MM-DD
    return_date: str | None = None
    party_size: int = 1
    priority: str = "economical"
    time_preference: str | None = None
    arrive_by: str | None = None  # HH:MM
    budget: int | None = None
    services: list[str] = field(default_factory=list)


@dataclass
class Plan:
    legs: list[Leg]
    request: Request
    label: str = ""
    nights: int = 0

    @property
    def total_price(self) -> int:
        return sum(l.price for l in self.legs)

    def outbound(self) -> list[Leg]:
        return [l for l in self.legs if l.direction == "outbound"]

    def returning(self) -> list[Leg]:
        return [l for l in self.legs if l.direction == "return"]


@dataclass
class CheckResult:
    rule_id: str
    passed: bool
    severity: str  # block / warn / info
    message_en: str
    message_hi: str
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def blocking(self) -> bool:
        return (not self.passed) and self.severity == "block"

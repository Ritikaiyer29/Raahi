"""All Checker thresholds. Every value is a DEMO ASSUMPTION, not an operator rule."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CheckerConfig:
    airport_buffer_min: int = 60  # be at the departure terminal this long before a domestic flight
    planner_target_buffer_min: int = 75  # what the Planner aims for
    min_transfer_min: dict = field(default_factory=lambda: {"metro": 3, "walk": 0, "flight": 30, "hotel": 0, "train": 20, "bus": 15})
    default_arrive_by_lunch: str = "13:00"
    price_drift_ask_pct: float = 3.0  # drift above this -> ASK
    near_tie_pct: float = 5.0  # options within this % -> ASK
    return_offset_days_if_date_passed: int = 2
    min_hotel_rating: float = 3.5


CONFIG = CheckerConfig()

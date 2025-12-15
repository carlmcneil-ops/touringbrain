from datetime import date
from typing import List, Optional

from pydantic import BaseModel


class Location(BaseModel):
    name: str
    latitude: float
    longitude: float


class DaySummary(BaseModel):
    date: date
    rain_mm: float
    wind_avg_kmh: float
    wind_gust_kmh: float
    towing_stress: int
    overnight_temp_c: float
    ai_summary: str
    park_up_flag: bool


class LocationSummary(BaseModel):
    location: Location
    day: DaySummary


class RouteLegInfo(BaseModel):
    distance_km: float
    drive_hours_estimate: float
    max_drive_hours: Optional[float] = None
    within_drive_limit: Optional[bool] = None


class RouteAlternative(BaseModel):
    name: str
    latitude: float
    longitude: float
    drive_hours_estimate: float
    towing_stress: int
    note: Optional[str] = None


class Comparison(BaseModel):
    # "from" | "to" | "same"
    better_for_towing: str
    reason: str


class TouringPlanRequest(BaseModel):
    from_location: Location
    to_location: Location
    travel_day_iso: date
    max_drive_hours: Optional[float] = None


class TouringPlanResponse(BaseModel):
    travel_day_iso: str
    travel_day_human: str
    main_leg: RouteLegInfo
    from_summary: LocationSummary
    to_summary: LocationSummary
    route_towing_stress: int
    comfort_label: str
    comparison: Comparison
    recommendation: str
    alternatives: List[RouteAlternative]
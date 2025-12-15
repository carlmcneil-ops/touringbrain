from datetime import date
from typing import List

from pydantic import BaseModel

from .caravan import Location


class DailyBriefingDay(BaseModel):
    date: date
    rain_mm: float
    wind_avg_kmh: float
    wind_avg_knots: float
    wind_gust_kmh: float
    wind_gust_knots: float
    overnight_temp_c: float
    towing_stress: int
    comfort_label: str
    ai_summary: str


class DailyBriefingRequest(BaseModel):
    location: Location
    days: int = 3  # 1–7 days, we’ll clamp in the route


class DailyBriefingResponse(BaseModel):
    location: Location
    days: List[DailyBriefingDay]
    headline: str
    recommendation: str
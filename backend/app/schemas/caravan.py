from datetime import date
from typing import List, Optional

from pydantic import BaseModel


class Location(BaseModel):
    name: str
    latitude: float
    longitude: float


class CaravanScoreRequest(BaseModel):
    """
    Request body for Caravan Mode scoring.
    For now we just take a current location and an optional home location.
    """
    location: Location
    home_location: Optional[Location] = None


class CaravanDayForecast(BaseModel):
    """
    Per-day forecast and scores for Caravan Mode.
    """
    date: date
    rain_mm: float
    wind_avg_kmh: float
    wind_avg_knots: float
    wind_gust_kmh: float
    wind_gust_knots: float
    towing_stress: int  # 0–100
    overnight_temp_c: float
    ai_summary: str


class CaravanScoreResponse(BaseModel):
    """
    Full Caravan Mode response for a single location.
    """
    location: Location
    days: List[CaravanDayForecast]
    recommendation: str
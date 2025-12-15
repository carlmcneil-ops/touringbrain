from datetime import date
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from ...schemas.caravan import (
    CaravanScoreRequest,
    CaravanScoreResponse,
    CaravanDayForecast,
    Location,
)
from ...services.weather import get_daily_weather
from ...services.caravan_lookup import lookup_caravan


router = APIRouter()


# ------------------------------------------------------------------------------------
# NEW ENDPOINT: caravan lookup
# ------------------------------------------------------------------------------------
@router.get("/lookup")
async def caravan_lookup(
    brand: str = Query(..., description="Caravan brand, e.g. 'Jayco'"),
    model: str = Query(..., description="Caravan model, e.g. 'Journey'"),
    length_category: Optional[str] = Query(
        None,
        description="Optional length hint like '19-20 ft' or '17-18 ft'"
    ),
):
    """
    Look up typical caravan figures (ATM, axle rating, ball weight guidance, etc.)
    All values are guidance only – users must confirm on their compliance plates
    and weigh their van when loaded.
    """
    try:
        matches = lookup_caravan(brand=brand, model=model, length_category=length_category)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not matches:
        return {
            "matches": [],
            "message": (
                "No caravan match found in the TouringBrain guide. "
                "Use your compliance plate and weighbridge figures to enter ATM and ball weight manually."
            ),
        }

    if len(matches) == 1:
        msg = "Found one likely match. Treat these numbers as a starting point only."
    else:
        msg = (
            "Found several possible matches. Pick the closest one to your van and "
            "always confirm against the plate and weighbridge."
        )

    return {
        "matches": [m.dict() for m in matches],
        "message": msg,
    }


# ------------------------------------------------------------------------------------
# EXISTING: towing stress + AI summary (unchanged)
# ------------------------------------------------------------------------------------
def _kmh_to_knots(kmh: float) -> float:
    return round(kmh / 1.852, 1)


def _compute_towing_stress(wind_avg_kmh: float, wind_gust_kmh: float, rain_mm: float) -> int:
    score = 0.0
    if wind_avg_kmh > 10:
        score += min(50.0, (wind_avg_kmh - 10.0) * 2.0)
    if wind_gust_kmh > 30:
        score += min(30.0, (wind_gust_kmh - 30.0) * 2.0)
    score += min(20.0, rain_mm * 2.0)
    return int(round(max(0.0, min(100.0, score))))


def _build_ai_summary(
    rain_mm: float,
    wind_avg_kmh: float,
    wind_gust_kmh: float,
    overnight_temp_c: float,
) -> str:
    parts: List[str] = []

    if wind_avg_kmh >= 30 or wind_gust_kmh >= 40:
        parts.append("Windy with periods that will feel uncomfortable for towing.")
    elif wind_avg_kmh >= 20:
        parts.append("A bit breezy at times but manageable for most rigs.")
    else:
        parts.append("Light winds for most of the day.")

    if rain_mm >= 8:
        parts.append("Expect solid rain at times, roads will be wet.")
    elif rain_mm >= 2:
        parts.append("Some showers around, roads may be damp.")
    else:
        parts.append("Mostly dry with only light or brief showers, if any.")

    if overnight_temp_c <= 2:
        parts.append("Cold overnight, you’ll want decent heating.")
    elif overnight_temp_c <= 6:
        parts.append("Cool overnight, a bit of extra bedding is a good idea.")
    else:
        parts.append("Overnight temperatures are fairly mild.")

    return " ".join(parts)


@router.post("/score", response_model=CaravanScoreResponse)
async def caravan_score(payload: CaravanScoreRequest) -> CaravanScoreResponse:
    loc: Location = payload.location

    try:
        daily = await get_daily_weather(latitude=loc.latitude, longitude=loc.longitude, days=3)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Weather service error: {e}")

    times = daily.get("time", [])
    rain_list = daily.get("precipitation_sum", [])
    wind_max_list = daily.get("wind_speed_10m_max", [])
    gust_max_list = daily.get("wind_gusts_10m_max", [])
    temp_min_list = daily.get("temperature_2m_min", [])

    n = min(len(times), len(rain_list), len(wind_max_list), len(gust_max_list), len(temp_min_list))
    if n == 0:
        raise HTTPException(status_code=502, detail="Weather service returned no daily data")

    days: List[CaravanDayForecast] = []
    park_up_flags: List[bool] = []

    for i in range(n):
        day_date = date.fromisoformat(times[i])
        rain_mm = float(rain_list[i])
        wind_gust_kmh = float(gust_max_list[i])
        wind_max_kmh = float(wind_max_list[i])
        wind_avg_kmh = round(wind_max_kmh * 0.7, 1)
        overnight_temp_c = float(temp_min_list[i])

        towing_stress = _compute_towing_stress(
            wind_avg_kmh=wind_avg_kmh,
            wind_gust_kmh=wind_gust_kmh,
            rain_mm=rain_mm,
        )

        ai_summary = _build_ai_summary(
            rain_mm=rain_mm,
            wind_avg_kmh=wind_avg_kmh,
            wind_gust_kmh=wind_gust_kmh,
            overnight_temp_c=overnight_temp_c,
        )

        days.append(
            CaravanDayForecast(
                date=day_date,
                rain_mm=rain_mm,
                wind_avg_kmh=wind_avg_kmh,
                wind_avg_knots=_kmh_to_knots(wind_avg_kmh),
                wind_gust_kmh=wind_max_kmh,
                wind_gust_knots=_kmh_to_knots(wind_max_kmh),
                towing_stress=towing_stress,
                overnight_temp_c=overnight_temp_c,
                ai_summary=ai_summary,
            )
        )

        park_up_flags.append((wind_avg_kmh >= 30.0) or (wind_gust_kmh >= 40.0))

    today_flag = park_up_flags[0] if len(park_up_flags) > 0 else False
    day2_flag = park_up_flags[1] if len(park_up_flags) > 1 else False
    day3_flag = park_up_flags[2] if len(park_up_flags) > 2 else False

    if today_flag and not (day2_flag or day3_flag):
        recommendation = "Park up today – winds hit our 30 km/h threshold. Tomorrow or Day 3 look better."
    elif day2_flag and not today_flag:
        recommendation = "Today is a better towing day than tomorrow. If you can, move today and park up tomorrow."
    elif today_flag and day2_flag and not day3_flag:
        recommendation = "Next two days look windy. Best towing window is on Day 3 if you can wait."
    else:
        recommendation = "No obvious 'park up' days from wind alone – choose the day that suits your plans."

    return CaravanScoreResponse(
        location=loc,
        days=days,
        recommendation=recommendation,
    )
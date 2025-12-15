from datetime import date
from typing import List

from fastapi import APIRouter, HTTPException

from ...schemas.briefing import (
    DailyBriefingRequest,
    DailyBriefingResponse,
    DailyBriefingDay,
)
from ...schemas.caravan import Location
from ...services.weather import get_daily_weather

router = APIRouter()


def _kmh_to_knots(kmh: float) -> float:
    return round(kmh / 1.852, 1)


def _compute_towing_stress(wind_avg_kmh: float, wind_gust_kmh: float, rain_mm: float) -> int:
    """
    Same basic towing stress logic as Caravan/Touring.
    """
    score = 0.0

    # Average wind: only start counting above 10 km/h
    if wind_avg_kmh > 10:
        score += min(50.0, (wind_avg_kmh - 10.0) * 2.0)  # max 50

    # Gust penalty above 30 km/h
    if wind_gust_kmh > 30:
        score += min(30.0, (wind_gust_kmh - 30.0) * 2.0)  # max 30

    # Rain adds a little, capped at 20
    score += min(20.0, rain_mm * 2.0)

    # Clamp to 0–100
    return int(round(max(0.0, min(100.0, score))))


def _build_ai_summary(rain_mm: float, wind_avg_kmh: float, wind_gust_kmh: float) -> str:
    """
    Simple rule-based language for touring/camping.
    """
    parts: List[str] = []

    # Wind
    if wind_avg_kmh >= 30 or wind_gust_kmh >= 40:
        parts.append("Windy with periods that will feel uncomfortable for towing.")
    elif wind_avg_kmh >= 20:
        parts.append("A bit breezy at times but manageable for most rigs.")
    else:
        parts.append("Light winds for most of the day.")

    # Rain
    if rain_mm >= 8:
        parts.append("Expect solid rain at times, roads will be wet and campsites muddy.")
    elif rain_mm >= 2:
        parts.append("Some showers around, roads and sites may be damp.")
    else:
        parts.append("Mostly dry with only light or brief showers, if any.")

    return " ".join(parts)


def _comfort_label(towing_stress: int, rain_mm: float, overnight_temp_c: float) -> str:
    """
    Quick human label for how the day will *feel* for towing + camping.
    """
    if towing_stress <= 25 and rain_mm < 2 and overnight_temp_c >= 5:
        return "Comfortable"
    if towing_stress <= 50:
        return "OK with care"
    if towing_stress <= 75:
        return "Stressy / exposed"
    return "Rough – park up if you can"


@router.post("/daily", response_model=DailyBriefingResponse)
async def daily_briefing(payload: DailyBriefingRequest) -> DailyBriefingResponse:
    """
    3-day (or up to 7-day) touring/camping outlook for a single location.
    """
    loc: Location = payload.location
    days_requested = max(1, min(payload.days, 7))  # clamp 1–7

    try:
        daily = await get_daily_weather(latitude=loc.latitude, longitude=loc.longitude, days=days_requested)
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

    days_out: List[DailyBriefingDay] = []

    for i in range(n):
        try:
            d = date.fromisoformat(times[i])
        except ValueError:
            # Skip bad dates
            continue

        rain_mm = float(rain_list[i])
        wind_max_kmh = float(wind_max_list[i])
        gust_max_kmh = float(gust_max_list[i])
        overnight_temp_c = float(temp_min_list[i])

        wind_avg_kmh = round(wind_max_kmh * 0.7, 1)
        towing_stress = _compute_towing_stress(
            wind_avg_kmh=wind_avg_kmh,
            wind_gust_kmh=gust_max_kmh,
            rain_mm=rain_mm,
        )

        ai_summary = _build_ai_summary(
            rain_mm=rain_mm,
            wind_avg_kmh=wind_avg_kmh,
            wind_gust_kmh=gust_max_kmh,
        )

        label = _comfort_label(
            towing_stress=towing_stress,
            rain_mm=rain_mm,
            overnight_temp_c=overnight_temp_c,
        )

        days_out.append(
            DailyBriefingDay(
                date=d,
                rain_mm=rain_mm,
                wind_avg_kmh=wind_avg_kmh,
                wind_avg_knots=_kmh_to_knots(wind_avg_kmh),
                wind_gust_kmh=wind_max_kmh,
                wind_gust_knots=_kmh_to_knots(wind_max_kmh),
                overnight_temp_c=overnight_temp_c,
                towing_stress=towing_stress,
                comfort_label=label,
                ai_summary=ai_summary,
            )
        )

    if not days_out:
        raise HTTPException(status_code=502, detail="No valid daily entries in weather data")

    # Build a simple headline / recommendation
    max_stress = max(d.towing_stress for d in days_out)
    min_stress = min(d.towing_stress for d in days_out)

    if max_stress <= 30:
        headline = "Nice run of days for touring and camping."
    elif max_stress <= 60:
        headline = "Mixed few days – some good windows, some rougher patches."
    else:
        headline = "Windy or wet spell coming – pick your window carefully."

    # Pick the "best" moving day as the one with lowest towing_stress
    best_day = min(days_out, key=lambda d: d.towing_stress)
    recommendation = (
        f"The easiest day to move on, from a towing perspective, looks like {best_day.date.isoformat()} "
        f"({best_day.comfort_label.lower()}, stress ~{best_day.towing_stress}/100)."
    )

    return DailyBriefingResponse(
        location=loc,
        days=days_out,
        headline=headline,
        recommendation=recommendation,
    )
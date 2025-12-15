from datetime import date
from math import asin, cos, radians, sin, sqrt, atan2, degrees
from typing import List, Optional

from fastapi import APIRouter, HTTPException

from ...schemas.touring import (
    Comparison,
    DaySummary,
    Location,
    LocationSummary,
    RouteAlternative,
    RouteLegInfo,
    TouringPlanRequest,
    TouringPlanResponse,
)
from ...services.weather import get_daily_weather

router = APIRouter()  # main.py already prefixes /touring


# ---------------------------------------------------------------------
# Basic helpers
# ---------------------------------------------------------------------


def _kmh_to_knots(kmh: float) -> float:
    return round(kmh / 1.852, 1)


def _compute_towing_stress(wind_avg_kmh: float, wind_gust_kmh: float, rain_mm: float) -> int:
    """
    Towing stress score from 0–100.

    - Light wind days land low (20–30)
    - Breezier days mid-range
    - Strong wind / gusts push toward 70–100
    """
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
    """
    Simple rule-based summary for now.
    """
    parts: List[str] = []

    # wind
    if wind_avg_kmh >= 30 or wind_gust_kmh >= 40:
        parts.append("Windy with stretches that will feel tiring for towing.")
    elif wind_avg_kmh >= 20:
        parts.append("A bit breezy at times but manageable for most rigs.")
    else:
        parts.append("Light winds for most of the day.")

    # rain
    if rain_mm >= 8:
        parts.append("Expect proper rain at times, roads will stay wet.")
    elif rain_mm >= 2:
        parts.append("Some showers around, roads may be damp.")
    else:
        parts.append("Mostly dry with only light or brief showers, if any.")

    # overnight temp
    if overnight_temp_c <= 2:
        parts.append("Cold overnight, you’ll want decent heating.")
    elif overnight_temp_c <= 6:
        parts.append("Cool overnight, a bit of extra bedding is a good idea.")
    else:
        parts.append("Overnight temperatures are fairly mild.")

    return " ".join(parts)


def _comfort_label(score: int) -> str:
    if score <= 40:
        return "good"
    if score <= 60:
        return "fair"
    if score <= 80:
        return "caution"
    return "park_up"


def _haversine_km(a: Location, b: Location) -> float:
    """
    Rough great-circle distance in km between two lat/lon points.
    """
    R = 6371.0  # km
    lat1, lon1 = radians(a.latitude), radians(a.longitude)
    lat2, lon2 = radians(b.latitude), radians(b.longitude)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * R * asin(sqrt(h))


def _bearing_deg(a: Location, b: Location) -> float:
    """
    Bearing in degrees from point A to point B (0–360, 0 = north).
    """
    lat1 = radians(a.latitude)
    lat2 = radians(b.latitude)
    dlon = radians(b.longitude - a.longitude)

    x = sin(dlon) * cos(lat2)
    y = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(dlon)
    brng = degrees(atan2(x, y))
    return (brng + 360.0) % 360.0


def _estimate_drive_leg(
    from_loc: Location,
    to_loc: Location,
    max_drive_hours: Optional[float],
) -> RouteLegInfo:
    """
    Very simple drive estimate:
    - Road distance ≈ 1.25 × straight-line distance
    - Average speed ≈ 80 km/h for towing
    """
    straight_km = _haversine_km(from_loc, to_loc)
    road_km = straight_km * 1.25
    drive_hours = road_km / 80.0 if road_km > 0 else 0.0

    within = None
    if max_drive_hours is not None:
        within = drive_hours <= max_drive_hours

    return RouteLegInfo(
        distance_km=round(road_km, 1),
        drive_hours_estimate=round(drive_hours, 2),
        max_drive_hours=max_drive_hours,
        within_drive_limit=within,
    )


# ---------------------------------------------------------------------
# Weather + daily summaries
# ---------------------------------------------------------------------


async def _build_day_summary_for_location(loc: Location, travel_date: date) -> DaySummary:
    """
    Pull daily weather for a few days and pick the entry matching the travel date.
    If there's no exact match, fall back to the first day returned.
    """
    try:
        daily = await get_daily_weather(latitude=loc.latitude, longitude=loc.longitude, days=5)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Weather service error for {loc.name}: {e}")

    times = daily.get("time", [])
    rain_list = daily.get("precipitation_sum", [])
    wind_max_list = daily.get("wind_speed_10m_max", [])
    gust_max_list = daily.get("wind_gusts_10m_max", [])
    temp_min_list = daily.get("temperature_2m_min", [])

    n = min(len(times), len(rain_list), len(wind_max_list), len(gust_max_list), len(temp_min_list))
    if n == 0:
        raise HTTPException(status_code=502, detail=f"Weather service returned no daily data for {loc.name}")

    idx = 0
    for i in range(n):
        try:
            d = date.fromisoformat(times[i])
        except Exception:
            continue
        if d == travel_date:
            idx = i
            break

    day_date = date.fromisoformat(times[idx])
    rain_mm = float(rain_list[idx])
    wind_gust_kmh = float(gust_max_list[idx])
    wind_max_kmh = float(wind_max_list[idx])
    wind_avg_kmh = round(wind_max_kmh * 0.7, 1)
    overnight_temp_c = float(temp_min_list[idx])

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

    park_up = (wind_avg_kmh >= 30.0) or (wind_gust_kmh >= 40.0)

    return DaySummary(
        date=day_date,
        rain_mm=rain_mm,
        wind_avg_kmh=wind_avg_kmh,
        wind_gust_kmh=wind_max_kmh,
        towing_stress=towing_stress,
        overnight_temp_c=overnight_temp_c,
        ai_summary=ai_summary,
        park_up_flag=park_up,
    )


# ---------------------------------------------------------------------
# Comparison + recommendation
# ---------------------------------------------------------------------


def _compare_locations(from_summary: DaySummary, to_summary: DaySummary) -> Comparison:
    if from_summary.towing_stress < to_summary.towing_stress - 5:
        return Comparison(
            better_for_towing="from",
            reason="Your starting point looks calmer for towing on this day than the destination.",
        )
    if to_summary.towing_stress < from_summary.towing_stress - 5:
        return Comparison(
            better_for_towing="to",
            reason="The destination looks calmer for towing on this day than your starting point.",
        )
    return Comparison(
        better_for_towing="same",
        reason="Towing conditions look broadly similar at both ends of the trip.",
    )


def _build_recommendation(
    route_stress: int,
    leg: RouteLegInfo,
) -> str:
    drive_note = ""
    if leg.max_drive_hours is not None:
        if leg.within_drive_limit is False:
            drive_note = (
                f" On these rough numbers this leg is longer than your preferred drive "
                f"window of about {leg.max_drive_hours:.1f} hours."
            )
        elif leg.within_drive_limit is True:
            drive_note = (
                f" On these rough numbers the drive fits within your preferred window of "
                f"about {leg.max_drive_hours:.1f} hours."
            )

    if route_stress >= 80:
        base = (
            "This is a high-stress towing day along this route – strong winds and/or "
            "weather mean it's worth considering a different day or a shorter leg."
        )
    elif route_stress >= 50:
        base = (
            "Conditions look workable but you’ll want to stay switched on – expect some "
            "gusts and patchy weather along the way."
        )
    else:
        base = (
            "On the weather and wind alone, this looks like a decent day for towing this leg."
        )

    return base + drive_note


# ---------------------------------------------------------------------
# Direction-aware alternative stops
# ---------------------------------------------------------------------


ALT_CANDIDATES = [
    # Central Otago / Mackenzie / West Coast-ish circuit
    {"name": "Cromwell", "latitude": -45.031, "longitude": 169.200},
    {"name": "Omarama", "latitude": -44.488, "longitude": 169.971},
    {"name": "Twizel", "latitude": -44.255, "longitude": 170.096},
    {"name": "Haast", "latitude": -43.878, "longitude": 169.042},
    {"name": "Geraldine", "latitude": -44.096, "longitude": 171.242},
]


async def _build_alternatives(
    from_loc: Location,
    to_loc: Location,
    travel_date: date,
    max_drive_hours: Optional[float],
) -> List[RouteAlternative]:
    """
    Suggest a few possible park-up locations based on:
    - real driving distance/time (rough estimate)
    - real weather + towing stress at the alternative
    - alignment with your general direction of travel
    """
    try:
        main_bearing = _bearing_deg(from_loc, to_loc)
    except Exception:
        main_bearing = None

    alternatives: List[RouteAlternative] = []

    for c in ALT_CANDIDATES:
        alt_loc = Location(
            name=c["name"],
            latitude=c["latitude"],
            longitude=c["longitude"],
        )

        # Skip if it's exactly the same as the starting point
        if (
            abs(alt_loc.latitude - from_loc.latitude) < 1e-4
            and abs(alt_loc.longitude - from_loc.longitude) < 1e-4
        ):
            continue

        # Drive estimate from current location to the alternative
        alt_leg = _estimate_drive_leg(from_loc, alt_loc, max_drive_hours)

        # Respect the drive window if given
        if max_drive_hours is not None and alt_leg.within_drive_limit is False:
            continue

        # Weather + towing stress at the alternative
        alt_day = await _build_day_summary_for_location(alt_loc, travel_date)
        alt_stress = alt_day.towing_stress
        alt_label = _comfort_label(alt_stress)

        # Direction of travel vs this alternative
        direction_note = ""
        if main_bearing is not None:
            try:
                alt_bearing = _bearing_deg(from_loc, alt_loc)
                delta = abs(main_bearing - alt_bearing)
                if delta > 180:
                    delta = 360 - delta

                if delta <= 45:
                    direction_note = "Roughly along your general line of travel."
                elif delta <= 90:
                    direction_note = "A small detour off your main line of travel."
                else:
                    direction_note = "More of a side-trip compared with your current route."
            except Exception:
                pass

        note_parts: List[str] = []
        if direction_note:
            note_parts.append(direction_note)
        note_parts.append(f"Towing stress sits around {alt_stress} today ({alt_label}).")
        note = " ".join(note_parts)

        alternatives.append(
            RouteAlternative(
                name=alt_loc.name,
                latitude=alt_loc.latitude,
                longitude=alt_loc.longitude,
                drive_hours_estimate=alt_leg.drive_hours_estimate,
                towing_stress=alt_stress,
                note=note,
            )
        )

    # Prefer calmer, on-route options first
    alternatives.sort(key=lambda a: a.towing_stress)

    return alternatives


# ---------------------------------------------------------------------
# Main endpoint
# ---------------------------------------------------------------------


@router.post("/plan", response_model=TouringPlanResponse)
async def touring_plan(payload: TouringPlanRequest) -> TouringPlanResponse:
    """
    Touring Mode – compare A → B on a given travel day, estimate drive time,
    and give a simple towing comfort view for the route plus some alternatives.
    """
    from_loc: Location = payload.from_location
    to_loc: Location = payload.to_location
    travel_date: date = payload.travel_day_iso

    # Daily summaries at each end
    from_day = await _build_day_summary_for_location(from_loc, travel_date)
    to_day = await _build_day_summary_for_location(to_loc, travel_date)

    from_summary = LocationSummary(location=from_loc, day=from_day)
    to_summary = LocationSummary(location=to_loc, day=to_day)

    # Main leg
    main_leg = _estimate_drive_leg(from_loc, to_loc, payload.max_drive_hours)

    # Route stress = worst of the two ends for now
    route_stress = max(from_day.towing_stress, to_day.towing_stress)
    comfort = _comfort_label(route_stress)

    comparison = _compare_locations(from_day, to_day)
    recommendation = _build_recommendation(route_stress, main_leg)

    # Direction-aware alternatives
    alternatives = await _build_alternatives(
        from_loc=from_loc,
        to_loc=to_loc,
        travel_date=travel_date,
        max_drive_hours=payload.max_drive_hours,
    )

    travel_day_human = travel_date.strftime("%A %d %B %Y")

    return TouringPlanResponse(
        travel_day_iso=travel_date.isoformat(),
        travel_day_human=travel_day_human,
        main_leg=main_leg,
        from_summary=from_summary,
        to_summary=to_summary,
        route_towing_stress=route_stress,
        comfort_label=comfort,
        comparison=comparison,
        recommendation=recommendation,
        alternatives=alternatives,
    )
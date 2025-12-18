# backend/app/api/routes/touring.py

from __future__ import annotations

from datetime import date
from math import asin, cos, radians, sin, sqrt
from typing import List, Optional

from fastapi import APIRouter, HTTPException

from ...schemas.touring import (
    Comparison,
    DaySummary,
    Location,
    LocationSummary,
    RouteAlternative,
    RouteLegInfo,
    RouteWindProfile,
    TouringPlanRequest,
    TouringPlanResponse,
)
from ...services.directions import get_route_km_hours
from ...services.geocode import GeocodeError, geocode_one_nz
from ...services.weather import get_daily_weather

router = APIRouter()


# ---------------------------------------------------------------------
# Basic helpers
# ---------------------------------------------------------------------

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
        parts.append("Windy with stretches that will feel tiring for towing.")
    elif wind_avg_kmh >= 20:
        parts.append("A bit breezy at times but manageable for most rigs.")
    else:
        parts.append("Light winds for most of the day.")

    if rain_mm >= 8:
        parts.append("Expect proper rain at times, roads will stay wet.")
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


def _comfort_label(score: int) -> str:
    if score <= 40:
        return "good"
    if score <= 60:
        return "fair"
    if score <= 80:
        return "caution"
    return "park_up"


def _haversine_km(a: Location, b: Location) -> float:
    # Safe fallback only — not “good enough” for real drive times
    R = 6371.0
    lat1, lon1 = radians(a.latitude or 0.0), radians(a.longitude or 0.0)
    lat2, lon2 = radians(b.latitude or 0.0), radians(b.longitude or 0.0)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * R * asin(sqrt(h))


async def _estimate_drive_leg(
    from_loc: Location,
    to_loc: Location,
    max_drive_hours: Optional[float],
) -> RouteLegInfo:
    """
    Primary: Mapbox Directions (real road distance + duration).
    Fallback: simple heuristic (ONLY if Mapbox fails) + logs why.
    """

    # Don’t ever send 0,0 to Mapbox. If coords are missing, something upstream failed.
    if from_loc.latitude is None or from_loc.longitude is None:
        raise HTTPException(status_code=500, detail="from_loc missing lat/lon (geocode failed upstream)")
    if to_loc.latitude is None or to_loc.longitude is None:
        raise HTTPException(status_code=500, detail="to_loc missing lat/lon (geocode failed upstream)")

    road_km: float
    drive_hours: float

    try:
        dist_km, hours = await get_route_km_hours(
            from_lat=float(from_loc.latitude),
            from_lon=float(from_loc.longitude),
            to_lat=float(to_loc.latitude),
            to_lon=float(to_loc.longitude),
        )

        # Optional towing realism: don’t claim an average faster than 90 km/h.
        # (This mainly protects you from “optimistic” routing times.)
        towing_floor = dist_km / 90.0
        hours = max(hours, towing_floor)

        road_km = float(dist_km)
        drive_hours = float(hours)

    except Exception as e:
        # Important: don’t silently regress. Log why we fell back.
        print("⚠️ Mapbox routing failed; falling back to heuristic:", repr(e))

        straight_km = _haversine_km(from_loc, to_loc)
        road_km = straight_km * 1.25
        drive_hours = (road_km / 80.0) if road_km > 0 else 0.0

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
# Geocode + weather
# ---------------------------------------------------------------------

async def _resolve_location(loc: Location) -> Location:
    if loc.latitude is not None and loc.longitude is not None:
        return loc

    name = (loc.name or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="Location name is required.")

    try:
        hit = await geocode_one_nz(name)
    except GeocodeError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return Location(
        name=hit.get("name") or name,
        latitude=float(hit["latitude"]),
        longitude=float(hit["longitude"]),
    )


async def _build_day_summary_for_location(loc: Location, travel_date: date) -> DaySummary:
    daily = await get_daily_weather(
        latitude=float(loc.latitude or 0.0),
        longitude=float(loc.longitude or 0.0),
        days=5,
    )

    times = daily.get("time", [])
    rain = daily.get("precipitation_sum", [])
    wind_max = daily.get("wind_speed_10m_max", [])
    gusts = daily.get("wind_gusts_10m_max", [])
    temp_min = daily.get("temperature_2m_min", [])

    idx = 0
    for i, t in enumerate(times):
        if date.fromisoformat(t) == travel_date:
            idx = i
            break

    rain_mm = float(rain[idx])
    wind_gust_kmh = float(gusts[idx])
    wind_avg_kmh = round(float(wind_max[idx]) * 0.7, 1)
    overnight_temp_c = float(temp_min[idx])

    towing_stress = _compute_towing_stress(wind_avg_kmh, wind_gust_kmh, rain_mm)

    return DaySummary(
        date=travel_date,
        rain_mm=rain_mm,
        wind_avg_kmh=wind_avg_kmh,
        wind_gust_kmh=wind_gust_kmh,
        towing_stress=towing_stress,
        overnight_temp_c=overnight_temp_c,
        ai_summary=_build_ai_summary(rain_mm, wind_avg_kmh, wind_gust_kmh, overnight_temp_c),
        park_up_flag=(wind_avg_kmh >= 30 or wind_gust_kmh >= 40),
    )


# ---------------------------------------------------------------------
# Route wind sampling
# ---------------------------------------------------------------------

def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _make_route_samples(from_loc: Location, to_loc: Location, samples: int) -> List[Location]:
    samples = max(3, min(21, samples))
    out: List[Location] = []

    for i in range(samples):
        t = i / (samples - 1)
        out.append(
            Location(
                name=f"Route sample {i+1}",
                latitude=_lerp(float(from_loc.latitude), float(to_loc.latitude), t),
                longitude=_lerp(float(from_loc.longitude), float(to_loc.longitude), t),
            )
        )
    return out


async def _build_route_wind_profile(
    from_loc: Location,
    to_loc: Location,
    travel_date: date,
    main_leg: RouteLegInfo,
    samples: int = 9,
) -> RouteWindProfile:
    pts = _make_route_samples(from_loc, to_loc, samples)

    worst_idx = 0
    worst_day: Optional[DaySummary] = None
    worst_score = -1

    for i, loc in enumerate(pts):
        day = await _build_day_summary_for_location(loc, travel_date)
        if day.towing_stress > worst_score:
            worst_score = day.towing_stress
            worst_idx = i
            worst_day = day

    km_at = round(main_leg.distance_km * (worst_idx / (len(pts) - 1)), 1)

    return RouteWindProfile(
        samples=len(pts),
        worst_at_km_from_start=km_at,
        worst_wind_avg_kmh=(worst_day.wind_avg_kmh if worst_day else 0.0),
        worst_wind_gust_kmh=(worst_day.wind_gust_kmh if worst_day else 0.0),
        worst_towing_stress=(worst_day.towing_stress if worst_day else 0),
        note="Wind exposure sampled along the A→B line (not road routing).",
    )


# ---------------------------------------------------------------------
# Main endpoint
# ---------------------------------------------------------------------

@router.post("/plan", response_model=TouringPlanResponse)
async def touring_plan(payload: TouringPlanRequest) -> TouringPlanResponse:
    print("TOURING payload:", payload.model_dump())

    from_loc = await _resolve_location(payload.from_location)
    to_loc = await _resolve_location(payload.to_location)
    travel_date = payload.travel_day_iso

    print("RESOLVED from_loc:", from_loc.model_dump())
    print("RESOLVED to_loc:", to_loc.model_dump())

    from_day = await _build_day_summary_for_location(from_loc, travel_date)
    to_day = await _build_day_summary_for_location(to_loc, travel_date)

    from_summary = LocationSummary(location=from_loc, day=from_day)
    to_summary = LocationSummary(location=to_loc, day=to_day)

    main_leg = await _estimate_drive_leg(from_loc, to_loc, payload.max_drive_hours)
    print("LEG:", main_leg.model_dump())

    route_wind_profile = await _build_route_wind_profile(
        from_loc=from_loc,
        to_loc=to_loc,
        travel_date=travel_date,
        main_leg=main_leg,
        samples=9,
    )

    route_stress = max(from_day.towing_stress, to_day.towing_stress)
    comfort = _comfort_label(route_stress)

    comparison = (
        Comparison(better_for_towing="from", reason="Start is calmer.")
        if from_day.towing_stress < to_day.towing_stress - 5
        else Comparison(better_for_towing="to", reason="Destination is calmer.")
        if to_day.towing_stress < from_day.towing_stress - 5
        else Comparison(better_for_towing="same", reason="Conditions are similar.")
    )

    return TouringPlanResponse(
        travel_day_iso=travel_date.isoformat(),
        travel_day_human=travel_date.strftime("%A %d %B %Y"),
        main_leg=main_leg,
        from_summary=from_summary,
        to_summary=to_summary,
        route_towing_stress=route_stress,
        comfort_label=comfort,
        comparison=comparison,
        recommendation=_build_ai_summary(
            rain_mm=max(from_day.rain_mm, to_day.rain_mm),
            wind_avg_kmh=max(from_day.wind_avg_kmh, to_day.wind_avg_kmh),
            wind_gust_kmh=max(from_day.wind_gust_kmh, to_day.wind_gust_kmh),
            overnight_temp_c=min(from_day.overnight_temp_c, to_day.overnight_temp_c),
        ),
        route_wind_profile=route_wind_profile,
        alternatives=[],
    )
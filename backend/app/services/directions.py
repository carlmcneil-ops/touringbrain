from __future__ import annotations

import os
from typing import Any, Dict, Tuple

import httpx

MAPBOX_DIRECTIONS_URL = "https://api.mapbox.com/directions/v5/mapbox/driving"


class DirectionsError(RuntimeError):
    pass


def _get_mapbox_token() -> str:
    token = (os.getenv("MAPBOX_TOKEN") or "").strip()
    if not token:
        raise DirectionsError("MAPBOX_TOKEN is not set in environment")
    return token


def _get_towing_factor() -> float:
    """
    Multiplier applied to Mapbox duration to better reflect towing reality.
    Example: 1.10 = +10% time.
    """
    raw = (os.getenv("TOWING_TIME_FACTOR") or "").strip()
    if not raw:
        return 1.10
    try:
        v = float(raw)
        return v if v > 0 else 1.10
    except Exception:
        return 1.10


async def get_route_km_hours(
    *,
    from_lat: float,
    from_lon: float,
    to_lat: float,
    to_lon: float,
    timeout_s: float = 12.0,
) -> Tuple[float, float]:
    """
    Returns (distance_km, duration_hours) using Mapbox Directions API.
    Duration is adjusted by towing factor.
    """
    token = _get_mapbox_token()

    # Mapbox expects lon,lat order
    coords = f"{from_lon},{from_lat};{to_lon},{to_lat}"
    url = f"{MAPBOX_DIRECTIONS_URL}/{coords}"

    params = {
        "access_token": token,
        "alternatives": "false",
        "overview": "false",
        "steps": "false",
    }

    async with httpx.AsyncClient(timeout=timeout_s) as client:
        r = await client.get(url, params=params)
        if r.status_code == 401:
            raise DirectionsError("Mapbox token rejected (401). Check MAPBOX_TOKEN.")
        r.raise_for_status()
        data: Dict[str, Any] = r.json()

    routes = data.get("routes") or []
    if not routes:
        code = data.get("code")
        msg = data.get("message")
        raise DirectionsError(f"No routes returned by Mapbox for this A→B (code={code}, message={msg})")

    route0 = routes[0]
    dist_m = route0.get("distance")
    dur_s = route0.get("duration")

    if dist_m is None or dur_s is None:
        print("⚠️ Mapbox route0 keys:", list(route0.keys()))
        raise DirectionsError("Mapbox route missing distance/duration fields")

    distance_km = float(dist_m) / 1000.0
    towing_factor = _get_towing_factor()
    duration_hours = (float(dur_s) / 3600.0) * towing_factor

    return distance_km, duration_hours


async def get_route_km_hours_polyline6(
    *,
    from_lat: float,
    from_lon: float,
    to_lat: float,
    to_lon: float,
    timeout_s: float = 12.0,
) -> Tuple[float, float, str]:
    """
    Returns (distance_km, duration_hours, polyline6) using Mapbox Directions API.
    Only needed if you ever re-enable the route image/map feature.
    """
    token = _get_mapbox_token()

    coords = f"{from_lon},{from_lat};{to_lon},{to_lat}"
    url = f"{MAPBOX_DIRECTIONS_URL}/{coords}"

    params = {
        "access_token": token,
        "alternatives": "false",
        "overview": "simplified",
        "steps": "false",
        "geometries": "polyline6",
    }

    async with httpx.AsyncClient(timeout=timeout_s) as client:
        r = await client.get(url, params=params)
        if r.status_code == 401:
            raise DirectionsError("Mapbox token rejected (401). Check MAPBOX_TOKEN.")
        r.raise_for_status()
        data: Dict[str, Any] = r.json()

    routes = data.get("routes") or []
    if not routes:
        code = data.get("code")
        msg = data.get("message")
        raise DirectionsError(f"No routes returned by Mapbox for this A→B (code={code}, message={msg})")

    route0 = routes[0]
    dist_m = route0.get("distance")
    dur_s = route0.get("duration")
    geom = route0.get("geometry")

    if dist_m is None or dur_s is None or not geom:
        print("⚠️ Mapbox route0 keys:", list(route0.keys()))
        raise DirectionsError("Mapbox route missing distance/duration/geometry fields")

    distance_km = float(dist_m) / 1000.0
    towing_factor = _get_towing_factor()
    duration_hours = (float(dur_s) / 3600.0) * towing_factor

    return distance_km, duration_hours, str(geom)
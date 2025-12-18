from __future__ import annotations

from typing import Any, Dict, List

import httpx


OPEN_METEO_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"


class GeocodeError(RuntimeError):
    pass


def _normalise_place_query(place: str) -> str:
    q = (place or "").strip()
    key = q.lower().replace(".", "").replace("’", "'")

    aliases = {
        "mt cook": "Mount Cook Village",
        "mount cook": "Mount Cook Village",
        "aoraki": "Mount Cook Village",
        "aoraki mt cook": "Mount Cook Village",
        "aoraki mount cook": "Mount Cook Village",
        "mt cook village": "Mount Cook Village",
        "mount cook village": "Mount Cook Village",
    }

    # IMPORTANT: keep a blank line after this return.
    return aliases.get(key, q)


def _pick_best_result(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not results:
        raise GeocodeError("No geocoding results to choose from")

    def score(r: Dict[str, Any]) -> float:
        pop = r.get("population")
        try:
            return float(pop) if pop is not None else 0.0
        except Exception:
            return 0.0

    return sorted(results, key=score, reverse=True)[0]


async def geocode_nz(
    place: str,
    *,
    count: int = 5,
    timeout_s: float = 10.0,
) -> List[Dict[str, Any]]:
    q = _normalise_place_query(place)
    if not q:
        raise GeocodeError("Place name is empty")

    params = {
        "name": q,
        "count": int(count),
        "language": "en",
        "format": "json",
        "country_code": "NZ",
    }

    async with httpx.AsyncClient(timeout=timeout_s) as client:
        r = await client.get(OPEN_METEO_GEOCODE_URL, params=params)
        r.raise_for_status()
        data = r.json()

    results = data.get("results") or []
    out: List[Dict[str, Any]] = []

    for res in results:
        lat = res.get("latitude")
        lon = res.get("longitude")
        name = res.get("name")

        if lat is None or lon is None or not name:
            continue

        country = (res.get("country") or "").strip()
        country_code = (res.get("country_code") or "").strip().upper()

        is_nz = (country_code == "NZ") or (country == "New Zealand")

        if not is_nz:
            try:
                latf = float(lat)
                lonf = float(lon)
            except Exception:
                continue

            if (-47.5 <= latf <= -33.5) and (165.0 <= lonf <= 179.5):
                is_nz = True

        if not is_nz:
            continue

        out.append(
            {
                "name": str(name),
                "latitude": float(lat),
                "longitude": float(lon),
                "admin1": res.get("admin1"),
                "admin2": res.get("admin2"),
                "country": res.get("country"),
                "confidence": res.get("confidence"),
                "timezone": res.get("timezone"),
                "country_code": res.get("country_code"),
            }
        )

    return out


async def geocode_one_nz(
    place: str,
    *,
    timeout_s: float = 10.0,
) -> Dict[str, Any]:
    raw = (place or "").strip()
    if not raw:
        raise GeocodeError("Place name is empty")

    q = _normalise_place_query(raw)

    matches = await geocode_nz(q, count=10, timeout_s=timeout_s)

    if not matches and "," not in q:
        matches = await geocode_nz(f"{q}, NZ", count=10, timeout_s=timeout_s)

    if not matches:
        raise GeocodeError(f"No NZ match found for '{place}'")

    return _pick_best_result(matches)
import json
import os
from typing import List, Optional

from app.schemas.vehicle import VehicleInfo

# Simple in-memory cache so we only read the JSON once
_DB_CACHE: List[dict] = []
_DB_LOADED: bool = False


def _get_data_path() -> str:
    """
    Resolve the path to backend/app/data/vehicles.json
    relative to this file.
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    data_path = os.path.join(current_dir, "..", "data", "vehicles.json")
    return os.path.normpath(data_path)


def _load_vehicle_db() -> List[dict]:
    """
    Load the vehicle database from JSON.
    """
    global _DB_CACHE, _DB_LOADED

    if _DB_LOADED:
        return _DB_CACHE

    data_path = _get_data_path()
    if not os.path.exists(data_path):
        raise FileNotFoundError(f"vehicles.json not found at {data_path}")

    with open(data_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    vehicles = raw.get("vehicles", [])
    if not isinstance(vehicles, list):
        raise ValueError("vehicles.json is not in the expected format: 'vehicles' must be a list")

    _DB_CACHE = vehicles
    _DB_LOADED = True
    return _DB_CACHE


def _normalise(value: Optional[str]) -> str:
    if not value:
        return ""
    return value.strip().lower()


def _vehicle_matches(record: dict, make: str, model: str, year: Optional[int], variant: Optional[str]) -> bool:
    """
    Basic match:
    - make + model must match (case-insensitive)
    - year must be inside year_range if both are present
    - variant is "soft" (we don't reject if it's different)
    """
    make_ok = _normalise(record.get("make")) == _normalise(make)
    model_ok = _normalise(record.get("model")) == _normalise(model)

    if not (make_ok and model_ok):
        return False

    # Year range check, if we have both year and a parsable range
    if year is not None:
        year_range = record.get("year_range") or ""
        if "-" in year_range:
            parts = year_range.split("-")
            try:
                start = int(parts[0])
                end = int(parts[1])
                if not (start <= year <= end):
                    return False
            except ValueError:
                # If parsing fails, ignore year
                pass

    # Variant is just advisory – we don't filter hard on it for now
    return True


def lookup_vehicle(
    make: str,
    model: str,
    year: Optional[int] = None,
    variant: Optional[str] = None,
) -> List[VehicleInfo]:
    """
    Look up one or more vehicle records matching the given fields.
    Returns a list of VehicleInfo objects. Can be empty if nothing matches.
    """
    vehicles = _load_vehicle_db()
    matches: List[VehicleInfo] = []

    for rec in vehicles:
        if _vehicle_matches(rec, make, model, year, variant):
            info = VehicleInfo(
                vehicle_id=rec.get("id", ""),
                make=rec.get("make", ""),
                model=rec.get("model", ""),
                year_range=rec.get("year_range", ""),
                variant=rec.get("variant", ""),
                country_region=rec.get("country_region"),
                braked_tow_capacity_kg=rec.get("braked_tow_capacity_kg"),
                unbraked_tow_capacity_kg=rec.get("unbraked_tow_capacity_kg"),
                max_ball_weight_kg=rec.get("max_ball_weight_kg"),
                gvm_kg=rec.get("gvm_kg"),
                gcm_kg=rec.get("gcm_kg"),
                confidence=rec.get("confidence", "low"),
                notes=rec.get(
                    "notes",
                    "Use as a rough guide only. Always check your vehicle plates and handbook."
                ),
            )
            matches.append(info)

    return matches


def debug_list_all() -> list:
    """
    Simple helper so you can manually inspect everything from a Python shell.
    Not used by the API.
    """
    return _load_vehicle_db()
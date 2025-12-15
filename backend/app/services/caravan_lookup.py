from pathlib import Path
from typing import List, Optional

import json
from pydantic import BaseModel


class CaravanInfo(BaseModel):
    """
    Typical towing-related data for a caravan / travel trailer.

    All values are generic or example figures only.
    Users MUST confirm against the actual compliance plate and
    weighbridge figures for their own rig.
    """
    caravan_id: str
    brand: str
    model: str
    variant: Optional[str] = None
    length_category: Optional[str] = None
    country_region: Optional[str] = None

    atm_kg: Optional[float] = None
    tare_kg: Optional[float] = None
    axle_rating_kg: Optional[float] = None
    ball_weight_empty_kg: Optional[float] = None

    typical_ball_loaded_pct_min: Optional[float] = None
    typical_ball_loaded_pct_max: Optional[float] = None

    confidence: str
    notes: Optional[str] = None


def _caravan_data_path() -> Path:
    """
    Return the path to caravans.json inside app/data.
    """
    # This file: backend/app/services/caravan_lookup.py
    # data dir:  backend/app/data/caravans.json
    services_dir = Path(__file__).resolve().parent
    data_dir = services_dir.parent / "data"
    return data_dir / "caravans.json"


def _load_caravan_db() -> List[dict]:
    """
    Load the raw caravan database from JSON.

    Raises FileNotFoundError or json.JSONDecodeError if something is badly wrong,
    which is fine – the API layer can turn that into a 500.
    """
    path = _caravan_data_path()
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    caravans = data.get("caravans", [])
    if not isinstance(caravans, list):
        raise ValueError("Invalid caravans.json format: 'caravans' should be a list")

    return caravans


def debug_list_all() -> List[dict]:
    """
    Debug helper: return the raw list of caravan dicts from the JSON file.

    You can call this from a Python shell to see exactly what's in the DB:
        from app.services.caravan_lookup import debug_list_all
        debug_list_all()
    """
    return _load_caravan_db()


def lookup_caravan(
    brand: str,
    model: str,
    length_category: Optional[str] = None,
) -> List[CaravanInfo]:
    """
    Look up one or more caravans by brand/model, with optional length hint.

    Matching is case-insensitive.
    Length matching is fuzzy:
      - "19ft" matches "19-20 ft"
      - "19" matches "19-20 ft"
      - "19-20ft" matches "19-20 ft"
    """
    brand_q = (brand or "").strip().lower()
    model_q = (model or "").strip().lower()
    length_q = (length_category or "").strip().lower()

    if not brand_q or not model_q:
        return []

    caravans = _load_caravan_db()
    matches: List[CaravanInfo] = []

    for c in caravans:
        c_brand = str(c.get("brand", "")).lower()
        c_model = str(c.get("model", "")).lower()
        c_length_raw = str(c.get("length_category", "")).lower()

        # basic brand/model contains matching
        if brand_q not in c_brand:
            continue
        if model_q not in c_model:
            continue

        # fuzzy length: make both sides number-only for comparison
        if length_q:
            import re
            # e.g. "19ft" -> "19", "19-20 ft" -> "1920"
            wanted_nums = "".join(re.findall(r"\d", length_q))
            have_nums = "".join(re.findall(r"\d", c_length_raw))

            # require that the query digits appear somewhere in the stored digits
            if wanted_nums and wanted_nums not in have_nums:
                continue

        matches.append(
            CaravanInfo(
                caravan_id=c.get("id", ""),
                brand=c.get("brand", ""),
                model=c.get("model", ""),
                variant=c.get("variant"),
                length_category=c.get("length_category"),
                country_region=c.get("country_region"),
                atm_kg=c.get("atm_kg"),
                tare_kg=c.get("tare_kg"),
                axle_rating_kg=c.get("axle_rating_kg"),
                ball_weight_empty_kg=c.get("ball_weight_empty_kg"),
                typical_ball_loaded_pct_min=c.get("typical_ball_loaded_pct_min"),
                typical_ball_loaded_pct_max=c.get("typical_ball_loaded_pct_max"),
                confidence=c.get("confidence", "low"),
                notes=c.get("notes"),
            )
        )

    return matches
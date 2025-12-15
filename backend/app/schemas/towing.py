from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel


class VehicleInput(BaseModel):
    """Basic tow vehicle info supplied by the user or a lookup."""
    label: str  # e.g. "2022 Kia Sportage Diesel AWD"
    tow_rating_braked_kg: Optional[float] = None
    max_ball_weight_kg: Optional[float] = None
    notes: Optional[str] = None


class CaravanInput(BaseModel):
    """Basic caravan / trailer info."""
    label: str  # e.g. "Jayco Journey 19.6"
    atm_kg: Optional[float] = None               # compliance plate ATM
    loaded_estimate_kg: Optional[float] = None   # estimated or weighed
    ball_weight_kg: Optional[float] = None       # measured ball weight
    axle_rating_kg: Optional[float] = None       # axle / chassis rating if known


class MotorhomeInput(BaseModel):
    """Motorhome / campervan weights and axle ratings."""
    label: str
    gvm_kg: Optional[float] = None
    current_weight_kg: Optional[float] = None
    front_axle_rating_kg: Optional[float] = None
    rear_axle_rating_kg: Optional[float] = None
    front_axle_actual_kg: Optional[float] = None
    rear_axle_actual_kg: Optional[float] = None
    rear_overhang_m: Optional[float] = None


class ExtrasInput(BaseModel):
    """Additional load information that affects stability."""
    rear_load_kg: Optional[float] = None
    num_ebikes: Optional[int] = None
    front_storage_heavy: Optional[bool] = None
    water_front_tank_litres: Optional[float] = None
    water_rear_tank_litres: Optional[float] = None
    notes: Optional[str] = None


class TowingCheck(BaseModel):
    item: Literal[
        "tow_rating",
        "ball_weight",
        "axle_rating",
        "rear_load",
        "water_load",
        "combined_mass",
        "front_load",
        "other",
    ]
    status: Literal["ok", "near_limit", "over_limit", "unknown"]
    detail: str


class AdviceBlock(BaseModel):
    summary: str
    detailed: List[str]


class TowingAdvisorRequest(BaseModel):
    """
    Request body for the Touring Brain towing advisor.

    For now, we primarily support rig_type="towed_caravan".
    """
    rig_type: Literal["towed_caravan", "motorhome", "campervan"]

    vehicle: Optional[VehicleInput] = None
    caravan: Optional[CaravanInput] = None
    motorhome: Optional[MotorhomeInput] = None
    extras: Optional[ExtrasInput] = None

    # ---- Optional vehicle lookup hints ----
    use_vehicle_lookup: Optional[bool] = False
    vehicle_make: Optional[str] = None
    vehicle_model: Optional[str] = None
    vehicle_year: Optional[int] = None
    vehicle_variant: Optional[str] = None

    # ---- Optional caravan lookup hints ----
    use_caravan_lookup: Optional[bool] = False
    caravan_brand: Optional[str] = None
    caravan_model: Optional[str] = None
    caravan_length_category: Optional[str] = None


class TowingAdvisorResponse(BaseModel):
    """
    High-level towing / loading guidance for the given rig.
    """
    status: Literal["ok", "near_limits", "over_limits", "unknown"]
    risk_colour: Literal["green", "amber", "red", "grey"]
    ball_weight_percent_of_atm: Optional[float] = None
    ball_weight_percent_of_loaded: Optional[float] = None
    checks: List[TowingCheck]
    advice: AdviceBlock
    inputs_echo: Dict[str, Any]
    disclaimer: str
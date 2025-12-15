from typing import List, Optional

from pydantic import BaseModel


class VehicleInfo(BaseModel):
    vehicle_id: str
    make: str
    model: str
    year_range: str
    variant: str
    country_region: Optional[str] = None
    braked_tow_capacity_kg: Optional[int] = None
    unbraked_tow_capacity_kg: Optional[int] = None
    max_ball_weight_kg: Optional[int] = None
    gvm_kg: Optional[int] = None
    gcm_kg: Optional[int] = None
    confidence: str
    notes: str


class VehicleLookupResponse(BaseModel):
    matches: List[VehicleInfo]
    message: str
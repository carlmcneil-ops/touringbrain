from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.schemas.vehicle import VehicleLookupResponse
from app.services.vehicle_lookup import lookup_vehicle

router = APIRouter(prefix="/vehicle", tags=["vehicle"])


@router.get("/lookup", response_model=VehicleLookupResponse)
def vehicle_lookup(
    make: str = Query(..., description="Vehicle make, e.g. 'Kia'"),
    model: str = Query(..., description="Vehicle model, e.g. 'Sportage'"),
    year: Optional[int] = Query(None, description="Model year, if you know it"),
    variant: Optional[str] = Query(
        None,
        description="Variant, e.g. 'diesel AWD', '3.2 4x4', 'petrol FWD'. Optional but helpful.",
    ),
) -> VehicleLookupResponse:
    """
    Look up towing-related data for a common NZ/AU tow vehicle.

    This is guidance only. Always confirm on the compliance plate,
    handbook, and any official NZTA information.
    """
    try:
        matches = lookup_vehicle(make=make, model=model, year=year, variant=variant)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not matches:
        msg = (
            "No exact match found in the TouringBrain vehicle guide. "
            "Use your compliance plate and handbook to enter tow limits and ball weight manually."
        )
        return VehicleLookupResponse(matches=[], message=msg)

    if len(matches) == 1:
        msg = "Found one likely match. Treat these numbers as a starting point only."
    else:
        msg = (
            "Found a few possible matches. Pick the closest one to your rig, "
            "and always double-check against the plates and handbook."
        )

    return VehicleLookupResponse(matches=matches, message=msg)
from typing import List, Optional

from fastapi import APIRouter, HTTPException

from ...schemas.towing import (
    AdviceBlock,
    CaravanInput,
    ExtrasInput,
    MotorhomeInput,
    TowingAdvisorRequest,
    TowingAdvisorResponse,
    TowingCheck,
    VehicleInput,
)
from ...services.vehicle_lookup import lookup_vehicle
from ...services.caravan_lookup import lookup_caravan

router = APIRouter()


@router.post("/evaluate", response_model=TowingAdvisorResponse)
async def evaluate_towing(payload: TowingAdvisorRequest) -> TowingAdvisorResponse:
    """
    Main entry point for the towing & loading advisor.

    - rig_type="towed_caravan"  -> car + caravan combination
    - rig_type="motorhome"      -> single heavy vehicle, axle and GVM checks
    - rig_type="campervan"      -> treated like motorhome for now
    """
    extras = payload.extras or ExtrasInput()

    # ---- TOWED CARAVAN BRANCH ----
    if payload.rig_type == "towed_caravan":
        vehicle = payload.vehicle
        caravan = payload.caravan

        vehicle_lookup_meta = None
        caravan_lookup_meta = None

        # --- Optional vehicle lookup integration ---
        if payload.use_vehicle_lookup and payload.vehicle_make and payload.vehicle_model:
            try:
                v_matches = lookup_vehicle(
                    make=payload.vehicle_make,
                    model=payload.vehicle_model,
                    year=payload.vehicle_year,
                    variant=payload.vehicle_variant,
                )
            except (FileNotFoundError, ValueError) as e:
                raise HTTPException(status_code=500, detail=f"Vehicle lookup error: {e}")

            if v_matches:
                v = v_matches[0]
                vehicle = VehicleInput(
                    label=f"{v.year_range} {v.make} {v.model}".strip(),
                    tow_rating_braked_kg=v.braked_tow_capacity_kg,
                    max_ball_weight_kg=v.max_ball_weight_kg,
                    notes=v.notes,
                )
                vehicle_lookup_meta = {
                    "used": True,
                    "make": payload.vehicle_make,
                    "model": payload.vehicle_model,
                    "year": payload.vehicle_year,
                    "variant": payload.vehicle_variant,
                    "match_id": v.vehicle_id,
                    "match_confidence": v.confidence,
                }
            else:
                vehicle_lookup_meta = {
                    "used": True,
                    "make": payload.vehicle_make,
                    "model": payload.vehicle_model,
                    "year": payload.vehicle_year,
                    "variant": payload.vehicle_variant,
                    "match_id": None,
                    "match_confidence": "none",
                }

        # --- Optional caravan lookup integration ---
        if payload.use_caravan_lookup and payload.caravan_brand and payload.caravan_model:
            try:
                c_matches = lookup_caravan(
                    brand=payload.caravan_brand,
                    model=payload.caravan_model,
                    length_category=payload.caravan_length_category,
                )
            except (FileNotFoundError, ValueError) as e:
                raise HTTPException(status_code=500, detail=f"Caravan lookup error: {e}")

            if c_matches:
                c = c_matches[0]

                # If no caravan block was provided, build one from lookup
                if caravan is None:
                    caravan = CaravanInput(
                        label=f"{c.brand} {c.model}".strip(),
                        atm_kg=c.atm_kg,
                        loaded_estimate_kg=None,
                        ball_weight_kg=None,
                        axle_rating_kg=c.axle_rating_kg,
                    )
                else:
                    # Only fill in missing fields from lookup
                    if caravan.atm_kg is None:
                        caravan.atm_kg = c.atm_kg
                    if caravan.axle_rating_kg is None:
                        caravan.axle_rating_kg = c.axle_rating_kg

                caravan_lookup_meta = {
                    "used": True,
                    "brand": payload.caravan_brand,
                    "model": payload.caravan_model,
                    "length_category": payload.caravan_length_category,
                    "match_id": c.caravan_id,
                    "match_confidence": c.confidence,
                }
            else:
                caravan_lookup_meta = {
                    "used": True,
                    "brand": payload.caravan_brand,
                    "model": payload.caravan_model,
                    "length_category": payload.caravan_length_category,
                    "match_id": None,
                    "match_confidence": "none",
                }

        # After optional lookups, we must have both blocks
        if vehicle is None or caravan is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    "For 'towed_caravan' you must provide both 'vehicle' and 'caravan' "
                    "blocks, or use the lookup hints so TouringBrain can fill them."
                ),
            )

        response = _evaluate_towed_caravan(
            vehicle=vehicle,
            caravan=caravan,
            extras=extras,
        )

        response.inputs_echo = {
            "rig_type": payload.rig_type,
            "vehicle": vehicle.dict(),
            "caravan": caravan.dict(),
            "motorhome": payload.motorhome.dict() if payload.motorhome else None,
            "extras": extras.dict(),
            "vehicle_lookup": vehicle_lookup_meta,
            "caravan_lookup": caravan_lookup_meta,
        }
        return response

    # ---- MOTORHOME / CAMPERVAN BRANCH ----
    if payload.rig_type in ("motorhome", "campervan"):
        if payload.motorhome is None:
            raise HTTPException(
                status_code=400,
                detail=f"For '{payload.rig_type}' you must provide a 'motorhome' block.",
            )

        response = _evaluate_motorhome(
            motorhome=payload.motorhome,
            extras=extras,
        )

        response.inputs_echo = {
            "rig_type": payload.rig_type,
            "vehicle": payload.vehicle.dict() if payload.vehicle else None,
            "caravan": payload.caravan.dict() if payload.caravan else None,
            "motorhome": payload.motorhome.dict(),
            "extras": extras.dict(),
        }
        return response

    # ---- UNKNOWN RIG TYPE ----
    raise HTTPException(
        status_code=400,
        detail=(
            f"Unsupported rig_type '{payload.rig_type}'. "
            "Use 'towed_caravan', 'motorhome' or 'campervan'."
        ),
    )


def _evaluate_towed_caravan(
    vehicle: VehicleInput,
    caravan: CaravanInput,
    extras: ExtrasInput,
) -> TowingAdvisorResponse:
    """
    Simple first-pass towing logic for a car + caravan combination.
    """
    checks: List[TowingCheck] = []

    tow_check = _check_tow_rating(vehicle, caravan)
    if tow_check is not None:
        checks.append(tow_check)

    ball_check, ball_atm_pct, ball_loaded_pct = _check_ball_weight(caravan, vehicle)
    if ball_check is not None:
        checks.append(ball_check)

    rear_check = _check_rear_load(extras)
    if rear_check is not None:
        checks.append(rear_check)

    front_check = _check_front_load(caravan, vehicle, extras, ball_atm_pct)
    if front_check is not None:
        checks.append(front_check)

    status, colour = _overall_status_and_colour(checks)
    advice = _build_advice(status, checks)

    disclaimer = (
        "This is general guidance only based on the numbers you entered and typical "
        "towing advice. It may not reflect the exact limits of your specific vehicle, "
        "caravan, year or model. Always check your owner’s manuals, compliance plates "
        "and local regulations, and use a certified weighbridge if in doubt."
    )

    return TowingAdvisorResponse(
        status=status,
        risk_colour=colour,
        ball_weight_percent_of_atm=ball_atm_pct,
        ball_weight_percent_of_loaded=ball_loaded_pct,
        checks=checks,
        advice=advice,
        inputs_echo={},  # filled in by evaluate_towing()
        disclaimer=disclaimer,
    )


def _evaluate_motorhome(
    motorhome: MotorhomeInput,
    extras: ExtrasInput,
) -> TowingAdvisorResponse:
    """
    Simple first-pass logic for a motorhome or campervan.
    """
    checks: List[TowingCheck] = []

    if motorhome.gvm_kg is not None and motorhome.current_weight_kg is not None:
        gvm = motorhome.gvm_kg
        actual = motorhome.current_weight_kg

        if actual > gvm:
            checks.append(
                TowingCheck(
                    item="combined_mass",
                    status="over_limit",
                    detail=(
                        f"Your measured motorhome weight ({actual:.0f} kg) appears to be over "
                        f"its GVM ({gvm:.0f} kg). Treat this as a red flag and get proper weights "
                        "and advice before travelling."
                    ),
                )
            )
        elif actual >= 0.9 * gvm:
            checks.append(
                TowingCheck(
                    item="combined_mass",
                    status="near_limit",
                    detail=(
                        f"Your measured motorhome weight ({actual:.0f} kg) is close to its GVM "
                        f"({gvm:.0f} kg). You have very little margin for extra gear, water or "
                        "passengers."
                    ),
                )
            )
        else:
            checks.append(
                TowingCheck(
                    item="combined_mass",
                    status="ok",
                    detail=(
                        f"On the numbers provided, your motorhome weight ({actual:.0f} kg) is "
                        f"under its GVM ({gvm:.0f} kg). Still worth confirming on a weighbridge "
                        "from time to time."
                    ),
                )
            )
    else:
        checks.append(
            TowingCheck(
                item="combined_mass",
                status="unknown",
                detail=(
                    "No usable GVM and current weight provided, so it's not possible to comment "
                    "on how heavily loaded the motorhome is. A certified weighbridge is the best "
                    "way to confirm you're within limits."
                ),
            )
        )

    def _axle_check(
        name: str,
        rating: Optional[float],
        actual: Optional[float],
    ) -> Optional[TowingCheck]:
        if rating is None or actual is None:
            return None
        if actual > rating:
            return TowingCheck(
                item="axle_rating",
                status="over_limit",
                detail=(
                    f"The {name} axle appears to be over its rated load "
                    f"({actual:.0f} kg vs {rating:.0f} kg). This is a red flag for handling, "
                    "tyre life and legal compliance."
                ),
            )
        if actual >= 0.9 * rating:
            return TowingCheck(
                item="axle_rating",
                status="near_limit",
                detail=(
                    f"The {name} axle is close to its rated load "
                    f"({actual:.0f} kg vs {rating:.0f} kg). You have very little margin for "
                    "extra gear at that end of the vehicle."
                ),
            )
        return TowingCheck(
            item="axle_rating",
            status="ok",
            detail=(
                f"The {name} axle load ({actual:.0f} kg) is under its rated limit "
                f"({rating:.0f} kg) on the numbers provided."
            ),
        )

    front_axle_check = _axle_check(
        "front",
        motorhome.front_axle_rating_kg,
        motorhome.front_axle_actual_kg,
    )
    if front_axle_check:
        checks.append(front_axle_check)

    rear_axle_check = _axle_check(
        "rear",
        motorhome.rear_axle_rating_kg,
        motorhome.rear_axle_actual_kg,
    )
    if rear_axle_check:
        checks.append(rear_axle_check)

    rear_load = extras.rear_load_kg or 0.0
    if extras.num_ebikes:
        rear_load += extras.num_ebikes * 27.0

    if motorhome.rear_overhang_m is not None and rear_load > 0:
        if motorhome.rear_overhang_m >= 2.0 and rear_load >= 60:
            checks.append(
                TowingCheck(
                    item="rear_load",
                    status="near_limit",
                    detail=(
                        f"There's a fair amount of weight (around {rear_load:.0f} kg) hanging "
                        f"off the rear with an overhang of about {motorhome.rear_overhang_m:.1f} m. "
                        "This adds a lot of leverage to the rear axle and can affect handling in "
                        "crosswinds or on rough roads."
                    ),
                )
            )
        else:
            checks.append(
                TowingCheck(
                    item="rear_load",
                    status="ok",
                    detail=(
                        f"There's some weight (around {rear_load:.0f} kg) mounted at the rear. "
                        "Even modest rear loads on a motorhome can change how it feels on the road, "
                        "so pay attention to how it drives and adjust if it feels light in the front."
                    ),
                )
            )

    status, colour = _overall_status_and_colour(checks)
    advice = _build_advice(status, checks)

    disclaimer = (
        "This is general guidance only based on the numbers you entered and typical "
        "motorhome loading advice. It may not reflect the exact limits of your specific "
        "chassis, conversion or model. Always check compliance plates, manuals and local "
        "regulations, and use a certified weighbridge if in doubt."
    )

    return TowingAdvisorResponse(
        status=status,
        risk_colour=colour,
        ball_weight_percent_of_atm=None,
        ball_weight_percent_of_loaded=None,
        checks=checks,
        advice=advice,
        inputs_echo={},  # filled in by evaluate_towing()
        disclaimer=disclaimer,
    )


def _check_tow_rating(
    vehicle: VehicleInput,
    caravan: CaravanInput,
) -> Optional[TowingCheck]:
    if vehicle.tow_rating_braked_kg is None:
        return TowingCheck(
            item="tow_rating",
            status="unknown",
            detail=(
                "No braked tow rating provided for the vehicle. Check your handbook or "
                "compliance plate and update these numbers."
            ),
        )

    van_weight = caravan.loaded_estimate_kg or caravan.atm_kg
    if van_weight is None:
        return TowingCheck(
            item="tow_rating",
            status="unknown",
            detail=(
                "No caravan loaded weight or ATM provided, so it's not possible to "
                "compare against your vehicle's tow rating."
            ),
        )

    rating = vehicle.tow_rating_braked_kg
    if van_weight > rating:
        return TowingCheck(
            item="tow_rating",
            status="over_limit",
            detail=(
                f"Your estimated caravan weight ({van_weight:.0f} kg) appears to be over "
                f"your vehicle's braked tow rating ({rating:.0f} kg). Treat this as a red "
                "flag and get proper weights and advice before towing."
            ),
        )

    if van_weight >= 0.9 * rating:
        return TowingCheck(
            item="tow_rating",
            status="near_limit",
            detail=(
                f"Your estimated caravan weight ({van_weight:.0f} kg) is close to your "
                f"vehicle's braked tow rating ({rating:.0f} kg). Allow very little margin "
                "for extra gear and aim to get weighed."
            ),
        )

    return TowingCheck(
        item="tow_rating",
        status="ok",
        detail=(
            f"On the numbers provided, your caravan weight ({van_weight:.0f} kg) is under "
            f"your vehicle's braked tow rating ({rating:.0f} kg). Still worth confirming "
            "with a weighbridge when you can."
        ),
    )


def _check_ball_weight(
    caravan: CaravanInput,
    vehicle: VehicleInput,
) -> (Optional[TowingCheck], Optional[float], Optional[float]):
    ball = caravan.ball_weight_kg
    atm = caravan.atm_kg
    loaded = caravan.loaded_estimate_kg or atm

    ball_atm_pct: Optional[float] = None
    ball_loaded_pct: Optional[float] = None

    if ball is not None and atm is not None and atm > 0:
        ball_atm_pct = (ball / atm) * 100.0

    if ball is not None and loaded is not None and loaded > 0:
        ball_loaded_pct = (ball / loaded) * 100.0

    if ball is None or (ball_atm_pct is None and ball_loaded_pct is None):
        return (
            TowingCheck(
                item="ball_weight",
                status="unknown",
                detail=(
                    "No usable ball weight or caravan weight provided, so it's not "
                    "possible to comment on ball weight percentage. A common rule of "
                    "thumb is around 8–12% of loaded caravan weight on the ball."
                ),
            ),
            ball_atm_pct,
            ball_loaded_pct,
        )

    effective_pct = ball_loaded_pct or ball_atm_pct

    if vehicle.max_ball_weight_kg is not None and ball > vehicle.max_ball_weight_kg:
        return (
            TowingCheck(
                item="ball_weight",
                status="over_limit",
                detail=(
                    f"Measured ball weight ({ball:.0f} kg) appears to be over your "
                    f"towbar/vehicle ball limit ({vehicle.max_ball_weight_kg:.0f} kg). "
                    "This is outside safe and legal guidance — re-check loading and "
                    "weights before towing."
                ),
            ),
            ball_atm_pct,
            ball_loaded_pct,
        )

    if effective_pct is None:
        status = "unknown"
        detail = (
            "Could not compute a reliable ball weight percentage. As a guide, many "
            "setups aim for roughly 8–12% of loaded caravan weight on the ball."
        )
    elif 8.0 <= effective_pct <= 12.0:
        status = "ok"
        detail = (
            f"Ball weight is about {effective_pct:.1f}% of caravan weight, which is "
            "within the common guidance band of around 8–12% for many rigs."
        )
    elif 6.0 <= effective_pct < 8.0 or 12.0 < effective_pct <= 14.0:
        status = "near_limit"
        detail = (
            f"Ball weight is about {effective_pct:.1f}% of caravan weight, which is on "
            "the edge of common guidance. Too low can encourage sway; too high can "
            "overload the towbar and rear axle."
        )
    else:
        status = "over_limit"
        detail = (
            f"Ball weight is about {effective_pct:.1f}% of caravan weight, which is "
            "well outside the common 8–12% guidance band. Very low ball weight often "
            "leads to sway, while very high ball weight can overload the towbar and "
            "rear axle."
        )

    return (
        TowingCheck(
            item="ball_weight",
            status=status,
            detail=detail,
        ),
        ball_atm_pct,
        ball_loaded_pct,
    )


def _check_rear_load(extras: ExtrasInput) -> Optional[TowingCheck]:
    rear_load = extras.rear_load_kg or 0.0
    if extras.num_ebikes:
        rear_load += extras.num_ebikes * 27.0

    if rear_load <= 0:
        return None

    if rear_load >= 100:
        status = "over_limit"
        detail = (
            f"There's a lot of weight hanging off the rear of the caravan (roughly "
            f"{rear_load:.0f} kg including bikes and racks). Heavy rear loads reduce "
            "effective ball weight and can make sway much more likely, especially in "
            "crosswinds or emergency manoeuvres."
        )
    elif rear_load >= 50:
        status = "near_limit"
        detail = (
            f"There's a significant amount of weight on the rear of the caravan "
            f"(around {rear_load:.0f} kg). Rear-mounted bikes and boxes tend to reduce "
            "effective ball weight and increase sway risk."
        )
    else:
        status = "ok"
        detail = (
            f"There's some weight on the rear of the caravan (about {rear_load:.0f} kg). "
            "Even modest rear loads can affect stability, so it's still worth checking "
            "ball weight and how the rig feels on the road."
        )

    return TowingCheck(
        item="rear_load",
        status=status,
        detail=detail,
    )


def _check_front_load(
    caravan: CaravanInput,
    vehicle: VehicleInput,
    extras: ExtrasInput,
    ball_atm_pct: Optional[float],
) -> Optional[TowingCheck]:
    """
    Comment on extra load towards the front of the van / A-frame.

    We treat 'front_storage_heavy' plus the numeric front load value as a signal
    that there's meaningful mass sitting forward of the axle (toolboxes, gas bottles,
    generators, bikes on the drawbar, etc.).
    """
    has_front_storage = bool(extras.front_storage_heavy)
    front_extra = extras.water_front_tank_litres or 0.0  # reused as "front extra kg"

    # If there's nothing meaningful flagged at the front, stay quiet.
    if not has_front_storage and front_extra <= 0:
        return None

    extra_mass_front = front_extra

    status = "unknown"
    reasons = []

    ball = caravan.ball_weight_kg
    ball_limit = vehicle.max_ball_weight_kg

    # Basic status based on ball limit / percentage if we have it
    if ball is not None and ball_limit is not None and ball > ball_limit:
        status = "over_limit"
        reasons.append(
            f"Measured ball weight ({ball:.0f} kg) already appears to exceed your "
            f"towbar/vehicle ball limit ({ball_limit:.0f} kg)."
        )
    elif ball_atm_pct is not None and ball_atm_pct > 12.0:
        status = "near_limit"
        reasons.append(
            f"Ball weight is already on the high side at about {ball_atm_pct:.1f}% of ATM. "
            "Extra weight at the front tends to push this even higher."
        )
    else:
        status = "near_limit"
        reasons.append(
            "Extra load mounted towards the front of the van tends to increase ball weight "
            "and put more load into the towbar and rear axle."
        )

    if extra_mass_front > 0:
        reasons.append(
            f"There's roughly {extra_mass_front:.0f} kg of additional gear mounted towards the front."
        )

    detail = (
        " ".join(reasons)
        + " Extra mass at the front (toolboxes, gas bottles, generators, bikes on the drawbar) "
        "increases ball weight and loads up the towbar and rear axle. "
        "If the ball weight is already on the high side, adding more at the front can push the setup "
        "outside safe limits. Always re-check ball weight after adding or moving front-mounted gear."
    )

    return TowingCheck(
        item="front_load",
        status=status,
        detail=detail,
    )


def _overall_status_and_colour(checks: List[TowingCheck]) -> (str, str):
    if not checks:
        return "unknown", "grey"

    has_over = any(c.status == "over_limit" for c in checks)
    has_near = any(c.status == "near_limit" for c in checks)
    has_ok = any(c.status == "ok" for c in checks)

    if has_over:
        return "over_limits", "red"
    if has_near:
        return "near_limits", "amber"
    if has_ok:
        return "ok", "green"

    return "unknown", "grey"


def _build_advice(status: str, checks: List[TowingCheck]) -> AdviceBlock:
    if status == "over_limits":
        summary = (
            "On the numbers you've given, this setup should be treated as a red flag "
            "until you've confirmed actual weights and limits."
        )
    elif status == "near_limits":
        summary = (
            "You're close to common limits in a few areas. Treat this as a caution and "
            "double-check weights before long trips or challenging routes."
        )
    elif status == "ok":
        summary = (
            "On the numbers you've given, your setup looks broadly within common "
            "guidance, but it's still worth confirming with a weighbridge."
        )
    else:
        summary = (
            "There wasn't enough information to give a firm view. Providing tow "
            "ratings, ball weight and caravan weight will improve this advice."
        )

    detailed = [c.detail for c in checks]

    if status in ("over_limits", "near_limits"):
        detailed.append(
            "Before travelling long distances, get weights measured on a certified "
            "weighbridge and review your manufacturer's limits. Consider shifting heavy "
            "items forward or redistributing load where appropriate."
        )

    return AdviceBlock(summary=summary, detailed=detailed)
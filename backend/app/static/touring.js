// app/static/towing.js
// Simple front-end for the Touring Brain towing advisor.

function numberOrNull(value) {
  if (value === undefined || value === null) return null;
  const trimmed = String(value).trim();
  if (trimmed === "") return null;
  const n = parseFloat(trimmed);
  return Number.isNaN(n) ? null : n;
}

async function callTowingAdvisor(payload) {
  const res = await fetch("/towing/evaluate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Backend error (${res.status}): ${text}`);
  }

  return res.json();
}

function applyResultToUI(result) {
  const card = document.getElementById("result-card");
  const statusPill = document.getElementById("status-pill");
  const adviceSummary = document.getElementById("advice-summary");
  const checksList = document.getElementById("checks-list");
  const disclaimerText = document.getElementById("disclaimer-text");

  if (!card || !statusPill || !adviceSummary || !checksList || !disclaimerText) return;

  // Status pill
  const colour = result.risk_colour || "grey";
  const status = result.status || "unknown";

  statusPill.className = ""; // reset
  statusPill.classList.add("status-pill", `status-${colour}`);
  statusPill.textContent = status.replace("_", " ");

  // Summary
  adviceSummary.textContent = result.advice?.summary || "";

  // Checks
  checksList.innerHTML = "";
  if (Array.isArray(result.checks)) {
    result.checks.forEach((c) => {
      const li = document.createElement("li");
      li.textContent = c.detail;
      checksList.appendChild(li);
    });
  }

  // Disclaimer from backend + our safety card sits underneath
  disclaimerText.textContent = result.disclaimer || "";

  card.style.display = "block";
}

// ---- VEHICLE LOOKUP ----

async function handleVehiclePresetChange(ev) {
  const preset = ev.target.value;
  const hintEl = document.getElementById("vehicle_guide_hint");
  const labelEl = document.getElementById("vehicle_label");
  const towRatingEl = document.getElementById("tow_rating");
  const ballLimitEl = document.getElementById("ball_limit");

  if (hintEl) hintEl.textContent = "";

  if (!preset) {
    return;
  }

  // Map preset ID -> lookup parameters
  let make, model, year, variant;
  switch (preset) {
    case "kia_sportage_2022":
      make = "Kia";
      model = "Sportage";
      year = 2022;
      variant = "diesel";
      break;
    case "toyota_hilux_4x4":
      make = "Toyota";
      model = "Hilux";
      year = 2020;
      variant = "diesel 4x4";
      break;
    case "ford_ranger_4x4":
      make = "Ford";
      model = "Ranger";
      year = 2022;
      variant = "diesel 4x4";
      break;
    case "isuzu_dmax_4x4":
      make = "Isuzu";
      model = "D-MAX";
      year = 2022;
      variant = "diesel 4x4";
      break;
    case "generic_medium_suv":
      make = "Generic";
      model = "Medium SUV Diesel";
      year = 2022;
      variant = "";
      break;
    default:
      return;
  }

  try {
    const params = new URLSearchParams({
      make,
      model,
    });
    if (year) params.append("year", String(year));
    if (variant) params.append("variant", variant);

    const res = await fetch(`/vehicle/lookup?${params.toString()}`, {
      method: "GET",
      headers: { Accept: "application/json" },
    });

    if (!res.ok) {
      throw new Error(`lookup failed (${res.status})`);
    }

    const data = await res.json();
    const match = Array.isArray(data.matches) && data.matches.length > 0 ? data.matches[0] : null;
    if (!match) {
      if (hintEl) {
        hintEl.textContent =
          "We couldn't find a guide entry for that preset. Enter your tow rating and ball limit from the plates instead.";
      }
      return;
    }

    if (labelEl) {
      labelEl.value = `${match.year_range || ""} ${match.make} ${match.model}`.trim();
    }
    if (towRatingEl && match.braked_tow_capacity_kg != null) {
      towRatingEl.value = String(match.braked_tow_capacity_kg);
    }
    if (ballLimitEl && match.max_ball_weight_kg != null) {
      ballLimitEl.value = String(match.max_ball_weight_kg);
    }

    if (hintEl) {
      hintEl.textContent =
        "Guide tow rating and ball limit filled from TouringBrain data. Your own plates and handbook always win.";
    }
  } catch (err) {
    if (hintEl) {
      hintEl.textContent = "Vehicle lookup failed – enter tow rating and ball limit manually.";
    }
    console.error(err);
  }
}

// ---- CARAVAN LOOKUP ----

async function handleCaravanPresetChange(ev) {
  const preset = ev.target.value;
  const hintEl = document.getElementById("caravan_guide_hint");
  const labelEl = document.getElementById("caravan_label");
  const atmEl = document.getElementById("atm");
  const loadedEl = document.getElementById("loaded");

  const explTare = document.getElementById("expl_tare");
  const explAtm = document.getElementById("expl_atm");
  const explLoaded = document.getElementById("expl_loaded_hint");
  const explBallBand = document.getElementById("expl_ball_band");

  if (hintEl) hintEl.textContent = "";

  if (!preset) {
    // Clear explainer numbers when user deselects
    if (explTare) explTare.textContent = "–";
    if (explAtm) explAtm.textContent = "–";
    if (explLoaded) explLoaded.textContent = "–";
    if (explBallBand) explBallBand.textContent = "–";
    return;
  }

  // Map preset -> lookup params
  let brand, model, lengthCategory;
  switch (preset) {
    case "jayco_journey_19":
      brand = "Jayco";
      model = "Journey";
      lengthCategory = "19ft";
      break;
    case "jayco_expanda_17":
      brand = "Jayco";
      model = "Expanda";
      lengthCategory = "17ft";
      break;
    case "generic_single_16":
      brand = "Generic";
      model = "Mid-size single axle";
      lengthCategory = "16ft";
      break;
    case "generic_tandem_21":
      brand = "Generic";
      model = "Large tandem tourer";
      lengthCategory = "21ft";
      break;
    case "generic_offroad_19":
      brand = "Generic";
      model = "Off-road 19ft";
      lengthCategory = "19ft";
      break;
    default:
      return;
  }

  try {
    const params = new URLSearchParams({
      brand,
      model,
    });
    if (lengthCategory) params.append("length_category", lengthCategory);

    const res = await fetch(`/caravan/lookup?${params.toString()}`, {
      method: "GET",
      headers: { Accept: "application/json" },
    });

    if (!res.ok) {
      throw new Error(`lookup failed (${res.status})`);
    }

    const data = await res.json();
    const match =
      Array.isArray(data.matches) && data.matches.length > 0 ? data.matches[0] : null;
    if (!match) {
      if (hintEl) {
        hintEl.textContent =
          "We couldn't find a guide entry for that caravan. Use your actual plate figures instead.";
      }
      return;
    }

    if (labelEl) {
      labelEl.value = `${match.brand} ${match.model}`.trim();
    }
    if (atmEl && match.atm_kg != null) {
      atmEl.value = String(match.atm_kg);
    }

    // Simple guess for "loaded" as a starting point: a bit under ATM
    if (loadedEl && match.atm_kg != null) {
      const loadedGuess = Math.round(match.atm_kg * 0.9);
      loadedEl.value = String(loadedGuess);
    }

    // Fill explainer table
    if (explTare && match.tare_kg != null) {
      explTare.textContent = `${match.tare_kg}`;
    } else if (explTare) {
      explTare.textContent = "–";
    }

    if (explAtm && match.atm_kg != null) {
      explAtm.textContent = `${match.atm_kg}`;
    } else if (explAtm) {
      explAtm.textContent = "–";
    }

    if (explLoaded && match.atm_kg != null) {
      const loadedGuess = Math.round(match.atm_kg * 0.9);
      explLoaded.textContent = `${loadedGuess} (rough touring guess)`;
    } else if (explLoaded) {
      explLoaded.textContent = "–";
    }

    if (explBallBand) {
      const minPct = match.typical_ball_loaded_pct_min ?? 8;
      const maxPct = match.typical_ball_loaded_pct_max ?? 12;
      explBallBand.textContent = `${minPct}–${maxPct}% of loaded weight (guide only)`;
    }

    if (hintEl) {
      hintEl.textContent =
        "Guide ATM / tare filled from TouringBrain data. Always check against your actual caravan plate and weighbridge slips.";
    }
  } catch (err) {
    if (hintEl) {
      hintEl.textContent =
        "Caravan lookup failed – enter ATM and loaded weight from your own plate and weighbridge.";
    }
    console.error(err);
  }
}

// ---- FORM SUBMIT ----

async function handleFormSubmit(ev) {
  ev.preventDefault();

  const statusText = document.getElementById("status-text");
  if (statusText) {
    statusText.textContent = "Checking your setup…";
  }

  const vehicleLabel = document.getElementById("vehicle_label");
  const caravanLabel = document.getElementById("caravan_label");
  const towRatingEl = document.getElementById("tow_rating");
  const ballLimitEl = document.getElementById("ball_limit");
  const atmEl = document.getElementById("atm");
  const loadedEl = document.getElementById("loaded");
  const ballWeightEl = document.getElementById("ball_weight");
  const rearLoadEl = document.getElementById("rear_load");
  const numEbikesEl = document.getElementById("num_ebikes");

  const payload = {
    rig_type: "towed_caravan",
    vehicle: {
      label: vehicleLabel ? vehicleLabel.value.trim() : "",
      tow_rating_braked_kg: numberOrNull(towRatingEl?.value),
      max_ball_weight_kg: numberOrNull(ballLimitEl?.value),
      notes: null,
    },
    caravan: {
      label: caravanLabel ? caravanLabel.value.trim() : "",
      atm_kg: numberOrNull(atmEl?.value),
      loaded_estimate_kg: numberOrNull(loadedEl?.value),
      ball_weight_kg: numberOrNull(ballWeightEl?.value),
      axle_rating_kg: null,
    },
    motorhome: null,
    extras: {
      rear_load_kg: numberOrNull(rearLoadEl?.value),
      num_ebikes: numberOrNull(numEbikesEl?.value),
      front_storage_heavy: null,
      water_front_tank_litres: null,
      water_rear_tank_litres: null,
      notes: null,
    },
  };

  try {
    const result = await callTowingAdvisor(payload);
    applyResultToUI(result);
    if (statusText) {
      statusText.textContent = "";
    }
  } catch (err) {
    console.error(err);
    if (statusText) {
      statusText.textContent = "Something went wrong talking to the backend – try again.";
    }
  }
}

// ---- BOOTSTRAP ----

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("towing-form");
  if (form) {
    form.addEventListener("submit", handleFormSubmit);
  }

  const vehiclePreset = document.getElementById("vehicle_preset");
  if (vehiclePreset) {
    vehiclePreset.addEventListener("change", handleVehiclePresetChange);
  }

  const caravanPreset = document.getElementById("caravan_preset");
  if (caravanPreset) {
    caravanPreset.addEventListener("change", handleCaravanPresetChange);
  }
});
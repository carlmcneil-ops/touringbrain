console.log("✅ LIVE towing.js loaded —", new Date().toISOString());
// static/towing.js
// TouringBrain — Towing & loading (clean rewrite)
//
// Locked spec implemented:
// 1) Front-load bands (single vs tandem +10kg; unknown => single)
// 2) Front-load modifies ball-weight status (bump ladder; critical forces OVER)
// 3) Overall severity = worst of (combined ball/front) + rear + backend checks
// 4) Rig orientation based on imbalance location only (front vs rear), not global severity
// 5) Rear-load severity is length-sensitive (short/medium/long)
//
// PLUS (rig images):
// - Utes => ute-*
// - Big wagons => large-suv-* (except Defender preset => defender-*)
// - SUVs => small-suv-*
// - No preset => defender-*
// - Axle: single => single-rig; tandem/unknown => twin-rig
// - Orientation: nose_heavy / nose_light / level => nose-heavy / nose-light / nose-level
// - Ghost rig: defender-twin-rig-nose-level
// - Handles defender typo file: defender-single-rig-nose-evel fallback
//
// Form behaviour:
// - Native required-field flags via checkValidity + reportValidity (NO double wiring)
// - Prevents double submit with a simple lock that ALWAYS clears (success/fail)

// ---------------------------
// Vehicle presets
// ---------------------------
const VEHICLE_PRESETS = {
  // Utes
  ford_ranger: { label: "Ford Ranger", tow_rating_kg: 3500, ball_limit_kg: 350 },
  toyota_hilux: { label: "Toyota Hilux", tow_rating_kg: 3500, ball_limit_kg: 350 },
  mitsubishi_triton: { label: "Mitsubishi Triton", tow_rating_kg: 3100, ball_limit_kg: 310 },
  nissan_navara: { label: "Nissan Navara", tow_rating_kg: 3500, ball_limit_kg: 350 },
  isuzu_dmax: { label: "Isuzu D-MAX", tow_rating_kg: 3500, ball_limit_kg: 350 },
  mazda_bt50: { label: "Mazda BT-50", tow_rating_kg: 3500, ball_limit_kg: 350 },
  vw_amarok: { label: "VW Amarok", tow_rating_kg: 3500, ball_limit_kg: 350 },
  byd_shark: { label: "BYD Shark (guide)", tow_rating_kg: 2500, ball_limit_kg: 150 },

  // Big wagons
  landcruiser_200_300: { label: "Toyota Land Cruiser 200/300", tow_rating_kg: 3500, ball_limit_kg: 350 },
  prado: { label: "Land Cruiser Prado", tow_rating_kg: 3000, ball_limit_kg: 300 },
  discovery_5: { label: "Land Rover Discovery 5", tow_rating_kg: 3500, ball_limit_kg: 350 },
  defender_110: { label: "Land Rover Defender 110", tow_rating_kg: 3500, ball_limit_kg: 350 },
  range_rover: { label: "Range Rover", tow_rating_kg: 3500, ball_limit_kg: 350 },
  ford_everest: { label: "Ford Everest", tow_rating_kg: 3500, ball_limit_kg: 350 },

  // SUVs
  rav4: { label: "Toyota RAV4 (guide)", tow_rating_kg: 1500, ball_limit_kg: 150 },
  outlander: { label: "Mitsubishi Outlander (guide)", tow_rating_kg: 1600, ball_limit_kg: 160 },
  sportage_diesel: { label: "Kia Sportage (guide)", tow_rating_kg: 1900, ball_limit_kg: 100 },
  cx5: { label: "Mazda CX-5 (guide)", tow_rating_kg: 1800, ball_limit_kg: 150 },
  tucson: { label: "Hyundai Tucson (guide)", tow_rating_kg: 1650, ball_limit_kg: 100 },
  seltos: { label: "Kia Seltos (guide)", tow_rating_kg: 1500, ball_limit_kg: 100 },
  xtrail: { label: "Nissan X-Trail (guide)", tow_rating_kg: 1600, ball_limit_kg: 160 },
  forester: { label: "Subaru Forester (guide)", tow_rating_kg: 1800, ball_limit_kg: 180 },
  medium_suv_generic: { label: "Generic medium SUV (guide)", tow_rating_kg: 1800, ball_limit_kg: 150 },
};

// ---------------------------
// Tiny DOM helpers
// ---------------------------
function $(id) {
  return document.getElementById(id);
}

function parseNumber(value) {
  if (value === null || value === undefined) return null;
  const n = parseFloat(String(value).trim());
  return Number.isNaN(n) ? null : n;
}

function formatKg(n) {
  if (n == null || !Number.isFinite(n)) return "–";
  return Math.round(n).toLocaleString("en-NZ");
}

// ---------------------------
// Shared status model (UI + aggregation)
// ok / near_limit / over_limit
// ---------------------------
function normalizeStatus(raw) {
  const s = (raw || "").toLowerCase();
  if (!s) return "unknown";
  if (s.includes("over")) return "over_limit";
  if (s.includes("near")) return "near_limit";
  if (s.includes("ok") || s.includes("within") || s.includes("green")) return "ok";
  return "unknown";
}

function statusRank(status) {
  const s = normalizeStatus(status);
  if (s === "ok") return 1;
  if (s === "near_limit") return 2;
  if (s === "over_limit") return 3;
  return 0;
}

function worstStatus(a, b) {
  return statusRank(a) >= statusRank(b) ? normalizeStatus(a) : normalizeStatus(b);
}

function niceStatusLabel(status) {
  const s = normalizeStatus(status);
  if (s === "ok") return "Within guide limits";
  if (s === "near_limit") return "Near limits";
  if (s === "over_limit") return "Over limits";
  return "No data";
}

// ---------------------------
// Form helpers
// ---------------------------
function getTowbarType() {
  const el = $("towbar_type");
  const v = (el?.value || "").toLowerCase();
  if (!v) return "unknown";
  if (v === "fixed") return "fixed";
  if (v === "detachable") return "detachable";
  if (v === "not_sure" || v === "unknown") return "not_sure";
  return "unknown";
}

function getAxleConfig() {
  const el = $("axle_config");
  const v = (el?.value || "").toLowerCase();
  if (v === "single") return "single";
  if (v === "tandem") return "tandem";
  return "unknown";
}

function getLengthFt() {
  const v = parseNumber($("caravan_length_m")?.value); // legacy id; label is ft
  if (v && v > 0) return v;
  return null;
}

// ---------------------------
// Quick guide UI updater (SINGLE source of truth)
// ---------------------------
function updateQuickGuideFromForm() {
  const tareKg = parseNumber($("caravan_tare")?.value);
  const atmKg = parseNumber($("caravan_atm")?.value);
  const loadedKg = parseNumber($("caravan_loaded")?.value);
  const ballKg = parseNumber($("caravan_ball")?.value);
  const caravanLabel = ($("caravan_label")?.value || "").trim();

  const setText = (id, text) => {
    const el = $(id);
    if (el) el.textContent = text;
  };

  // Optional: update the quick guide title if you've got an element for it.
  // (Won't break anything if it doesn't exist.)
  const titleEl = $("quick-guide-title") || $("quick-guide-heading");
  if (titleEl) {
    titleEl.textContent = caravanLabel ? `${caravanLabel} — Caravan weights – quick guide` : "Caravan weights – quick guide";
  }

  setText("expl_tare", formatKg(tareKg));
  setText("expl_atm", formatKg(atmKg));
  setText("expl_loaded_hint", formatKg(loadedKg));

  // Typical ball band: 8–12% of loaded (if loaded exists)
  if (loadedKg && loadedKg > 0) {
    const low = loadedKg * 0.08;
    const high = loadedKg * 0.12;
    setText("expl_ball_band", `${formatKg(low)}–${formatKg(high)} kg (8–12%)`);
  } else {
    setText("expl_ball_band", "–");
  }

  // Your ball weight (if known)
  if (loadedKg && loadedKg > 0 && ballKg && ballKg > 0) {
    const pct = (ballKg / loadedKg) * 100;
    setText("expl_ball_pct", `${formatKg(ballKg)} kg (${pct.toFixed(1)}%)`);
    setText("expl_ball_comment", "Your measured ball weight as a percentage of loaded travel weight.");
  } else if (ballKg && ballKg > 0) {
    setText("expl_ball_pct", `${formatKg(ballKg)} kg`);
    setText("expl_ball_comment", "Add a loaded travel weight to see your percentage.");
  } else {
    setText("expl_ball_pct", "–");
    setText("expl_ball_comment", "Add a measured ball weight to see your percentage.");
  }
}

// ---------------------------
// 1) Front-load thresholds (LOCKED)
// ---------------------------
function computeFrontLoadStatus(frontKg, axleConfig) {
  const axle = axleConfig === "tandem" ? "tandem" : "single"; // unknown => single (safer)

  if (frontKg == null || frontKg <= 0) return { band: "ok", uiStatus: "ok", rank: 0 };

  if (axle === "single") {
    // 0–20 OK, 21–40 Amber, 41–80 Red, >80 Critical
    if (frontKg > 80) return { band: "critical", uiStatus: "over_limit", rank: 3 };
    if (frontKg >= 41) return { band: "red", uiStatus: "over_limit", rank: 2 };
    if (frontKg >= 21) return { band: "amber", uiStatus: "near_limit", rank: 1 };
    return { band: "ok", uiStatus: "ok", rank: 0 };
  }

  // tandem (+10kg allowance)
  // 0–30 OK, 31–50 Amber, 51–90 Red, >90 Critical
  if (frontKg > 90) return { band: "critical", uiStatus: "over_limit", rank: 3 };
  if (frontKg >= 51) return { band: "red", uiStatus: "over_limit", rank: 2 };
  if (frontKg >= 31) return { band: "amber", uiStatus: "near_limit", rank: 1 };
  return { band: "ok", uiStatus: "ok", rank: 0 };
}

// ---------------------------
// Rear-load severity (LOCKED — length-sensitive)
// ---------------------------
function computeRearLoadStatus(rearKg, lengthFt) {
  if (rearKg == null || rearKg <= 0) return { band: "ok", uiStatus: "ok", rank: 0, bucket: "medium" };

  const len = lengthFt == null ? null : lengthFt;
  let bucket = "medium";
  if (len != null && len <= 18) bucket = "short";
  else if (len != null && len >= 24) bucket = "long";

  if (bucket === "short") {
    // 0–24 ok, 25–49 amber, >=50 red
    if (rearKg >= 50) return { band: "red", uiStatus: "over_limit", rank: 2, bucket };
    if (rearKg >= 25) return { band: "amber", uiStatus: "near_limit", rank: 1, bucket };
    return { band: "ok", uiStatus: "ok", rank: 0, bucket };
  }

  if (bucket === "long") {
    // 0–14 ok, 15–29 amber, >=30 red
    if (rearKg >= 30) return { band: "red", uiStatus: "over_limit", rank: 2, bucket };
    if (rearKg >= 15) return { band: "amber", uiStatus: "near_limit", rank: 1, bucket };
    return { band: "ok", uiStatus: "ok", rank: 0, bucket };
  }

  // medium (18–23ft): 0–19 ok, 20–39 amber, >=40 red
  if (rearKg >= 40) return { band: "red", uiStatus: "over_limit", rank: 2, bucket };
  if (rearKg >= 20) return { band: "amber", uiStatus: "near_limit", rank: 1, bucket };
  return { band: "ok", uiStatus: "ok", rank: 0, bucket };
}

// ---------------------------
// Ball-weight status (distribution slices only; do not add to mass)
// ---------------------------
function computeBallStatus(inputs) {
  const { loadedKg, measuredBallKg, ballLimitKg, towbarType, axleConfig, lengthFt, frontKg, rearKg } = inputs;

  if (!loadedKg || loadedKg <= 0) {
    return { status: "unknown", estimatedBallKg: null, percent: null, effectiveBallLimitKg: null };
  }

  // Effective ball limit by towbar type
  let effectiveLimit = ballLimitKg && ballLimitKg > 0 ? ballLimitKg : null;
  if (effectiveLimit != null) {
    if (towbarType === "detachable") effectiveLimit = Math.round(effectiveLimit * 0.75);
    if (towbarType === "not_sure") effectiveLimit = Math.round(effectiveLimit * 0.70);
  }

  // Base % bands (guide)
  let baseLowPct = axleConfig === "single" ? 9.0 : 8.0;
  let baseHighPct = axleConfig === "single" ? 13.0 : 12.0;

  if (axleConfig === "single" && lengthFt != null && lengthFt >= 21) {
    baseLowPct += 0.5;
    baseHighPct -= 0.5;
  }

  // Measured ball wins; else estimate at ~10%
  let ballKg = measuredBallKg != null ? measuredBallKg : loadedKg * 0.10;

  // Distribution influence (guide-level)
  let lengthFactor = 1.0;
  if (lengthFt != null) {
    if (lengthFt >= 24) lengthFactor = 1.15;
    else if (lengthFt >= 20) lengthFactor = 1.08;
    else if (lengthFt <= 17) lengthFactor = 0.95;
  }

  let frontFactor = 0.8 * lengthFactor;
  let rearFactor = 0.45 * lengthFactor;

  if (axleConfig === "tandem") {
    frontFactor = 0.55 * lengthFactor;
    rearFactor = 0.35 * lengthFactor;
  }

  const f = frontKg && frontKg > 0 ? frontKg : 0;
  const r = rearKg && rearKg > 0 ? rearKg : 0;

  ballKg = ballKg + f * frontFactor - r * rearFactor;
  if (ballKg < 0) ballKg = 0;

  const pct = (ballKg / loadedKg) * 100;

  let status = "ok";

  const heavyAmberPct = towbarType === "fixed" ? baseHighPct : baseHighPct - 1.0;
  const heavyRedPct = towbarType === "fixed" ? baseHighPct + 1.5 : baseHighPct + 0.5;

  if ((effectiveLimit != null && ballKg > effectiveLimit) || pct > heavyRedPct) {
    status = "over_limit";
  } else if ((effectiveLimit != null && ballKg >= effectiveLimit * 0.9) || pct >= heavyAmberPct) {
    status = "near_limit";
  }

  // Light side (tail-heavy feel)
  if (status !== "over_limit") {
    let lightAmberPct = Math.max(6.5, baseLowPct - 2.0);
    let lightRedPct = Math.max(5.0, baseLowPct - 3.5);

    if (axleConfig === "single" && lengthFt != null && lengthFt >= 21) {
      lightAmberPct += 0.5;
      lightRedPct += 0.5;
    }

    if (pct < lightRedPct) status = "over_limit";
    else if (pct < lightAmberPct && status === "ok") status = "near_limit";
  }

  return { status, estimatedBallKg: ballKg, percent: pct, effectiveBallLimitKg: effectiveLimit };
}

// ---------------------------
// 2) Front-load modifies ball-weight status (LOCKED)
// ---------------------------
function combineLoadAndBallStatus(ballStatus, frontBand) {
  const b = normalizeStatus(ballStatus);

  if (frontBand === "ok") return b;

  if (frontBand === "amber") {
    if (b === "ok") return "near_limit";
    return b;
  }

  if (frontBand === "red") {
    if (b === "ok") return "near_limit";
    if (b === "near_limit") return "over_limit";
    return b;
  }

  // critical
  return "over_limit";
}

// ---------------------------
// 3) Overall severity (LOCKED)
// ---------------------------
function computeOverallStatus(backendData, combinedBallFrontStatus, rearStatus, distributionStatus) {
  let worst = "unknown";

  worst = worstStatus(worst, normalizeStatus(backendData?.status));

  const checks = Array.isArray(backendData?.checks) ? backendData.checks : [];
  for (const c of checks) worst = worstStatus(worst, normalizeStatus(c?.status));

  worst = worstStatus(worst, combinedBallFrontStatus);
  worst = worstStatus(worst, rearStatus);
  worst = worstStatus(worst, distributionStatus);

  let risk_colour = "grey";
  if (worst === "ok") risk_colour = "green";
  else if (worst === "near_limit") risk_colour = "amber";
  else if (worst === "over_limit") risk_colour = "red";

  return { status: worst, risk_colour };
}

// ---------------------------
// 4) Rig orientation (LOCKED)
// ---------------------------
function getRigOrientation(frontRank, rearRank, overallStatus) {
  const overall = normalizeStatus(overallStatus);

  let orientation = "level";
  if (rearRank > frontRank && rearRank >= 1) orientation = "nose_light";
  else if (frontRank >= rearRank && frontRank >= 1) orientation = "nose_heavy";

  const showBadge = orientation !== "level" && overall === "over_limit";
  return { orientation, showBadge };
}

// ---------------------------
// UI — pill, checks, rig
// ---------------------------
function setStatusPill(status, riskColour) {
  const pill = $("towing-status-pill");
  if (!pill) return;

  pill.className = "tb-status-pill";

  let colourClass = "tb-status-pill--grey";
  let label = "Not checked yet";

  const keyColour = (riskColour || "").toLowerCase();
  const keyStatus = normalizeStatus(status);

  if (keyColour === "green" || keyStatus === "ok") {
    colourClass = "tb-status-pill--green";
    label = "Within guide limits";
  } else if (keyColour === "amber" || keyStatus === "near_limit") {
    colourClass = "tb-status-pill--amber";
    label = "Near limits";
  } else if (keyColour === "red" || keyStatus === "over_limit") {
    colourClass = "tb-status-pill--red";
    label = "Over limits";
  }

  pill.classList.add(colourClass);
  pill.textContent = label;

  const riskLabel = $("towing-risk-label");
  if (riskLabel) {
    riskLabel.textContent = keyStatus === "unknown" ? "" : `Status: ${niceStatusLabel(keyStatus)}`;
  }
}

function niceCheckLabel(item) {
  switch (item) {
    case "tow_rating":
      return "Tow rating vs van weight";
    case "atm":
      return "Van plate ATM vs loaded";
    case "ball_weight":
      return "Ball weight";
    case "rear_load":
      return "Weight hanging off the rear";
    case "front_load":
      return "Weight on the front";
    case "distribution":
      return "Load distribution sanity check";
    default:
      return "Other";
  }
}

function statusBadgeClass(status) {
  const s = normalizeStatus(status);
  if (s === "ok") return "tb-check-status tb-check-status--ok";
  if (s === "near_limit") return "tb-check-status tb-check-status--amber";
  if (s === "over_limit") return "tb-check-status tb-check-status--red";
  return "tb-check-status tb-check-status--unknown";
}

function renderChecks(params) {
  const { backendChecks, towRatingStatus, atmStatus, ballStatus, frontStatus, rearStatus, distributionStatus, distributionDetail } =
    params;

  const list = $("towing-checks-list");
  if (!list) return;

  list.innerHTML = "";

  const checks = [];
  checks.push({ item: "tow_rating", status: towRatingStatus.status, detail: towRatingStatus.detail });
  checks.push({ item: "atm", status: atmStatus.status, detail: atmStatus.detail });
  checks.push({ item: "ball_weight", status: ballStatus.status, detail: ballStatus.detail });
  checks.push({ item: "front_load", status: frontStatus.status, detail: frontStatus.detail });
  checks.push({ item: "rear_load", status: rearStatus.status, detail: rearStatus.detail });

  if (distributionDetail) checks.push({ item: "distribution", status: distributionStatus, detail: distributionDetail });

  if (Array.isArray(backendChecks)) {
    for (const c of backendChecks) {
      const item = c?.item;
      if (!item) continue;
      if (["tow_rating", "ball_weight", "front_load", "rear_load", "atm"].includes(item)) continue;
      checks.push({ item, status: normalizeStatus(c?.status), detail: c?.detail || "" });
    }
  }

  for (const check of checks) {
    const li = document.createElement("li");
    li.className = "tb-check-item";

    const titleRow = document.createElement("div");
    titleRow.className = "tb-check-title-row";

    const title = document.createElement("span");
    title.className = "tb-check-title";
    title.textContent = niceCheckLabel(check.item);

    const badge = document.createElement("span");
    badge.className = statusBadgeClass(check.status);
    badge.textContent = niceStatusLabel(check.status);

    titleRow.appendChild(title);
    titleRow.appendChild(badge);

    const detail = document.createElement("div");
    detail.className = "tb-check-detail";
    detail.textContent = check.detail || "";

    li.appendChild(titleRow);
    li.appendChild(detail);
    list.appendChild(li);
  }
}

// ---------------------------
// Rig image mapping (LOCKED rules + your filenames)
// ---------------------------
function getVehicleFamilyFromPreset(presetKey) {
  if (!presetKey) return "defender";
  if (presetKey === "defender_110") return "defender";

  const uteKeys = new Set([
    "ford_ranger",
    "toyota_hilux",
    "mitsubishi_triton",
    "nissan_navara",
    "isuzu_dmax",
    "mazda_bt50",
    "vw_amarok",
    "byd_shark",
  ]);
  if (uteKeys.has(presetKey)) return "ute";

  const bigWagonKeys = new Set(["landcruiser_200_300", "prado", "discovery_5", "range_rover", "ford_everest"]);
  if (bigWagonKeys.has(presetKey)) return "large-suv";

  return "small-suv";
}

function getAxleSuffix(axleConfig) {
  return axleConfig === "single" ? "single-rig" : "twin-rig"; // unknown => twin-rig
}

function getOrientationSuffix(orientation) {
  if (orientation === "nose_heavy") return "nose-heavy";
  if (orientation === "nose_light") return "nose-light";
  return "nose-level";
}

function rigImagePath(family, axleSuffix, orientationSuffix) {
  return `/static/images/${family}-${axleSuffix}-${orientationSuffix}.png`;
}

function updateRigVisual(params) {
  const rigCard = $("rig-card");
  const rigImage = $("rig-image");
  const rigCaption = $("rig-caption");
  if (!rigCard || !rigImage || !rigCaption) return;

  const { orientation, showBadge, riskColour, noData, presetKey, axleConfig } = params;

  let badge = document.getElementById("rig-danger-badge");
  if (!badge) {
    badge = document.createElement("div");
    badge.id = "rig-danger-badge";
    badge.textContent = "✕";
    rigCard.appendChild(badge);
  }

  if (noData) {
    rigImage.onerror = null;
    rigImage.src = rigImagePath("defender", "twin-rig", "nose-level");
    rigImage.style.opacity = "0.35";
    rigCaption.textContent = "Once you've added your tow vehicle and caravan details, we'll show your current setup here.";
    badge.style.display = "none";
    rigCard.style.borderColor = "rgba(209,213,219,0.9)";
    return;
  }

  if (orientation === "nose_light") {
    rigCaption.textContent =
      "You’ve got more weight hanging off the rear than the front. That can lighten the ball and make the rig feel twitchy or sway-prone.";
  } else if (orientation === "nose_heavy") {
    rigCaption.textContent =
      "You’ve got more weight forward than the rear. Worth watching ball weight, towbar limits, and how the van behaves on rough roads.";
  } else {
    rigCaption.textContent =
      "On these numbers, your rig looks broadly within guide limits. Still worth confirming with real-world weighbridge figures.";
  }

  const family = getVehicleFamilyFromPreset(presetKey);
  const axleSuffix = getAxleSuffix(axleConfig);
  const orientationSuffix = getOrientationSuffix(orientation);

  rigImage.style.opacity = "0.95";
  rigImage.onerror = null;
  rigImage.src = rigImagePath(family, axleSuffix, orientationSuffix);

  rigImage.onerror = () => {
    if (family === "defender" && axleSuffix === "single-rig" && orientationSuffix === "nose-level") {
      rigImage.src = `/static/images/defender-single-rig-nose-evel.png`;
    }
  };

  const keyColour = (riskColour || "").toLowerCase();
  if (keyColour === "green") rigCard.style.borderColor = "rgba(16,185,129,0.9)";
  else if (keyColour === "amber") rigCard.style.borderColor = "#fbbf24";
  else if (keyColour === "red") rigCard.style.borderColor = "#f97373";
  else rigCard.style.borderColor = "rgba(209,213,219,0.9)";

  badge.style.display = showBadge ? "flex" : "none";
}

function buildResultSummary(status, riskColour, backendSummary) {
  const keyStatus = normalizeStatus(status);
  const keyColour = (riskColour || "").toLowerCase();

  const caravanLabel = ($("caravan_label")?.value || "").trim();
  const prefix = caravanLabel ? `${caravanLabel} — ` : "";

  const msgOver =
    backendSummary ||
    "TouringBrain has found one or more areas over common limits. Treat this as a red flag: lighten the van, re-check all plate ratings, and confirm real weights on a weighbridge before towing.";

  const msgNear =
    backendSummary ||
    "On the numbers you've given, your setup looks broadly within common guidance, but it's still worth confirming with a weighbridge.";

  const msgOk =
    backendSummary ||
    "On these numbers your setup looks within common NZ guide limits. Still worth confirming with real-world weighbridge figures.";

  const msgDefault =
    backendSummary ||
    "Fill in your details and hit “Check my setup” to see a towing sanity check.";

  if (keyStatus === "over_limit" || keyColour === "red") return prefix + msgOver;
  if (keyStatus === "near_limit" || keyColour === "amber") return prefix + msgNear;
  if (keyStatus === "ok" || keyColour === "green") return prefix + msgOk;
  return prefix + msgDefault;
}

// ---------------------------
// Payload builder (backend still expects these fields)
// ---------------------------
function buildTowingPayload() {
  const vehicleLabel = $("vehicle_label")?.value || "";
  const caravanLabel = $("caravan_label")?.value || "";

  const towRating = parseNumber($("tow_rating")?.value);
  const ballLimit = parseNumber($("ball_limit")?.value);

  const atm = parseNumber($("caravan_atm")?.value);
  const loaded = parseNumber($("caravan_loaded")?.value);
  const ball = parseNumber($("caravan_ball")?.value);

  const front = parseNumber($("front_extra_kg")?.value);
  const rear = parseNumber($("rear_extra_kg")?.value);

  return {
    rig_type: "towed_caravan",
    vehicle: {
      label: (vehicleLabel || "Tow vehicle").trim(),
      tow_rating_braked_kg: towRating,
      max_ball_weight_kg: ballLimit,
    },
    caravan: {
      label: (caravanLabel || "Caravan").trim(),
      atm_kg: atm,
      loaded_estimate_kg: loaded,
      ball_weight_kg: ball,
      axle_rating_kg: null,
    },
    extras: { front_extra_kg: front, rear_extra_kg: rear },
    use_vehicle_lookup: false,
    use_caravan_lookup: false,
  };
}

// ---------------------------
// Preset handler
// ---------------------------
function onPresetChange() {
  const select = $("vehicle_preset");
  if (!select) return;

  const presetKey = select.value;
  const hintEl = $("vehicle-preset-hint");

  if (!presetKey) {
    if (hintEl) hintEl.textContent = "";
    return;
  }

  const preset = VEHICLE_PRESETS[presetKey];
  if (!preset) {
    if (hintEl) hintEl.textContent = "";
    return;
  }

  if ($("vehicle_label") && !($("vehicle_label").value || "").trim()) $("vehicle_label").value = preset.label;
  if ($("tow_rating") && preset.tow_rating_kg != null) $("tow_rating").value = preset.tow_rating_kg;
  if ($("ball_limit") && preset.ball_limit_kg != null) $("ball_limit").value = preset.ball_limit_kg;

  if (hintEl) hintEl.textContent = "Using TouringBrain guide figures. Always confirm with your handbook and vehicle/caravan plates.";
}

// ---------------------------
// Ensure Ford Everest exists in dropdown (Big Wagons)
// ---------------------------
function ensureEverestOption() {
  const select = $("vehicle_preset");
  if (!select) return;

  if (select.querySelector('option[value="ford_everest"]')) return;

  const opt = document.createElement("option");
  opt.value = "ford_everest";
  opt.textContent = "Ford Everest";

  const groups = Array.from(select.querySelectorAll("optgroup"));
  const big = groups.find((g) => /big\s*wagons?|wagons?/i.test(g.label || ""));
  if (big) big.appendChild(opt);
  else select.appendChild(opt);
}

// ---------------------------
// Main submit handler
// ---------------------------
async function submitTowingForm(event) {
  event.preventDefault();

  const form = event.currentTarget || $("towing-form");
  if (!form) return;

  if (!form.checkValidity()) {
    form.reportValidity();
    return;
  }

  // Keep the quick guide in sync even if user never typed after load
  updateQuickGuideFromForm();

  if (form.dataset.submitting === "1") return;
  form.dataset.submitting = "1";

  try {
    const summaryEl = $("towing-summary");
    if (summaryEl) summaryEl.textContent = "Running checks on your setup…";

    const payload = buildTowingPayload();

    const towRatingKg = parseNumber($("tow_rating")?.value);
    const ballLimitKg = parseNumber($("ball_limit")?.value);

    const atmKg = parseNumber($("caravan_atm")?.value);
    const loadedKg = parseNumber($("caravan_loaded")?.value);
    const measuredBallKg = parseNumber($("caravan_ball")?.value);

    const axleConfig = getAxleConfig();
    const towbarType = getTowbarType();
    const lengthFt = getLengthFt();

    const frontKg = parseNumber($("front_extra_kg")?.value) || 0;
    const rearKg = parseNumber($("rear_extra_kg")?.value) || 0;

    const presetKey = ($("vehicle_preset")?.value || "").trim();

    const noData =
      (!loadedKg || loadedKg <= 0) && (!measuredBallKg || measuredBallKg <= 0) && (!atmKg || atmKg <= 0);

    const front = computeFrontLoadStatus(frontKg, axleConfig);
    const rear = computeRearLoadStatus(rearKg, lengthFt);

    const ball = computeBallStatus({
      loadedKg,
      measuredBallKg,
      ballLimitKg,
      towbarType,
      axleConfig,
      lengthFt,
      frontKg,
      rearKg,
    });

    const combinedBallFrontStatus = combineLoadAndBallStatus(ball.status, front.band);

    // Distribution sanity: front+rear should not exceed loaded (since slices)
    let distributionStatus = "ok";
    let distributionDetail = "";
    if (loadedKg && loadedKg > 0 && (frontKg > 0 || rearKg > 0)) {
      const sum = frontKg + rearKg;
      if (sum > loadedKg) {
        const ratio = sum / loadedKg;
        distributionStatus = ratio >= 1.15 ? "over_limit" : "near_limit";
        distributionDetail = `Your front + rear slices add up to ${sum.toFixed(
          0
        )} kg, which is more than your loaded travel weight (${loadedKg.toFixed(
          0
        )} kg). These fields are meant to be slices of the loaded weight, not extra on top.`;
      } else {
        distributionDetail = `Front + rear slices total ${sum.toFixed(0)} kg out of ${loadedKg.toFixed(0)} kg loaded travel weight.`;
      }
    }

    // Tow rating check
    const towRatingStatus = (() => {
      if (!towRatingKg || !loadedKg) {
        return {
          status: "near_limit",
          detail: "No usable tow rating or loaded travel weight provided, so TouringBrain can’t confirm tow rating margin.",
        };
      }
      if (loadedKg > towRatingKg) {
        return {
          status: "over_limit",
          detail: `Your caravan travel weight (${loadedKg.toFixed(0)} kg) is over your vehicle’s braked tow rating (${towRatingKg.toFixed(0)} kg).`,
        };
      }
      const ratio = loadedKg / towRatingKg;
      if (ratio >= 0.9) {
        return {
          status: "near_limit",
          detail: `Your caravan travel weight (${loadedKg.toFixed(0)} kg) is close to your braked tow rating (${towRatingKg.toFixed(0)} kg).`,
        };
      }
      return {
        status: "ok",
        detail: `On the numbers provided, your caravan weight (${loadedKg.toFixed(
          0
        )} kg) is under your vehicle's braked tow rating (${towRatingKg.toFixed(
          0
        )} kg). Still worth confirming with a weighbridge when you can.`,
      };
    })();

    // ATM check
    const atmStatus = (() => {
      if (!atmKg || !loadedKg) {
        return {
          status: "near_limit",
          detail: "No usable van plate ATM or loaded travel weight provided, so TouringBrain can’t confirm whether you're under the van’s plated maximum.",
        };
      }
      if (loadedKg > atmKg) {
        return {
          status: "over_limit",
          detail: `Your caravan travel weight (${loadedKg.toFixed(0)} kg) is over the van’s plated ATM (${atmKg.toFixed(0)} kg).`,
        };
      }
      const ratio = loadedKg / atmKg;
      if (ratio >= 0.9) {
        return {
          status: "near_limit",
          detail: `Your caravan travel weight (${loadedKg.toFixed(0)} kg) is close to the van’s plated ATM (${atmKg.toFixed(0)} kg).`,
        };
      }
      return {
        status: "ok",
        detail: `Your caravan travel weight (${loadedKg.toFixed(0)} kg) is under the van’s plated ATM (${atmKg.toFixed(0)} kg).`,
      };
    })();

    // Ball check detail (uses combined status)
    const ballDetail = (() => {
      if (!loadedKg || loadedKg <= 0) {
        return {
          status: "near_limit",
          detail: "No loaded travel weight provided, so TouringBrain can’t estimate ball weight percentage.",
        };
      }
      const pct = ball.percent != null ? ball.percent : null;
      const pctText = pct != null ? `${pct.toFixed(1)}%` : "–";
      const estText = ball.estimatedBallKg != null ? `${ball.estimatedBallKg.toFixed(0)} kg` : "–";

      let limitLine = "";
      if (ball.effectiveBallLimitKg != null) limitLine = ` Effective ball limit (towbar type applied): ${ball.effectiveBallLimitKg.toFixed(0)} kg.`;
      else if (ballLimitKg != null) limitLine = ` Ball limit entered: ${ballLimitKg.toFixed(0)} kg.`;

      if (combinedBallFrontStatus === "over_limit") {
        return {
          status: "over_limit",
          detail: `Estimated ball load ${estText} (~${pctText} of loaded).${limitLine} Front loading may be pushing this into an unsafe zone.`,
        };
      }
      if (combinedBallFrontStatus === "near_limit") {
        return {
          status: "near_limit",
          detail: `Estimated ball load ${estText} (~${pctText} of loaded).${limitLine} Worth checking with a ball scale and weighbridge.`,
        };
      }
      return { status: "ok", detail: `Estimated ball load ${estText} (~${pctText} of loaded).${limitLine}` };
    })();

    const frontDetail = (() => {
      const axleLabel = axleConfig === "tandem" ? "tandem" : "single (or unknown)";
      if (!frontKg || frontKg <= 0) return { status: "ok", detail: "No meaningful front load entered." };
      if (front.band === "critical") return { status: "over_limit", detail: `Front load ${frontKg.toFixed(0)} kg (${axleLabel}) falls in the critical band. Treat this as a red flag.` };
      if (front.band === "red") return { status: "over_limit", detail: `Front load ${frontKg.toFixed(0)} kg (${axleLabel}) falls in the red band. High risk of nose-heavy behaviour.` };
      if (front.band === "amber") return { status: "near_limit", detail: `Front load ${frontKg.toFixed(0)} kg (${axleLabel}) is in the amber band. Worth double-checking ball weight and towbar limits.` };
      return { status: "ok", detail: `Front load ${frontKg.toFixed(0)} kg (${axleLabel}) looks OK.` };
    })();

    const rearDetail = (() => {
      if (!rearKg || rearKg <= 0) return { status: "ok", detail: "No meaningful rear load entered." };
      const bucketLabel = rear.bucket === "short" ? "short van" : rear.bucket === "long" ? "long van" : "medium van";
      if (rear.band === "red") return { status: "over_limit", detail: `Rear load ${rearKg.toFixed(0)} kg (${bucketLabel}) falls in the red band. This can increase sway risk.` };
      if (rear.band === "amber") return { status: "near_limit", detail: `Rear load ${rearKg.toFixed(0)} kg (${bucketLabel}) is in the amber band. Keep an eye on stability and ball weight.` };
      return { status: "ok", detail: `Rear load ${rearKg.toFixed(0)} kg (${bucketLabel}) looks OK.` };
    })();

    // Call backend
    const response = await fetch("/towing/evaluate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    let backendData = null;
    if (response.ok) backendData = await response.json();

    const overall = computeOverallStatus(backendData, combinedBallFrontStatus, rear.uiStatus, distributionStatus);

    setStatusPill(overall.status, overall.risk_colour);

    if (summaryEl) {
      const backendSummary = backendData?.advice?.summary || backendData?.disclaimer || "";
      // IMPORTANT: buildResultSummary already prefixes with caravan label, so don't double-prefix.
      summaryEl.textContent = buildResultSummary(overall.status, overall.risk_colour, backendSummary);
    }

    renderChecks({
      backendChecks: backendData?.checks || [],
      towRatingStatus,
      atmStatus,
      ballStatus: ballDetail,
      frontStatus: frontDetail,
      rearStatus: rearDetail,
      distributionStatus,
      distributionDetail,
    });

    const { orientation, showBadge } = getRigOrientation(front.rank, rear.rank, overall.status);
    updateRigVisual({
      orientation,
      showBadge,
      riskColour: overall.risk_colour,
      noData,
      presetKey,
      axleConfig,
    });

    setTimeout(() => {
      const resultsCard = document.getElementById("towing-result-card");
      if (resultsCard) resultsCard.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 100);
  } catch (err) {
    console.error("Error calling /towing/evaluate:", err);

    const summaryEl = $("towing-summary");
    if (summaryEl) {
      summaryEl.textContent =
        "We couldn’t reach the TouringBrain towing service. Showing a local-only sanity check based on your inputs.";
    }
  } finally {
    form.dataset.submitting = "0";
  }
}

// ---------------------------
// Rear-load gauge UI
// ---------------------------
function updateRearLoadUI() {
  const fill = $("rear-gauge-fill");
  const pill = $("rear-load-commentary");
  if (!fill || !pill) return;

  const rearKg = parseNumber($("rear_extra_kg")?.value) || 0;
  const lengthFt = getLengthFt();

  const rear = computeRearLoadStatus(rearKg, lengthFt);

  const maxRed = rear.bucket === "short" ? 50 : rear.bucket === "long" ? 30 : 40;

  const pct = maxRed > 0 ? Math.max(0, Math.min(1, rearKg / maxRed)) * 100 : 0;
  fill.style.width = `${pct.toFixed(0)}%`;

  pill.classList.remove(
    "tb-rear-commentary-pill--ghost",
    "tb-rear-commentary-pill--ok",
    "tb-rear-commentary-pill--amber",
    "tb-rear-commentary-pill--red"
  );

  fill.style.background = "rgba(156, 163, 175, 0.9)"; // grey default

  if (!rearKg) {
    pill.classList.add("tb-rear-commentary-pill--ghost");
    pill.textContent = "Add rear weight and van length to see how twitchy this might get.";
    fill.style.width = "0%";
    return;
  }

  if (rear.band === "ok") {
    pill.classList.add("tb-rear-commentary-pill--ok");
    pill.textContent = "Rear load looks OK on these numbers.";
    fill.style.background = "rgba(16, 185, 129, 0.9)";
    return;
  }

  if (rear.band === "amber") {
    pill.classList.add("tb-rear-commentary-pill--amber");
    pill.textContent = "Rear load is getting up there — worth watching sway and ball weight.";
    fill.style.background = "rgba(245, 158, 11, 0.95)";
    return;
  }

  pill.classList.add("tb-rear-commentary-pill--red");
  pill.textContent = "Rear load is in the red zone — higher sway risk. Shift weight forward.";
  fill.style.background = "rgba(239, 68, 68, 0.9)";
}

// ---------------------------
// Init
// ---------------------------
document.addEventListener("DOMContentLoaded", () => {
  ensureEverestOption();

  const form = $("towing-form");
  if (form) {
    form.dataset.submitting = "0";
    form.addEventListener("submit", submitTowingForm);

    const submitBtn = $("towing-submit");
    if (submitBtn) {
      // Fix “needs two clicks”: first interaction can be swallowed by <select> focus.
      submitBtn.addEventListener("pointerdown", (e) => {
        e.preventDefault();
        form.requestSubmit();
      });

      submitBtn.addEventListener("click", (e) => {
        e.preventDefault();
        form.requestSubmit();
      });
    }
  }

  const presetSelect = $("vehicle_preset");
  if (presetSelect) {
    presetSelect.addEventListener("change", onPresetChange);
    if ((presetSelect.value || "").trim()) onPresetChange();
  }

  const blurOnChange = (id) => {
    const el = $(id);
    if (!el) return;
    el.addEventListener("change", () => el.blur());
  };
  blurOnChange("towbar_type");
  blurOnChange("axle_config");

  // Quick guide wiring (covers typing + paste + autofill + “picked suggestion”)
const quickIds = ["caravan_label", "caravan_tare", "caravan_atm", "caravan_loaded", "caravan_ball"];

const wireQuickGuide = (id) => {
  const el = $(id);
  if (!el) return;

  // normal typing
  el.addEventListener("input", updateQuickGuideFromForm);

  // Chrome autofill / suggestion pick often triggers change, not input
  el.addEventListener("change", updateQuickGuideFromForm);

  // some autofill flows only show up on blur
  el.addEventListener("blur", updateQuickGuideFromForm);

  // safety net for “browser filled it but no events fired”
  el.addEventListener("focus", () => setTimeout(updateQuickGuideFromForm, 50));
};

quickIds.forEach(wireQuickGuide);

// run once on load
updateQuickGuideFromForm();

  // Rear-load gauge wiring
  updateRearLoadUI();
  $("rear_extra_kg")?.addEventListener("input", updateRearLoadUI);
  $("caravan_length_m")?.addEventListener("input", updateRearLoadUI);

  // Ghost rig on load
  updateRigVisual({
    orientation: "level",
    showBadge: false,
    riskColour: "grey",
    noData: true,
    presetKey: "",
    axleConfig: "tandem",
  });
});
// app/static/touring.js
// Touring mode – STEP 2 wiring
// Purpose:
// 1) Form submits
// 2) Calls backend /touring/plan
// 3) Renders full response into STEP 5 (#touring_result)
// 4) Persists form + last result in localStorage

document.addEventListener("DOMContentLoaded", () => {
  console.log("✅ touring.js loaded");

  const LS_TOURING_FORM = "tb.touring.form.v1";
  const LS_TOURING_RESULT = "tb.touring.result.v1";

  const form = document.getElementById("touring_form");
  if (!form) {
    console.warn("❌ touring_form not found");
    return;
  }

  const resultEl = document.getElementById("touring_result");
  if (!resultEl) {
    console.warn("❌ touring_result container not found");
    return;
  }

  // ---------- small helpers ----------

  function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[c]));
  }

  function safeNum(x, dp = 1) {
    const n = Number(x);
    return Number.isFinite(n) ? n.toFixed(dp) : "—";
  }

  function safeInt(x) {
    const n = Number(x);
    return Number.isFinite(n) ? String(Math.round(n)) : "—";
  }

  function cap(s) {
    const t = String(s ?? "");
    return t ? t.charAt(0).toUpperCase() + t.slice(1) : "—";
  }

  function formatDriveTime(hours) {
    const hNum = Number(hours);
    if (!Number.isFinite(hNum) || hNum <= 0) return "—";

    const totalMinutes = Math.round(hNum * 60);

    if (totalMinutes < 60) {
      return `Around ${totalMinutes} minutes`;
    }

    const h = Math.floor(totalMinutes / 60);
    const m = totalMinutes % 60;

    if (m === 0) {
      return `Around ${h} hour${h > 1 ? "s" : ""}`;
    }

    return `Around ${h} hour${h > 1 ? "s" : ""} ${m} minute${m !== 1 ? "s" : ""}`;
  }

  function humanTravelDayLabel(choice) {
    const c = String(choice || "").toLowerCase().trim();
    if (c === "today") return "Today";
    if (c === "tomorrow") return "Tomorrow";
    if (c === "in_2_days") return "In 2 days";
    if (/^\d{4}-\d{2}-\d{2}$/.test(c)) return c;
    return choice || "—";
  }

  // Convert UI choice -> YYYY-MM-DD (NZ-local, no UTC drift)
  function ymdLocal(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }

  function resolveTravelDayIso(choice) {
    const c = String(choice || "").toLowerCase().trim();
    const today = new Date();
    if (c === "today") return ymdLocal(today);
    if (c === "tomorrow") return ymdLocal(new Date(today.getFullYear(), today.getMonth(), today.getDate() + 1));
    if (c === "day_after_tomorrow") return ymdLocal(new Date(today.getFullYear(), today.getMonth(), today.getDate() + 2));
    if (c === "in_2_days") return ymdLocal(new Date(today.getFullYear(), today.getMonth(), today.getDate() + 2));
    if (c === "in_3_days") return ymdLocal(new Date(today.getFullYear(), today.getMonth(), today.getDate() + 3));

    // If the radio is already an ISO date (YYYY-MM-DD), accept it
    if (/^\d{4}-\d{2}-\d{2}$/.test(c)) return c;

    // Worst-case fallback: treat unknown strings as today (prevents 422)
    return ymdLocal(today);
  }

  // ---------- persistence (form + last result) ----------

  function saveTouringFormState() {
    const origin = document.getElementById("touring_origin")?.value ?? "";
    const destination = document.getElementById("touring_destination")?.value ?? "";
    const travelDayChoice =
      form.querySelector('input[name="travel_day"]:checked')?.value || "";

    const state = { origin, destination, travelDayChoice };

    try {
      localStorage.setItem(LS_TOURING_FORM, JSON.stringify(state));
    } catch (e) {
      // ignore
    }
  }

  function loadTouringFormState() {
    const raw = localStorage.getItem(LS_TOURING_FORM);
    if (!raw) return;

    let state;
    try { state = JSON.parse(raw); } catch { return; }

    if (typeof state.origin === "string") {
      const el = document.getElementById("touring_origin");
      if (el) el.value = state.origin;
    }
    if (typeof state.destination === "string") {
      const el = document.getElementById("touring_destination");
      if (el) el.value = state.destination;
    }
    if (typeof state.travelDayChoice === "string" && state.travelDayChoice) {
      const selector = `input[name="travel_day"][value="${CSS.escape(state.travelDayChoice)}"]`;
      const radio = form.querySelector(selector);
      if (radio) radio.checked = true;
    }
  }

  function saveTouringResultState(data) {
    try {
      localStorage.setItem(LS_TOURING_RESULT, JSON.stringify(data));
    } catch (e) {
      // ignore
    }
  }

  function loadTouringResultState() {
    const raw = localStorage.getItem(LS_TOURING_RESULT);
    if (!raw) return;

    let data;
    try { data = JSON.parse(raw); } catch { return; }

    if (data && typeof data === "object" && data.main_leg) {
      resultEl.innerHTML = renderResult(data);
    }
  }

  // ✅ restore saved state now that form + resultEl exist
  loadTouringFormState();
  loadTouringResultState();

  // ✅ autosave
  form.addEventListener("input", saveTouringFormState);
  form.addEventListener("change", saveTouringFormState);

  // ---------- action/why helpers ----------

  function renderActionAdvice(comfortRaw) {
    const c = String(comfortRaw || "").toLowerCase();
    if (c === "good" || c === "fair") return "";

    const isParkUp = (c === "park_up");
    const title = isParkUp
      ? "Action advice — Could be a tough towing day, double-check"
      : "Action advice — Take care";

    const bullets = isParkUp
      ? [
          "Strong gusts expected at/near your destination. Suggest the best call might be to stay put and go when things settle down.",
          "If you absolutely must move: go early, take it slow, and avoid exposed stretches if possible.",
        ]
      : [
          "Go early if you can — wind often builds later.",
          "Take it slow and try to avoid exposed stretches if possible.",
        ];

    const lis = bullets
      .map(b => '<li class="tb-summary-text" style="margin:0.25rem 0;">' + esc(b) + '</li>')
      .join("");

    return (
      '<div style="margin-top:0.75rem; padding:0.85rem 1rem; border:1px solid rgba(229,231,235,1); border-radius:1rem; background: rgba(255,255,255,0.92);">' +
        '<div style="font-weight:900; margin-bottom:0.4rem;">' + esc(title) + '</div>' +
        '<ul style="margin:0 0 0 1.1rem; padding:0;">' + lis + '</ul>' +
      '</div>'
    );
  }

  function renderWhyBlock(comfortRaw, ctx) {
    const c = String(comfortRaw || "").toLowerCase();
    if (c !== "caution" && c !== "park_up") return "";

    const stress = ctx?.stress ?? "—";
    const compBetter = ctx?.compBetter ?? "—";
    const compReason = ctx?.compReason ?? "";

    const fromGust = Number(ctx?.fromDay?.wind_gust_kmh);
    const toGust = Number(ctx?.toDay?.wind_gust_kmh);

    let trigger = "";
    if (Number.isFinite(fromGust) && Number.isFinite(toGust)) {
      if (toGust > fromGust + 8) {
        trigger = `Stronger gusts expected near your destination (${safeNum(toGust, 1)} km/h).`;
      } else if (fromGust > toGust + 8) {
        trigger = `Stronger gusts expected near your departure (${safeNum(fromGust, 1)} km/h).`;
      } else {
        trigger = `Gust risk is similar at both ends (up to ~${safeNum(Math.max(fromGust, toGust), 1)} km/h).`;
      }
    }

    const timeHint =
      (c === "park_up")
        ? "If you absolutely must move: go early if you can — wind often builds later."
        : "Tip: go early if you can — wind often builds later.";

    return `
      <div style="
        margin-top:0.9rem;
        padding:1rem 1.1rem;
        border:1px solid rgba(229,231,235,1);
        border-radius:1rem;
        background: rgba(255,255,255,0.96);
      ">
        <div style="font-weight:900; font-size:1.05rem; margin-bottom:0.55rem;">
          Why this call
        </div>

        <div class="tb-summary-text" style="margin:0.25rem 0;">
          <strong>Route towing stress:</strong> ${esc(stress)} / 100
        </div>

        ${trigger ? `
          <div class="tb-summary-text" style="margin:0.25rem 0;">
            <strong>What’s driving it:</strong> ${esc(trigger)}
          </div>
        ` : ``}

        <div class="tb-summary-text" style="margin:0.25rem 0;">
          <strong>Towing pick:</strong> ${esc(compBetter)}${compReason ? " — " + esc(compReason) : ""}
        </div>

        <div class="tb-summary-text" style="margin:0.45rem 0 0;">
          ${esc(timeHint)}
        </div>
      </div>
    `;
  }

  // ---------- main renderer ----------

  function renderResult(data) {
    let comfortRaw = String(data?.comfort_label ?? "—").toLowerCase();

    const stress = safeInt(data?.route_towing_stress);
    const travelHuman = data?.travel_day_human ?? "";
    const travelIso = data?.travel_day_iso ?? "";
    const rec = data?.recommendation ?? "";

    function pillClass(label) {
      if (label === "good") return "tb-status-pill tb-status-pill--green";
      if (label === "fair") return "tb-status-pill tb-status-pill--amber";
      if (label === "caution") return "tb-status-pill tb-status-pill--amber";
      if (label === "park_up") return "tb-status-pill tb-status-pill--red";
      return "tb-status-pill tb-status-pill--grey";
    }

    const legKm = safeNum(data?.main_leg?.distance_km, 1);
    const legHrsNum = Number(data?.main_leg?.drive_hours_estimate);

    const fromName = data?.from_summary?.location?.name ?? "—";
    const toName = data?.to_summary?.location?.name ?? "—";

    const fromDay = data?.from_summary?.day ?? {};
    const toDay = data?.to_summary?.day ?? {};

    // upgrade comfort to park_up if either end has park_up_flag
    if (fromDay?.park_up_flag || toDay?.park_up_flag) {
      comfortRaw = "park_up";
    }

    const compBetter = cap(data?.comparison?.better_for_towing ?? "—");
    const compReason = data?.comparison?.reason ?? "";

    return `
      <!-- CARD 1: Call -->
      <div class="tb-card">
        <h2 style="margin-top:0">Your touring call</h2>

        <div class="tb-result-header">
          <span class="${pillClass(comfortRaw)}">${esc(String(comfortRaw).toUpperCase())}</span>
          <span class="tb-risk-label">
            ${travelHuman ? esc(travelHuman) : ""}${travelIso ? ` (${esc(travelIso)})` : ""}
          </span>
        </div>

        ${renderActionAdvice(comfortRaw)}

    <div style="
  margin-top:0.9rem;
  padding:1rem 1.1rem;
  border:1px solid rgba(203,213,225,1);
  border-radius:1rem;
  background: #f8fafc;
">
  <div style="font-weight:900; font-size:1.05rem; margin-bottom:0.55rem;">
    Summary
  </div>
  <p class="tb-summary-text" style="margin:0; line-height:1.55;">
    ${esc(rec)}
  </p>
</div>

        ${renderWhyBlock(comfortRaw, {
          stress,
          compBetter,
          compReason,
          fromName,
          toName,
          fromDay,
          toDay
        })}

        ${data.route_wind_profile ? `
          <div style="
            margin-top:16px;
            border:1px solid rgba(229,231,235,1);
            border-radius:1rem;
            padding:1.05rem 1.15rem;
            background:#ffffff;
            box-shadow:
              0 12px 28px rgba(15,23,42,0.10),
              0 0 0 1px rgba(255,255,255,0.55) inset;
          ">
            <div style="font-weight:900; font-size:1.02rem;">🌬️ Conditions along your route</div>
            <p class="tb-summary-text" style="margin-top:6px; line-height:1.45;">
              Breeziest stretch looks near ${esc(toName)}, with gusts up to
              <strong>${esc(safeNum(data.route_wind_profile.worst_wind_gust_kmh,1))} km/h</strong>
              (avg ~${esc(safeNum(data.route_wind_profile.worst_wind_avg_kmh,1))} km/h).
            </p>
            <p class="tb-helper-text" style="margin-top:0.5rem;">
              Wind exposure sampled along the A→B line (not road routing).
            </p>
          </div>
        ` : ``}
      </div>

      <!-- CARD 2: Drive leg -->
      <div class="tb-card">
        <h2 style="margin-top:0">Drive leg</h2>

        <!-- From → To row -->
        <div style="display:flex; align-items:center; gap:14px; flex-wrap:wrap; margin-top:6px;">
          <div style="min-width:160px;">
            <div class="tb-helper-text" style="margin:0;">From</div>
            <div style="font-weight:800; font-size:1.05rem;">${esc(fromName)}</div>
          </div>

          <!-- Arrow bar -->
          <div style="
            flex: 1 1 auto;
            max-width: 420px;
            margin: 0 auto;
            position: relative;
            height: 34px;
          ">
            <div style="
              position:absolute;
              left:0;
              right:0;
              top:50%;
              transform:translateY(-50%);
              height:14px;
              border-radius:999px;
              background: rgba(229, 231, 235, 0.85);
              border: 1px solid rgba(209, 213, 219, 0.9);
              box-shadow: inset 0 1px 0 rgba(255,255,255,0.7);
              z-index:0;
            "></div>

            <div style="
              position:absolute;
              right:-2px;
              top:50%;
              transform:translateY(-50%);
              width:0;
              height:0;
              border-top:8px solid transparent;
              border-bottom:8px solid transparent;
              border-left:12px solid rgba(156,163,175,0.95);
              z-index:1;
            "></div>

            <img
              src="/static/images/rig-placeholder.png"
              alt="Rig"
              style="
                position:absolute;
                left:50%;
                top:50%;
                transform:translate(-50%, -62%);
                height:35px;
                opacity:0.85;
                pointer-events:none;
                z-index:2;
              "
              onerror="this.style.display='none';"
            />
          </div>

          <div style="min-width:160px; text-align:left;">
            <div class="tb-helper-text" style="margin:0;">To</div>
            <div style="font-weight:800; font-size:1.05rem;">${esc(toName)}</div>
          </div>
        </div>

        <!-- Numbers (distance left, drive-time centered) -->
        <div style="
          display:grid;
          grid-template-columns: 1fr auto 1fr;
          align-items:start;
          gap:16px;
          margin-top:14px;
        ">
          <div style="justify-self:start;">
            <div class="tb-helper-text" style="margin:0;">Distance</div>
            <div style="font-weight:900; font-size:1.1rem;">${esc(legKm)} km</div>
          </div>

          <div style="justify-self:center; text-align:center;">
            <div class="tb-helper-text" style="margin:0;">Drive time</div>
            <div style="font-weight:900; font-size:1.1rem;">
              ${formatDriveTime(legHrsNum)}
            </div>
          </div>

          <div></div>
        </div>
      </div>

      <!-- CARD 3: Weather snapshot -->
      <div class="tb-card">
        <h2 style="margin-top:0">Weather snapshot</h2>

        <div style="display:grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap:16px; margin-top:10px;">
          <!-- FROM -->
          <div style="
            border: 1px solid rgba(229,231,235,1);
            border-radius: 1rem;
            padding: 1rem 1.05rem;
            background: rgba(255,255,255,0.92);
            box-shadow:
              0 10px 24px rgba(15, 23, 42, 0.08),
              0 0 0 1px rgba(255, 255, 255, 0.55) inset;
          ">
            <div style="display:flex; align-items:center; justify-content:space-between; gap:10px;">
              <div style="font-weight:900; font-size:1.05rem;">📍 ${esc(fromName)}</div>
              ${fromDay?.park_up_flag ? `<span class="tb-status-pill tb-status-pill--red">PARK UP</span>` : ``}
            </div>

            <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-top:10px;">
              <div>
                <div class="tb-helper-text" style="margin:0;">💨 Wind avg</div>
                <div style="font-weight:900; font-size:1.05rem;">${esc(safeNum(fromDay?.wind_avg_kmh,1))} <span style="font-weight:700; color:#6b7280;">km/h</span></div>
              </div>
              <div>
                <div class="tb-helper-text" style="margin:0;">🌬️ Gusts</div>
                <div style="font-weight:900; font-size:1.05rem;">${esc(safeNum(fromDay?.wind_gust_kmh,1))} <span style="font-weight:700; color:#6b7280;">km/h</span></div>
              </div>
              <div>
                <div class="tb-helper-text" style="margin:0;">🌧️ Rain</div>
                <div style="font-weight:900; font-size:1.05rem;">${esc(safeNum(fromDay?.rain_mm,1))} <span style="font-weight:700; color:#6b7280;">mm</span></div>
              </div>
              <div>
                <div class="tb-helper-text" style="margin:0;">🌡️ Overnight low</div>
                <div style="font-weight:900; font-size:1.05rem;">${esc(safeNum(fromDay?.overnight_temp_c,1))} <span style="font-weight:700; color:#6b7280;">°C</span></div>
              </div>
            </div>

            ${fromDay?.ai_summary ? `<p class="tb-summary-text" style="margin-top:10px;">${esc(fromDay.ai_summary)}</p>` : ``}
          </div>

          <!-- TO -->
          <div style="
            border: 1px solid rgba(229,231,235,1);
            border-radius: 1rem;
            padding: 1rem 1.05rem;
            background: rgba(255,255,255,0.92);
            box-shadow:
              0 10px 24px rgba(15, 23, 42, 0.08),
              0 0 0 1px rgba(255, 255, 255, 0.55) inset;
          ">
            <div style="display:flex; align-items:center; justify-content:space-between; gap:10px;">
              <div style="font-weight:900; font-size:1.05rem;">🎯 ${esc(toName)}</div>
              ${toDay?.park_up_flag ? `<span class="tb-status-pill tb-status-pill--red">GUST ALERT</span>` : ``}
            </div>

            <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-top:10px;">
              <div>
                <div class="tb-helper-text" style="margin:0;">💨 Wind avg</div>
                <div style="font-weight:900; font-size:1.05rem;">${esc(safeNum(toDay?.wind_avg_kmh,1))} <span style="font-weight:700; color:#6b7280;">km/h</span></div>
              </div>
              <div>
                <div class="tb-helper-text" style="margin:0;">🌬️ Gusts</div>
                <div style="font-weight:900; font-size:1.05rem;">${esc(safeNum(toDay?.wind_gust_kmh,1))} <span style="font-weight:700; color:#6b7280;">km/h</span></div>
              </div>
              <div>
                <div class="tb-helper-text" style="margin:0;">🌧️ Rain</div>
                <div style="font-weight:900; font-size:1.05rem;">${esc(safeNum(toDay?.rain_mm,1))} <span style="font-weight:700; color:#6b7280;">mm</span></div>
              </div>
              <div>
                <div class="tb-helper-text" style="margin:0;">🌡️ Overnight low</div>
                <div style="font-weight:900; font-size:1.05rem;">${esc(safeNum(toDay?.overnight_temp_c,1))} <span style="font-weight:700; color:#6b7280;">°C</span></div>
              </div>
            </div>

            ${toDay?.ai_summary ? `<p class="tb-summary-text" style="margin-top:10px;">${esc(toDay.ai_summary)}</p>` : ``}
          </div>
        </div>
      </div>
    `;
  }

  // ---------- progress UI ----------

  function renderLoadingCard(origin, destination, travelDayChoice) {
    const originText = origin ? esc(origin) : "—";
    const destText = destination ? esc(destination) : "—";
    const dayText = travelDayChoice ? esc(humanTravelDayLabel(travelDayChoice)) : "—";

    return `
      <div class="tb-card">
        <h2 style="margin-top:0">Working on it…</h2>

        <div class="tb-result-header" style="margin-bottom:0.6rem;">
          <span class="tb-status-pill tb-status-pill--grey">CALCULATING</span>
          <span class="tb-risk-label">Touring call • ${dayText}</span>
        </div>

        <p class="tb-summary-text" style="margin:0.2rem 0 0.85rem;">
          From <strong>${originText}</strong> to <strong>${destText}</strong>
        </p>

        <div style="
          border: 1px solid rgba(229,231,235,1);
          border-radius: 999px;
          background: rgba(243,244,246,0.9);
          overflow: hidden;
          height: 12px;
          box-shadow: 0 0 0 1px rgba(255,255,255,0.55) inset;
        ">
          <div id="tb-progress-fill" style="
            width: 8%;
            height: 100%;
            border-radius: 999px;
            background: linear-gradient(135deg, rgba(37,99,235,0.95), rgba(29,78,216,0.95));
            transition: width 220ms ease;
          "></div>
        </div>

        <div id="tb-progress-stage" class="tb-summary-text" style="
          margin-top:0.75rem;
          font-size:0.95rem;
          line-height:1.4;
          color:#111827;
        ">
          Starting…
        </div>

        <div class="tb-helper-text" style="margin-top:0.5rem;">
          This can take a few seconds on slow network days.
        </div>
      </div>
    `;
  }

  function startProgressUI(origin, destination, travelDayChoice, submitBtn) {
    resultEl.innerHTML = renderLoadingCard(origin, destination, travelDayChoice);

    const fillEl = document.getElementById("tb-progress-fill");
    const stageEl = document.getElementById("tb-progress-stage");

    let oldBtnText = "";
    if (submitBtn) {
      oldBtnText = submitBtn.textContent || "";
      submitBtn.disabled = true;
      submitBtn.textContent = "Calculating…";
      submitBtn.style.opacity = "0.85";
      submitBtn.style.cursor = "not-allowed";
    }

    if (!fillEl || !stageEl) {
      return {
        stop: () => {
          if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = oldBtnText || "Get touring call";
            submitBtn.style.opacity = "";
            submitBtn.style.cursor = "";
          }
        },
      };
    }

    const stages = [
      "📍 Finding your locations (geocoding)…",
      "🌦️ Pulling forecasts for both ends of the trip…",
      "🌬️ Sampling wind exposure along the route…",
      "🧮 Scoring towing stress & comfort…",
      "🧭 Writing your touring call…",
    ];

    let stageIdx = 0;
    stageEl.textContent = stages[stageIdx];

    let pct = 8;
    fillEl.style.width = pct + "%";

    const tickTimer = setInterval(() => {
      const remaining = 88 - pct;

      if (remaining > 0) {
        const step = Math.max(0.6, remaining * 0.08);
        pct = Math.min(88, pct + step);
        fillEl.style.width = pct.toFixed(0) + "%";
        return;
      }

      if (pct < 95) {
        pct = Math.min(95, pct + 0.25);
        fillEl.style.width = pct.toFixed(0) + "%";
      }
    }, 260);

    let pulseTimer = null;
    const stageTimer = setInterval(() => {
      stageIdx = Math.min(stages.length - 1, stageIdx + 1);
      stageEl.textContent = stages[stageIdx];

      if (stageIdx === stages.length - 1 && !pulseTimer) {
        let dots = 0;
        const base = stages[stageIdx].replace(/\.*$/, "");
        pulseTimer = setInterval(() => {
          dots = (dots + 1) % 4;
          stageEl.textContent = base + ".".repeat(dots);
        }, 450);
      }
    }, 900);

    let stopped = false;

    const stop = (finalState) => {
      if (stopped) return;
      stopped = true;

      clearInterval(tickTimer);
      clearInterval(stageTimer);
      if (pulseTimer) clearInterval(pulseTimer);

      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.textContent = oldBtnText || "Get touring call";
        submitBtn.style.opacity = "";
        submitBtn.style.cursor = "";
      }

      fillEl.style.width = "100%";
      if (finalState === "success") stageEl.textContent = "✅ Done.";
      else if (finalState === "error") stageEl.textContent = "⚠️ Something went wrong.";
      else stageEl.textContent = "…";
    };

    return { stop };
  }

  // ---------- submit handler ----------

  form.addEventListener("submit", async (e) => {
    e.preventDefault();

    const origin = document.getElementById("touring_origin")?.value.trim() || "";
    const destination = document.getElementById("touring_destination")?.value.trim() || "";
    const travelDayChoice =
      form.querySelector('input[name="travel_day"]:checked')?.value || "";

    if (!origin || !destination || !travelDayChoice) {
      resultEl.innerHTML =
        "<div class='tb-card'><strong>Please complete all fields before submitting.</strong></div>";
      return;
    }

    // save immediately (so switching tabs keeps it)
    saveTouringFormState();

    const travelDayIso = resolveTravelDayIso(travelDayChoice);

    const submitBtn = form.querySelector('button[type="submit"]');
    const progress = startProgressUI(origin, destination, travelDayChoice, submitBtn);

    try {
      const payload = {
        from_location: { name: origin },
        to_location: { name: destination },
        travel_day_iso: travelDayIso,
        max_drive_hours: null,
      };

      const res = await fetch("/touring/plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const txt = await res.text().catch(() => "");
        throw new Error("Backend error " + res.status + (txt ? (": " + txt) : ""));
      }

      const data = await res.json();

      progress.stop("success");
      resultEl.innerHTML = renderResult(data);

      // ✅ persist last result
      saveTouringResultState(data);

      // ✅ jump user to the result (so “Your touring call” is on-screen)
      requestAnimationFrame(() => {
        resultEl.scrollIntoView({ behavior: "smooth", block: "start" });
      });

    } catch (err) {
      progress.stop("error");

      const msg = (err && err.message) ? err.message : "Unknown error";
      resultEl.innerHTML =
        '<div class="tb-card">' +
          '<h2 style="margin-top:0">Sorry — we couldn’t get a touring call right now.</h2>' +
          '<p class="tb-summary-text">' + esc(msg) + '</p>' +
          '<p class="tb-helper-text" style="margin-top:0.6rem;">' +
            'Tip: if this keeps happening, check your backend console for the real error.' +
          '</p>' +
        '</div>';
    }
  });
});
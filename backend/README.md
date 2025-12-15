Touring Brain – Backend v0 Cheat Sheet

What exists right now

FastAPI app with these core pieces:
	•	Caravan Mode – 3-day towing/camping forecast at a single location.
	•	Touring Mode – Compares A → B on a travel day, plus suggested alternatives (currently canned).
	•	Daily Briefing – 3-day local outlook with comfort labels.
	•	Towing & Loading Advisor – Caravan + motorhome safety checks.
	•	Health check – Simple uptime endpoint.

All running locally at:
http://127.0.0.1:8000
Docs: http://127.0.0.1:8000/docs

⸻

	1.	Health Check
Endpoint:
GET /health

Use:
Quick “is the backend alive?” ping.

⸻

	2.	Caravan Mode – 3-Day Towing Forecast

Endpoint:
POST /caravan/forecast

Request example:
location name Wanaka, latitude -44.697, longitude 169.135, days_ahead 3

Response shape simplified:
location (Wanaka)
days each containing:
date,
rain_mm,
wind_avg_kmh,
wind_gust_kmh,
towing_stress (0-100),
overnight_temp_c,
ai_summary
recommendation line (park up vs similar days)

What it does:
	•	Hits Open-Meteo for daily data
	•	Calculates towing stress based on wind + gusts + rain
	•	AI summary per day
	•	Simple recommendation (park-up or not)

⸻

	3.	Touring Mode – A → B Planning

Endpoint:
POST /touring/plan

Request example:
from_location (name, lat, lon)
to_location (name, lat, lon)
travel_day_iso e.g. 2025-12-09
max_drive_hours e.g. 4.0

Response shape simplified:
from_summary (weather + towing stress + AI summary + park_up_flag)
to_summary (same)
comparison (better_for_towing, reason)
recommendation (decision: go_to_destination or consider_alternatives)
alternatives[] list of locations with drive time and towing stress (currently canned suggestions e.g. Cromwell, Twizel)

What it does now:
	•	Real Open-Meteo for from and to
	•	Compares towing stress
	•	Simple recommendations
	•	Stubbed alternatives for now (can be replaced with real drive logic)

⸻

	4.	Daily Briefing – 3-Day Local Outlook

Endpoint:
POST /briefing/daily

Request example:
location name Wanaka, latitude -44.697, longitude 169.135, days_ahead 3

Response shape simplified:
location
days[] each:
date
rain_mm
wind_avg_kmh
wind_gust_kmh
overnight_temp_c
towing_stress
comfort_label (good, ok with care, park up)
ai_summary
headline
recommendation

What it does:
	•	Same weather + stress engine
	•	Comfort labels
	•	Headline + recommendation for next few days

⸻

	5.	Towing & Loading Advisor

Endpoint:
POST /towing/evaluate

Supports:
rig_type: towed_caravan
rig_type: motorhome
rig_type: campervan (alias handled same as motorhome)

Example – Car + Caravan

rig_type towed_caravan
vehicle label 2023 Ford Ranger 3.2, tow_rating_braked_kg 3500, max_ball_weight_kg 250
caravan label Jayco Journey 19.6, atm_kg 2600, loaded_estimate_kg 2400, ball_weight_kg 230
extras rear_load_kg 20, num_ebikes 0, front_storage_heavy false, water_front_tank_litres 20

Response:
status near_limits
risk_colour amber
ball_weight_percent_of_atm about 8.8
ball_weight_percent_of_loaded about 9.6
checks includes tow_rating ok, ball_weight ok, rear_load ok, front_load near_limit
advice summary “close to limits”
inputs_echo echoes payload
disclaimer towing-specific guidance

Example – Motorhome

rig_type motorhome
motorhome label Fiat Ducato Motorhome 7.2m, gvm_kg 4495, current_weight_kg 4300, front_axle_rating_kg 2100, front_axle_actual_kg 1950, rear_axle_rating_kg 2500, rear_axle_actual_kg 2350, rear_overhang_m 2.3
extras rear_load_kg 40, num_ebikes 2, water_rear_tank_litres 80

Response:
status near_limits
risk_colour amber
checks include combined_mass near GVM, front/rear axle near limits, rear_load near (due to long overhang)
advice mentions axle load, rear leverage, and to get weighed
disclaimer motorhome-specific guidance

⸻

Where we’re at

Backend v0 now has:
	•	Real weather-driven Caravan Mode
	•	Real weather-driven Touring Mode (with stubbed alternatives)
	•	Real weather-driven Daily Briefing
	•	Towing Advisor with:
	•	Car + caravan logic
	•	Motorhome logic
	•	Rear loads, e-bikes, front storage/water
	•	Amber/red guidance
	•	Disclaimers

⸻

Suggested next moves:
	1.	Add this cheat sheet into backend/README.md so future you sees all endpoints and payloads quickly.
	2.	Then decide between:
	•	Simple web UI MVP
	•	Smarter touring alternatives (real locations + drive times)
	•	Marketing / landing content (NZ caravan crowd)

⸻

END OF COPY
from typing import Dict, Any

import httpx

OPEN_METEO_BASE_URL = "https://api.open-meteo.com/v1/forecast"


async def get_daily_weather(latitude: float, longitude: float, days: int = 3) -> Dict[str, Any]:
    """
    Fetch daily weather data from Open-Meteo for the given location.

    We request:
    - daily precipitation (rain)
    - daily max wind speed at 10m
    - daily max wind gusts at 10m
    - daily minimum temperature
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": ",".join(
            [
                "precipitation_sum",
                "wind_speed_10m_max",
                "wind_gusts_10m_max",
                "temperature_2m_min",
            ]
        ),
        "forecast_days": days,
        "timezone": "auto",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(OPEN_METEO_BASE_URL, params=params)
        response.raise_for_status()
        data = response.json()

    if "daily" not in data:
        raise ValueError("Unexpected response from Open-Meteo: 'daily' block missing")

    return data["daily"]
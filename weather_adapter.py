"""Weather Adapter Module.

Handles all HTTP communication with the Open-Meteo API.
Provides geocoding, current weather, and forecast data as clean dicts.
No MCP logic belongs here — this is a pure data-fetching layer.

API Reference:
    - Forecast: https://api.open-meteo.com/v1/forecast
    - Geocoding: https://geocoding-api.open-meteo.com/v1/search
"""

import httpx
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

HTTP_TIMEOUT = 15.0  # seconds

# WMO Weather interpretation codes → human-readable descriptions
WMO_CODES: dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Foggy",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snowfall",
    73: "Moderate snowfall",
    75: "Heavy snowfall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


# ---------------------------------------------------------------------------
# Geocoding
# ---------------------------------------------------------------------------


def geocode(location: str) -> dict[str, Any]:
    """Resolve a city/place name to latitude, longitude, and metadata.

    Args:
        location: City name, optionally with country (e.g. "Paris, France").

    Returns:
        Dict with keys: name, latitude, longitude, country, timezone.

    Raises:
        ValueError: If the location cannot be resolved.
        RuntimeError: If the geocoding API request fails.
    """
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT) as client:
            resp = client.get(GEOCODING_URL, params={"name": location, "count": 1})
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Geocoding API request failed: {exc}") from exc

    data = resp.json()
    results = data.get("results")
    if not results:
        raise ValueError(
            f"Could not resolve location '{location}'. "
            "Try a more specific name (e.g. 'Austin, Texas' instead of 'Austin')."
        )

    hit = results[0]
    return {
        "name": hit.get("name", location),
        "latitude": hit["latitude"],
        "longitude": hit["longitude"],
        "country": hit.get("country", "Unknown"),
        "admin1": hit.get("admin1", ""),
        "timezone": hit.get("timezone", "UTC"),
    }


# ---------------------------------------------------------------------------
# Current Weather
# ---------------------------------------------------------------------------


def get_current_weather(latitude: float, longitude: float) -> dict[str, Any]:
    """Fetch current weather conditions for a coordinate pair.

    Args:
        latitude: Latitude in decimal degrees.
        longitude: Longitude in decimal degrees.

    Returns:
        Dict with keys: temperature_c, feels_like_c, humidity_pct,
        wind_speed_kmh, wind_direction_deg, condition, weather_code.

    Raises:
        RuntimeError: If the weather API request fails.
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": (
            "temperature_2m,relative_humidity_2m,apparent_temperature,"
            "weather_code,wind_speed_10m,wind_direction_10m"
        ),
        "timezone": "auto",
    }

    try:
        with httpx.Client(timeout=HTTP_TIMEOUT) as client:
            resp = client.get(FORECAST_URL, params=params)
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Weather API request failed: {exc}") from exc

    current = resp.json().get("current", {})
    weather_code = current.get("weather_code", 0)

    return {
        "temperature_c": current.get("temperature_2m"),
        "feels_like_c": current.get("apparent_temperature"),
        "humidity_pct": current.get("relative_humidity_2m"),
        "wind_speed_kmh": current.get("wind_speed_10m"),
        "wind_direction_deg": current.get("wind_direction_10m"),
        "weather_code": weather_code,
        "condition": WMO_CODES.get(weather_code, "Unknown"),
    }


# ---------------------------------------------------------------------------
# Multi-day Forecast
# ---------------------------------------------------------------------------


def get_forecast(latitude: float, longitude: float, days: int = 7) -> list[dict[str, Any]]:
    """Fetch a multi-day daily forecast for a coordinate pair.

    Args:
        latitude: Latitude in decimal degrees.
        longitude: Longitude in decimal degrees.
        days: Number of forecast days (1-16, default 7).

    Returns:
        List of dicts, one per day, with keys: date, temp_max_c, temp_min_c,
        precipitation_probability_pct, precipitation_sum_mm, condition,
        weather_code, wind_speed_max_kmh, uv_index_max.

    Raises:
        RuntimeError: If the weather API request fails.
    """
    days = max(1, min(days, 16))  # Open-Meteo supports 1-16 days

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": (
            "temperature_2m_max,temperature_2m_min,precipitation_probability_max,"
            "precipitation_sum,weather_code,wind_speed_10m_max,uv_index_max"
        ),
        "timezone": "auto",
        "forecast_days": days,
    }

    try:
        with httpx.Client(timeout=HTTP_TIMEOUT) as client:
            resp = client.get(FORECAST_URL, params=params)
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Weather API request failed: {exc}") from exc

    daily = resp.json().get("daily", {})
    dates = daily.get("time", [])

    forecast_days = []
    for i, date in enumerate(dates):
        weather_code = daily["weather_code"][i] if daily.get("weather_code") else 0
        forecast_days.append({
            "date": date,
            "temp_max_c": daily.get("temperature_2m_max", [None])[i],
            "temp_min_c": daily.get("temperature_2m_min", [None])[i],
            "precipitation_probability_pct": daily.get("precipitation_probability_max", [None])[i],
            "precipitation_sum_mm": daily.get("precipitation_sum", [None])[i],
            "weather_code": weather_code,
            "condition": WMO_CODES.get(weather_code, "Unknown"),
            "wind_speed_max_kmh": daily.get("wind_speed_10m_max", [None])[i],
            "uv_index_max": daily.get("uv_index_max", [None])[i],
        })

    return forecast_days


# ---------------------------------------------------------------------------
# Travel Recommendation Logic
# ---------------------------------------------------------------------------

# Thresholds for recommendations
UMBRELLA_PRECIP_THRESHOLD = 40  # precipitation probability %
JACKET_TEMP_THRESHOLD = 15  # degrees C
HEAVY_COAT_TEMP_THRESHOLD = 5  # degrees C
WIND_CHILL_THRESHOLD = 30  # km/h — wind makes it feel colder
SUNSCREEN_UV_THRESHOLD = 5  # UV index
HEAT_ADVISORY_THRESHOLD = 35  # degrees C
LAYERS_SWING_THRESHOLD = 10  # temp difference max-min in a day


def build_recommendations(forecast_days: list[dict[str, Any]]) -> dict[str, Any]:
    """Analyze forecast data and produce actionable travel recommendations.

    Applies threshold-based logic to raw forecast data to generate
    packing/planning advice for travelers.

    Args:
        forecast_days: List of daily forecast dicts (from get_forecast).

    Returns:
        Dict with keys: summary, items_to_pack (list), daily_advice (list),
        alerts (list), overall_rating (str).
    """
    items_to_pack: set[str] = set()
    daily_advice: list[dict[str, Any]] = []
    alerts: list[str] = []

    rain_days = 0
    hot_days = 0
    cold_days = 0

    for day in forecast_days:
        advice_items: list[str] = []
        temp_max = day.get("temp_max_c") or 0
        temp_min = day.get("temp_min_c") or 0
        precip_prob = day.get("precipitation_probability_pct") or 0
        wind_max = day.get("wind_speed_max_kmh") or 0
        uv_max = day.get("uv_index_max") or 0
        temp_swing = temp_max - temp_min

        # Rain / umbrella logic
        if precip_prob >= UMBRELLA_PRECIP_THRESHOLD:
            items_to_pack.add("Umbrella / rain jacket")
            advice_items.append(f"Rain likely ({precip_prob}% chance) — carry rain gear")
            rain_days += 1

        # Cold / jacket logic
        if temp_min < HEAVY_COAT_TEMP_THRESHOLD:
            items_to_pack.add("Heavy winter coat")
            items_to_pack.add("Warm layers (fleece, thermals)")
            advice_items.append(f"Very cold (low {temp_min}°C) — bundle up")
            cold_days += 1
        elif temp_min < JACKET_TEMP_THRESHOLD:
            items_to_pack.add("Light jacket or sweater")
            advice_items.append(f"Cool temperatures (low {temp_min}°C) — bring a jacket")
            cold_days += 1

        # Wind chill
        if wind_max >= WIND_CHILL_THRESHOLD:
            items_to_pack.add("Windbreaker")
            advice_items.append(f"Windy conditions ({wind_max} km/h) — windbreaker recommended")

        # UV / sunscreen
        if uv_max >= SUNSCREEN_UV_THRESHOLD:
            items_to_pack.add("Sunscreen (SPF 30+)")
            items_to_pack.add("Sunglasses")
            advice_items.append(f"High UV index ({uv_max}) — apply sunscreen")

        # Heat advisory
        if temp_max >= HEAT_ADVISORY_THRESHOLD:
            items_to_pack.add("Water bottle")
            items_to_pack.add("Light breathable clothing")
            advice_items.append(f"Hot day ({temp_max}°C) — stay hydrated")
            alerts.append(f"{day['date']}: Heat advisory — high of {temp_max}°C")
            hot_days += 1

        # Layer logic
        if temp_swing >= LAYERS_SWING_THRESHOLD:
            items_to_pack.add("Layers (temperature varies significantly)")
            advice_items.append(
                f"Large temperature swing ({temp_min}°C to {temp_max}°C) — dress in layers"
            )

        daily_advice.append({
            "date": day["date"],
            "condition": day["condition"],
            "advice": advice_items if advice_items else ["No special precautions needed"],
        })

    # Overall rating
    total_days = len(forecast_days)
    if rain_days > total_days / 2:
        overall_rating = "Rainy — plan indoor alternatives"
    elif hot_days > total_days / 2:
        overall_rating = "Hot — prioritize shade and hydration"
    elif cold_days > total_days / 2:
        overall_rating = "Cold — pack warm clothing"
    elif rain_days == 0 and cold_days == 0 and hot_days == 0:
        overall_rating = "Pleasant — great conditions for outdoor activities"
    else:
        overall_rating = "Mixed — pack for varying conditions"

    # Build summary
    summary_parts = []
    if rain_days:
        summary_parts.append(f"{rain_days}/{total_days} days with rain expected")
    if hot_days:
        summary_parts.append(f"{hot_days}/{total_days} days with high heat")
    if cold_days:
        summary_parts.append(f"{cold_days}/{total_days} days with cold temperatures")
    if not summary_parts:
        summary_parts.append("Generally mild and dry conditions throughout")

    return {
        "summary": "; ".join(summary_parts),
        "overall_rating": overall_rating,
        "items_to_pack": sorted(items_to_pack),
        "daily_advice": daily_advice,
        "alerts": alerts,
    }

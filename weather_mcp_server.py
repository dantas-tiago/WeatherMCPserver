"""Weather Prediction MCP Server.

Exposes weather-forecast tools via the Model Context Protocol (MCP)
using FastMCP with streamable-HTTP transport. Designed for deployment
as a Databricks App and consumption by Agent Bricks agents.

Tools:
    - get_current_weather: Current conditions for a location.
    - get_forecast: Multi-day forecast for a location.
    - get_travel_recommendation: Packing/planning advice derived from forecast.
    - compare_weather: Side-by-side comparison of multiple cities (stretch).
"""

import os

from fastmcp import FastMCP

import weather_adapter as adapter
import db_logger

# ---------------------------------------------------------------------------
# Server Setup
# ---------------------------------------------------------------------------

mcp = FastMCP(
    name="Weather Prediction MCP Server",
    instructions=(
        "This server provides real-time weather data and travel recommendations. "
        "Use get_current_weather for live conditions, get_forecast for multi-day "
        "outlooks, and get_travel_recommendation for actionable packing/planning advice. "
        "All tools accept a location as a city name (e.g. 'Chicago', 'Austin, Texas'). "
        "If a location cannot be resolved, the tool will return an error message."
    ),
)


# ---------------------------------------------------------------------------
# Tool: get_current_weather
# ---------------------------------------------------------------------------


@mcp.tool
def get_current_weather(location: str) -> dict:
    """Get current weather conditions for a given location.

    Returns temperature, feels-like temperature, humidity, wind speed/direction,
    and a human-readable condition description.

    Args:
        location: City name, optionally with state/country
                  (e.g. "Chicago", "Austin, Texas", "Paris, France").

    Returns:
        Dict with location metadata and current weather data including:
        - temperature_c: Current temperature in Celsius
        - feels_like_c: Apparent temperature in Celsius
        - humidity_pct: Relative humidity percentage
        - wind_speed_kmh: Wind speed in km/h
        - wind_direction_deg: Wind direction in degrees
        - condition: Human-readable weather condition
    """
    with db_logger.RequestTimer("get_current_weather", location=location) as timer:
        try:
            geo = adapter.geocode(location)
        except ValueError as exc:
            timer.set_error(str(exc))
            return {"error": str(exc)}
        except RuntimeError as exc:
            timer.set_error(f"Geocoding service unavailable: {exc}")
            return {"error": f"Geocoding service unavailable: {exc}"}

        timer.set_resolved(f"{geo['name']}, {geo['country']}")

        try:
            weather = adapter.get_current_weather(geo["latitude"], geo["longitude"])
        except RuntimeError as exc:
            timer.set_error(f"Weather service unavailable: {exc}")
            return {"error": f"Weather service unavailable: {exc}"}

        return {
            "location": {
                "name": geo["name"],
                "country": geo["country"],
                "region": geo["admin1"],
                "coordinates": {"lat": geo["latitude"], "lon": geo["longitude"]},
            },
            "current": weather,
        }


# ---------------------------------------------------------------------------
# Tool: get_forecast
# ---------------------------------------------------------------------------


@mcp.tool
def get_forecast(location: str, days: int = 7) -> dict:
    """Get a multi-day weather forecast for a given location.

    Returns daily high/low temperatures, precipitation probability,
    wind speed, UV index, and conditions for the next N days.

    Args:
        location: City name, optionally with state/country
                  (e.g. "Seattle", "London, UK").
        days: Number of forecast days (1-16, default 7).

    Returns:
        Dict with location metadata and a list of daily forecasts,
        each containing:
        - date: ISO date string (YYYY-MM-DD)
        - temp_max_c / temp_min_c: High/low temperatures
        - precipitation_probability_pct: Chance of rain/snow
        - precipitation_sum_mm: Expected total precipitation
        - wind_speed_max_kmh: Max wind speed
        - uv_index_max: Peak UV index
        - condition: Human-readable condition
    """
    with db_logger.RequestTimer("get_forecast", location=location, days=days) as timer:
        try:
            geo = adapter.geocode(location)
        except ValueError as exc:
            timer.set_error(str(exc))
            return {"error": str(exc)}
        except RuntimeError as exc:
            timer.set_error(f"Geocoding service unavailable: {exc}")
            return {"error": f"Geocoding service unavailable: {exc}"}

        timer.set_resolved(f"{geo['name']}, {geo['country']}")

        try:
            forecast = adapter.get_forecast(geo["latitude"], geo["longitude"], days=days)
        except RuntimeError as exc:
            timer.set_error(f"Weather service unavailable: {exc}")
            return {"error": f"Weather service unavailable: {exc}"}

        return {
            "location": {
                "name": geo["name"],
                "country": geo["country"],
                "region": geo["admin1"],
                "coordinates": {"lat": geo["latitude"], "lon": geo["longitude"]},
            },
            "forecast_days": forecast,
        }


# ---------------------------------------------------------------------------
# Tool: get_travel_recommendation
# ---------------------------------------------------------------------------


@mcp.tool
def get_travel_recommendation(location: str, days: int = 5) -> dict:
    """Get travel packing and planning recommendations for a location.

    Analyzes the forecast and applies threshold-based logic to produce
    actionable advice:
    - Umbrella needed if precipitation probability > 40%
    - Jacket recommended if temperature drops below 15°C
    - Heavy coat if below 5°C
    - Sunscreen if UV index >= 5
    - Hydration alert if temperature exceeds 35°C
    - Layers advised if daily temperature swing > 10°C

    Args:
        location: City name, optionally with state/country
                  (e.g. "Miami", "Tokyo, Japan").
        days: Number of days to analyze (1-16, default 5).

    Returns:
        Dict with:
        - location: Resolved location metadata
        - summary: One-line overview of conditions
        - overall_rating: Qualitative rating (Pleasant, Mixed, Rainy, etc.)
        - items_to_pack: List of recommended items
        - daily_advice: Per-day breakdown with specific tips
        - alerts: Any severe-weather advisories
    """
    with db_logger.RequestTimer("get_travel_recommendation", location=location, days=days) as timer:
        try:
            geo = adapter.geocode(location)
        except ValueError as exc:
            timer.set_error(str(exc))
            return {"error": str(exc)}
        except RuntimeError as exc:
            timer.set_error(f"Geocoding service unavailable: {exc}")
            return {"error": f"Geocoding service unavailable: {exc}"}

        timer.set_resolved(f"{geo['name']}, {geo['country']}")

        try:
            forecast = adapter.get_forecast(geo["latitude"], geo["longitude"], days=days)
        except RuntimeError as exc:
            timer.set_error(f"Weather service unavailable: {exc}")
            return {"error": f"Weather service unavailable: {exc}"}

        recommendations = adapter.build_recommendations(forecast)

        return {
            "location": {
                "name": geo["name"],
                "country": geo["country"],
                "region": geo["admin1"],
            },
            **recommendations,
        }


# ---------------------------------------------------------------------------
# Tool: compare_weather (stretch)
# ---------------------------------------------------------------------------


@mcp.tool
def compare_weather(locations: list[str], days: int = 3) -> dict:
    """Compare weather forecasts across multiple cities side by side.

    Useful for deciding between travel destinations or understanding
    regional weather differences.

    Args:
        locations: List of city names to compare (2-5 cities).
        days: Number of forecast days to compare (1-7, default 3).

    Returns:
        Dict with a comparison table: for each city, the forecast summary
        and overall rating. Includes a 'best_pick' recommendation.
    """
    with db_logger.RequestTimer("compare_weather", location=",".join(locations), days=days) as timer:
        if len(locations) < 2:
            timer.set_error("Provide at least 2 locations to compare.")
            return {"error": "Provide at least 2 locations to compare."}
        if len(locations) > 5:
            timer.set_error("Maximum 5 locations for comparison.")
            return {"error": "Maximum 5 locations for comparison."}

        days = max(1, min(days, 7))
        results = []

        for loc in locations:
            try:
                geo = adapter.geocode(loc)
                forecast = adapter.get_forecast(geo["latitude"], geo["longitude"], days=days)
                recs = adapter.build_recommendations(forecast)
                results.append({
                    "location": f"{geo['name']}, {geo['country']}",
                    "overall_rating": recs["overall_rating"],
                    "summary": recs["summary"],
                    "items_to_pack": recs["items_to_pack"],
                    "avg_high_c": round(
                        sum(d["temp_max_c"] for d in forecast if d["temp_max_c"]) / len(forecast), 1
                    ),
                    "avg_low_c": round(
                        sum(d["temp_min_c"] for d in forecast if d["temp_min_c"]) / len(forecast), 1
                    ),
                    "rain_days": sum(
                        1 for d in forecast
                        if (d.get("precipitation_probability_pct") or 0) >= 40
                    ),
                })
            except (ValueError, RuntimeError) as exc:
                results.append({"location": loc, "error": str(exc)})

        # Pick the "best" destination (fewest rain days, pleasant rating preferred)
        valid = [r for r in results if "error" not in r]
        best_pick = None
        if valid:
            pleasant = [r for r in valid if "Pleasant" in r["overall_rating"]]
            if pleasant:
                best_pick = min(pleasant, key=lambda r: r["rain_days"])["location"]
            else:
                best_pick = min(valid, key=lambda r: r["rain_days"])["location"]

        timer.set_resolved(best_pick or ",".join(locations))

        return {
            "comparison": results,
            "best_pick": best_pick,
            "note": "Best pick is based on fewest rain days and most pleasant conditions.",
        }


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    port = int(os.environ.get("PORT", 8000))

    async def health_check(request):
        """Health check / service discovery endpoint."""
        return JSONResponse({
            "status": "healthy",
            "service": "Weather Prediction MCP Server",
            "version": "1.0.0",
            "mcp_endpoint": "/mcp",
            "transport": "streamable-http",
            "tools": [
                "get_current_weather",
                "get_forecast",
                "get_travel_recommendation",
                "compare_weather",
            ],
        })

    # Build the ASGI app from FastMCP and inject health routes
    app = mcp.http_app(path="/mcp", transport="streamable-http")
    app.routes.insert(0, Route("/", health_check, methods=["GET"]))
    app.routes.insert(1, Route("/health", health_check, methods=["GET"]))

    uvicorn.run(app, host="0.0.0.0", port=port)

# Weather Prediction MCP Server

A Model Context Protocol (MCP) server that exposes weather-forecast tools, designed for consumption by a Databricks Agent Bricks agent. Deployed as a Databricks App.

## Architecture

```
┌───────────────────────────────────────────────────────────────────┐
│  User (natural language)                                         │
│       │                                                          │
│       v                                                          │
│  Agent Bricks Agent (system_prompt.txt)                          │
│       │  MCP tool calls (streamable-HTTP)                        │
│       v                                                          │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │  weather_mcp_server.py (FastMCP, Databricks App)       │   │
│  │    ├─ get_current_weather(location)                     │   │
│  │    ├─ get_forecast(location, days)                      │   │
│  │    ├─ get_travel_recommendation(location, days)         │   │
│  │    └─ compare_weather(locations, days)                  │   │
│  └───────────────────────────────────────────────────────────┘   │
│       │                                                          │
│       v                                                          │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │  weather_adapter.py (HTTP layer)                        │   │
│  │    ├─ geocode(location) → lat/lon                       │   │
│  │    ├─ get_current_weather(lat, lon)                     │   │
│  │    ├─ get_forecast(lat, lon, days)                      │   │
│  │    └─ build_recommendations(forecast)                   │   │
│  └───────────────────────────────────────────────────────────┘   │
│       │                                                          │
│       v                                                          │
│  Open-Meteo API (free, no key required)                          │
│    ├─ geocoding-api.open-meteo.com/v1/search                     │
│    └─ api.open-meteo.com/v1/forecast                              │
└───────────────────────────────────────────────────────────────────┘
```

## Weather API

**Open-Meteo** — chosen because:
- Zero signup, zero API keys, zero cost
- ~10,000 calls/day (non-commercial)
- Global coverage (not US-only)
- Provides geocoding, current weather, and 16-day forecasts in one API family

## Tools

| Tool | Purpose | Key Inputs |
|------|---------|------------|
| `get_current_weather` | Live conditions (temp, wind, humidity) | `location` |
| `get_forecast` | Multi-day daily forecast | `location`, `days` (1-16) |
| `get_travel_recommendation` | Packing/planning advice with thresholds | `location`, `days` (1-16) |
| `compare_weather` | Side-by-side city comparison | `locations` (list), `days` |

### Recommendation Thresholds

| Condition | Threshold | Advice |
|-----------|-----------|--------|
| Rain | Precip probability > 40% | Bring umbrella/rain jacket |
| Cold | Temp < 15°C | Light jacket |
| Very cold | Temp < 5°C | Heavy coat + thermals |
| Windy | Wind > 30 km/h | Windbreaker |
| High UV | UV index ≥ 5 | Sunscreen + sunglasses |
| Heat | Temp > 35°C | Hydration alert |
| Variable | Day swing > 10°C | Dress in layers |

## Project Structure

```
WeatherMCPserver/
├── weather_adapter.py       # HTTP layer: Open-Meteo API calls + geocoding + logic
├── weather_mcp_server.py    # FastMCP server with @mcp.tool decorators
├── pyproject.toml           # UV package management
├── app.yaml                 # Databricks App deployment config
├── system_prompt.txt        # Agent Bricks system prompt
└── README.md                # This file
```

## Setup & Deployment

### Prerequisites

- Databricks workspace with Apps enabled
- UV installed (`pip install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- No API keys needed (Open-Meteo is key-free)

### Local Development

```bash
# Install dependencies
uv sync

# Run the MCP server locally
uv run weather_mcp_server.py

# Server starts on http://localhost:8000
# MCP endpoint: http://localhost:8000/mcp
```

### Deploy as Databricks App

```bash
# From the workspace, deploy the app
databricks apps create weather-mcp-server \
  --source-code-path /Workspace/Users/<your-email>/WeatherMCPserver

# Or deploy via the Apps UI:
# 1. Go to Compute > Apps > Create App
# 2. Point source to this folder
# 3. The app.yaml handles the rest
```

### Register as External MCP Tool in Agent Bricks

1. Navigate to your Agent Bricks agent configuration
2. Add an External MCP connection:
   - **URL**: `https://<your-app-url>/mcp`
   - **Transport**: Streamable HTTP
3. Paste the contents of `system_prompt.txt` as the agent's system prompt
4. Test with: "What's the weather in Tokyo right now?"

## Example Queries

**Current conditions:**
> "What's the temperature in Berlin right now?"

**Forecast:**
> "Will it rain in Chicago this week?"

**Travel advice:**
> "I'm traveling to Austin, Texas for 3 days. What should I pack?"

**Comparison:**
> "Which has better weather this weekend: Miami, LA, or Denver?"

**Edge cases (handled gracefully):**
> "What's the weather in Xyzzyville?" → Error: location not found, suggests being more specific.

## Authentication & Secrets

**None required.** Open-Meteo needs no API key. If you later add a keyed API (e.g. WeatherAPI.com), store the key as a Databricks secret:

```python
from databricks.sdk import WorkspaceClient
w = WorkspaceClient()
api_key = w.secrets.get_secret(scope="weather", key="api_key").value
```

Never hardcode keys in source files.

## Lakebase Integration (Optional)

Query history can be stored in the provisioned Lakebase Postgres instance for dashboard/analytics:

```
Host: ep-gentle-paper-e1xaec1l.database.eastus2.azuredatabricks.net
Database: databricks_postgres
User: WeatherMCPserver
```

## License

Internal project — Databricks learning challenge submission.

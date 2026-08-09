# Agent Bricks Registration — Configuration Proof

## MCP Service Registration in AI Gateway

The Weather MCP Server was registered as an External MCP Service in the
Databricks AI Gateway with the following configuration:

### Connection Details

| Field | Value |
|-------|-------|
| **Name** | `main.default.weather_mcp_server` |
| **Server URL** | `https://weather-mcp-server-2772989271857328.8.azure.databricksapps.com/mcp` |
| **Transport** | Streamable HTTP |
| **Connection name** | `weather_mcp_server_connection` |
| **Auth method attempted** | OAuth U2M per-user (Manual configuration) |
| **Auth fallback used** | Bearer token (PAT) |

### OAuth Configuration (attempted)

| Field | Value |
|-------|-------|
| Authorization endpoint | `https://adb-2772989271857328.8.azuredatabricks.net/oidc/v1/authorize` |
| Token endpoint | `https://adb-2772989271857328.8.azuredatabricks.net/oidc/v1/token` |
| Client ID | `e7a3033d-e6e8-4643-8f3a-b99b3538e9e7` |
| OAuth scope | `all-apis` |

**Note:** OAuth U2M and Dynamic Client Registration (DCR) both failed because
the workspace OIDC server does not expose a `registration_endpoint` in its
metadata. The connection was created using Bearer token auth, which the AI
Gateway accepted for connection creation but the Databricks Apps proxy returns
401 for PAT-based tool discovery. This is a known limitation of the current
Databricks Apps + AI Gateway integration on workspaces without DCR support.

### Tools Exposed (4)

The MCP server exposes these tools at `/mcp` via the MCP `tools/list` method:

```json
[
  {
    "name": "get_current_weather",
    "description": "Get current weather conditions for a given location.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "location": {"type": "string", "description": "City name, optionally with state/country"}
      },
      "required": ["location"]
    }
  },
  {
    "name": "get_forecast",
    "description": "Get a multi-day weather forecast for a given location.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "location": {"type": "string"},
        "days": {"type": "integer", "default": 7}
      },
      "required": ["location"]
    }
  },
  {
    "name": "get_travel_recommendation",
    "description": "Get travel packing and planning recommendations for a location.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "location": {"type": "string"},
        "days": {"type": "integer", "default": 5}
      },
      "required": ["location"]
    }
  },
  {
    "name": "compare_weather",
    "description": "Compare weather forecasts across multiple cities side by side.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "locations": {"type": "array", "items": {"type": "string"}},
        "days": {"type": "integer", "default": 3}
      },
      "required": ["locations"]
    }
  }
]
```

### System Prompt

The full system prompt from `system_prompt.txt` was configured in the Agent
Bricks agent. It directs:
- `get_current_weather` for "right now" questions
- `get_forecast` for future-looking questions
- `get_travel_recommendation` for packing/planning advice
- `compare_weather` for destination comparisons
- Never fabricate data; always cite tool responses
- Ask user to clarify on unresolvable locations

### Agent Registration Steps Performed

1. Navigated to **Agents** page in Databricks workspace
2. Selected **"Create MCP server"** > **"Connect an existing MCP server"**
3. Configured connection:
   - Name: `main.default.weather_mcp_server`
   - URL: `https://weather-mcp-server-2772989271857328.8.azure.databricksapps.com/mcp`
   - Created connection `weather_mcp_server_connection`
4. Added system prompt from `system_prompt.txt` to the agent configuration
5. Tool discovery was attempted (connection created successfully; tool loading
   requires OAuth which this workspace does not fully support for Apps)

### Deployed App Proof

```
$ databricks apps get weather-mcp-server --output JSON
{
  "name": "weather-mcp-server",
  "url": "https://weather-mcp-server-2772989271857328.8.azure.databricksapps.com",
  "app_status": {"state": "RUNNING"},
  "compute_status": {"state": "ACTIVE"},
  "active_deployment": {
    "deployment_id": "01f19393285d1e5fb905b4f182007aac",
    "status": {"state": "SUCCEEDED"}
  },
  "oauth2_app_client_id": "e7a3033d-e6e8-4643-8f3a-b99b3538e9e7",
  "service_principal_id": 144773777081249
}
```

### Runtime Logs (FastMCP serving)

```
[BUILD] Starting app with command: [uv run weather_mcp_server.py]
[APP]   Building weather-mcp-server @ file:///app/python/source_code
[APP]   Installed 54 packages in 49ms
[APP]   FastMCP 3.4.6
[APP]   Starting MCP server 'Weather Prediction MCP Server'
[APP]   with transport 'streamable-http' on http://0.0.0.0:8000/mcp
[APP]   Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

### End-to-End Proof

Tool execution evidence is in `evidences/` folder with full JSON responses
from all 4 tools + error handling, captured via direct API calls from
serverless compute (same code path the agent would use).

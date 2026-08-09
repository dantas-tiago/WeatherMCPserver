"""Weather MCP Server Dashboard.

Streamlit dashboard showing request analytics from the Lakebase Postgres
request_logs table. Deployed as a companion Databricks App.
"""

import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import psycopg2
import streamlit as st

# ---------------------------------------------------------------------------
# Page Config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Weather MCP Dashboard",
    page_icon="\u2601\ufe0f",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Database Connection
# ---------------------------------------------------------------------------


@st.cache_resource
def get_connection():
    """Create a persistent database connection."""
    return psycopg2.connect(
        host=os.environ.get("PGHOST", "localhost"),
        database=os.environ.get("PGDATABASE", "databricks_postgres"),
        user=os.environ.get("PGUSER", "WeatherMCPserver"),
        password=os.environ.get("PGPASSWORD", ""),
        sslmode="require",
    )


def run_query(query: str) -> pd.DataFrame:
    """Execute a query and return results as a DataFrame."""
    conn = get_connection()
    try:
        return pd.read_sql_query(query, conn)
    except Exception:
        # Reconnect on stale connection
        conn.close()
        st.cache_resource.clear()
        conn = get_connection()
        return pd.read_sql_query(query, conn)


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.title("\u2601\ufe0f Weather MCP Server Dashboard")
st.caption("Real-time analytics from the Weather Prediction MCP Server request logs")

# ---------------------------------------------------------------------------
# KPI Row
# ---------------------------------------------------------------------------

kpi_df = run_query("""
    SELECT 
        COUNT(*) as total_requests,
        COUNT(*) FILTER (WHERE success) as successful,
        COUNT(*) FILTER (WHERE NOT success) as failed,
        ROUND(AVG(response_time_ms)::numeric, 0) as avg_response_ms,
        COUNT(DISTINCT location_query) as unique_locations
    FROM request_logs;
""")

if not kpi_df.empty:
    row = kpi_df.iloc[0]
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total Requests", int(row["total_requests"]))
    col2.metric("Successful", int(row["successful"]))
    col3.metric("Failed", int(row["failed"]))
    col4.metric("Avg Response (ms)", int(row["avg_response_ms"]) if row["avg_response_ms"] else 0)
    col5.metric("Unique Locations", int(row["unique_locations"]))

st.divider()

# ---------------------------------------------------------------------------
# Charts Row 1: Volume Over Time + Success Rate by Tool
# ---------------------------------------------------------------------------

chart_col1, chart_col2 = st.columns(2)

with chart_col1:
    st.subheader("Request Volume Over Time")
    volume_df = run_query("""
        SELECT 
            DATE_TRUNC('hour', timestamp) as hour,
            COUNT(*) as requests,
            COUNT(*) FILTER (WHERE success) as successful,
            COUNT(*) FILTER (WHERE NOT success) as failed
        FROM request_logs
        GROUP BY 1
        ORDER BY 1;
    """)
    if not volume_df.empty:
        fig = px.bar(
            volume_df, x="hour", y=["successful", "failed"],
            barmode="stack",
            color_discrete_map={"successful": "#2ecc71", "failed": "#e74c3c"},
            labels={"value": "Requests", "hour": "Time"},
        )
        fig.update_layout(legend_title_text="Status", height=300)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No data yet.")

with chart_col2:
    st.subheader("Requests by Tool")
    tool_df = run_query("""
        SELECT 
            tool_name,
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE success) as successful,
            ROUND(AVG(response_time_ms)::numeric, 0) as avg_ms
        FROM request_logs
        GROUP BY tool_name
        ORDER BY total DESC;
    """)
    if not tool_df.empty:
        fig = px.bar(
            tool_df, x="tool_name", y="total",
            color="avg_ms",
            color_continuous_scale="Blues",
            labels={"tool_name": "Tool", "total": "Requests", "avg_ms": "Avg ms"},
        )
        fig.update_layout(height=300)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No data yet.")

# ---------------------------------------------------------------------------
# Charts Row 2: Top Locations + Response Time Distribution
# ---------------------------------------------------------------------------

chart_col3, chart_col4 = st.columns(2)

with chart_col3:
    st.subheader("Top Queried Locations")
    loc_df = run_query("""
        SELECT 
            COALESCE(resolved_location, location_query) as location,
            COUNT(*) as requests
        FROM request_logs
        WHERE location_query IS NOT NULL
        GROUP BY 1
        ORDER BY requests DESC
        LIMIT 10;
    """)
    if not loc_df.empty:
        fig = px.bar(
            loc_df, x="requests", y="location",
            orientation="h",
            color="requests",
            color_continuous_scale="Viridis",
        )
        fig.update_layout(height=300, showlegend=False, yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No data yet.")

with chart_col4:
    st.subheader("Response Time Distribution")
    rt_df = run_query("""
        SELECT response_time_ms, tool_name, success
        FROM request_logs
        WHERE response_time_ms IS NOT NULL;
    """)
    if not rt_df.empty:
        fig = px.histogram(
            rt_df, x="response_time_ms", color="tool_name",
            nbins=20,
            labels={"response_time_ms": "Response Time (ms)", "tool_name": "Tool"},
        )
        fig.update_layout(height=300)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No data yet.")

st.divider()

# ---------------------------------------------------------------------------
# Recent Requests Table
# ---------------------------------------------------------------------------

st.subheader("Recent Requests")

recent_df = run_query("""
    SELECT 
        timestamp,
        tool_name,
        location_query,
        resolved_location,
        success,
        response_time_ms,
        error_message
    FROM request_logs
    ORDER BY timestamp DESC
    LIMIT 50;
""")

if not recent_df.empty:
    # Style the dataframe
    st.dataframe(
        recent_df,
        column_config={
            "timestamp": st.column_config.DatetimeColumn("Time", format="YYYY-MM-DD HH:mm:ss"),
            "tool_name": "Tool",
            "location_query": "Query",
            "resolved_location": "Resolved",
            "success": st.column_config.CheckboxColumn("OK"),
            "response_time_ms": st.column_config.NumberColumn("ms", format="%d"),
            "error_message": "Error",
        },
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("No requests logged yet. Start using the Weather MCP tools!")

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.divider()
st.caption(
    "Data source: Lakebase Postgres `request_logs` table | "
    "MCP Server: weather-mcp-server | "
    "Auto-refreshes on page load"
)

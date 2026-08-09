"""Database Logger Module.

Logs MCP tool requests to Lakebase Postgres for analytics and debugging.
Designed to be fail-safe: logging errors are caught and printed but never
crash the MCP server or affect tool responses.

Connection credentials are read from environment variables:
    - PGHOST: Postgres host
    - PGDATABASE: Database name
    - PGUSER: Username
    - PGPASSWORD: Password
"""

import json
import logging
import os
import time
from contextlib import contextmanager
from typing import Any

import psycopg2
import psycopg2.pool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Connection Pool (lazy-initialized)
# ---------------------------------------------------------------------------

_pool: psycopg2.pool.SimpleConnectionPool | None = None


def _get_pool() -> psycopg2.pool.SimpleConnectionPool:
    """Get or create the connection pool (lazy singleton)."""
    global _pool
    if _pool is None or _pool.closed:
        _pool = psycopg2.pool.SimpleConnectionPool(
            minconn=1,
            maxconn=5,
            host=os.environ.get("PGHOST", "localhost"),
            database=os.environ.get("PGDATABASE", "databricks_postgres"),
            user=os.environ.get("PGUSER", "WeatherMCPserver"),
            password=os.environ.get("PGPASSWORD", ""),
            sslmode="require",
            connect_timeout=5,
        )
        logger.info("Database connection pool created.")
    return _pool


@contextmanager
def _get_conn():
    """Context manager that checks out a connection and returns it to the pool."""
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def log_request(
    tool_name: str,
    location_query: str | None = None,
    resolved_location: str | None = None,
    success: bool = True,
    response_time_ms: int | None = None,
    error_message: str | None = None,
    extra_params: dict[str, Any] | None = None,
) -> None:
    """Log a tool request to the database.

    This function is fail-safe: any exception is logged to stderr
    but never propagated to the caller.

    Args:
        tool_name: Name of the MCP tool called.
        location_query: Raw location string from the user.
        resolved_location: Resolved location name (city, country).
        success: Whether the tool call succeeded.
        response_time_ms: Time taken in milliseconds.
        error_message: Error message if the call failed.
        extra_params: Additional parameters (stored as JSONB).
    """
    try:
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO request_logs
                    (tool_name, location_query, resolved_location, success,
                     response_time_ms, error_message, extra_params)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    tool_name,
                    location_query,
                    resolved_location,
                    success,
                    response_time_ms,
                    error_message,
                    json.dumps(extra_params) if extra_params else None,
                ),
            )
            cur.close()
    except Exception as exc:
        # Never crash the MCP server due to logging failures
        logger.warning(f"Failed to log request to database: {exc}")


class RequestTimer:
    """Context manager to time a tool call and log it.

    Usage:
        with RequestTimer("get_current_weather", location="Chicago") as timer:
            result = do_work()
            timer.set_resolved("Chicago, United States")
            if "error" in result:
                timer.set_error(result["error"])
    """

    def __init__(self, tool_name: str, location: str | None = None, **extra_params):
        self.tool_name = tool_name
        self.location_query = location
        self.resolved_location: str | None = None
        self.error_message: str | None = None
        self.extra_params = extra_params if extra_params else None
        self._start: float = 0

    def set_resolved(self, resolved: str) -> None:
        """Set the resolved location name."""
        self.resolved_location = resolved

    def set_error(self, error: str) -> None:
        """Mark this request as failed."""
        self.error_message = error

    def __enter__(self):
        self._start = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed_ms = int((time.time() - self._start) * 1000)
        success = self.error_message is None and exc_type is None

        if exc_type is not None:
            self.error_message = f"{exc_type.__name__}: {exc_val}"

        log_request(
            tool_name=self.tool_name,
            location_query=self.location_query,
            resolved_location=self.resolved_location,
            success=success,
            response_time_ms=elapsed_ms,
            error_message=self.error_message,
            extra_params=self.extra_params,
        )

        # Never suppress exceptions from the tool itself
        return False

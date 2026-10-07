"""PostgreSQL access layer (SQLAlchemy + psycopg2)."""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine

from config import config

logger = logging.getLogger(__name__)

LANDING_TABLE = "weather_hourly"
LANDING_SCHEMA = "raw"
LANDING_COLUMNS = [
    "city",
    "latitude",
    "longitude",
    "observation_timestamp",
    "temperature_celsius",
    "apparent_temperature_celsius",
    "precipitation_mm",
    "wind_speed_kmh",
    "humidity_pct",
    "weather_code",
    "temperature_difference",
    "precipitation_flag",
    "high_wind_flag",
    "is_rainy",
    "is_extreme_temperature",
]


class DatabaseConfigError(RuntimeError):
    """Raised when the database settings are incomplete."""


def build_database_url() -> URL:
    """Build the connection URL from environment variables."""
    settings = config.get_db_settings()
    if not settings["password"]:
        raise DatabaseConfigError(
            "WEATHER_DB_PASSWORD is not set. Copy .env.example to .env first."
        )
    return URL.create(
        "postgresql+psycopg2",
        username=settings["user"],
        password=settings["password"],
        host=settings["host"],
        port=settings["port"],
        database=settings["database"],
    )


def get_engine(url: URL | str | None = None) -> Engine:
    """Create a SQLAlchemy engine."""
    return create_engine(url or build_database_url(), pool_pre_ping=True)


def split_sql_statements(sql_text: str) -> list[str]:
    """Split a SQL script into statements (comments removed).

    Simple on purpose: our scripts avoid ``;`` inside strings and ``$$`` blocks.
    """
    without_comments = re.sub(r"--[^\n]*", "", sql_text)
    return [part.strip() for part in without_comments.split(";") if part.strip()]


def run_sql_file(engine: Engine, sql_path: str | Path) -> int:
    """Execute every statement of a SQL file in one transaction."""
    path = Path(sql_path)
    statements = split_sql_statements(path.read_text(encoding="utf-8"))
    with engine.begin() as connection:
        for statement in statements:
            connection.exec_driver_sql(statement)
    logger.info("Executed %d statements from %s", len(statements), path.name)
    return len(statements)


def init_database(engine: Engine, sql_dir: str | Path = config.SQL_DIR) -> None:
    """Create schemas, tables, dimensions, facts and views (idempotent)."""
    for file_name in config.SQL_SETUP_FILES:
        run_sql_file(engine, Path(sql_dir) / file_name)


def prepare_landing_dataframe(df: pd.DataFrame, run_id: str) -> pd.DataFrame:
    """Select the landing-table columns and tag the rows with the run id."""
    missing = [c for c in LANDING_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"missing columns for the landing table: {missing}")
    landing = df[LANDING_COLUMNS].copy()
    landing.insert(0, "run_id", run_id)
    return landing


def load_landing_table(engine: Engine, df: pd.DataFrame, run_id: str) -> int:
    """Append the processed rows to ``raw.weather_hourly``.

    Rows of the same ``run_id`` are deleted first, so retries are idempotent.
    """
    landing = prepare_landing_dataframe(df, run_id)
    with engine.begin() as connection:
        connection.execute(
            text(f"DELETE FROM {LANDING_SCHEMA}.{LANDING_TABLE} WHERE run_id = :run_id"),
            {"run_id": run_id},
        )
        landing.to_sql(
            LANDING_TABLE,
            connection,
            schema=LANDING_SCHEMA,
            if_exists="append",
            index=False,
            method="multi",
            chunksize=1000,
        )
    logger.info("Loaded %d rows into raw.weather_hourly", len(landing))
    return len(landing)


def load_quality_report(engine: Engine, report: dict[str, Any]) -> int:
    """Store the checks of a quality report in ``raw.quality_report``."""
    rows = [
        {
            "run_id": report["run_id"],
            "run_timestamp": report["generated_at"],
            "check_name": check["name"],
            "passed": check["passed"],
            "failed_rows": check["failed_rows"],
            "total_rows": check["total_rows"],
            "message": check["message"],
        }
        for check in report["checks"]
    ]
    insert_sql = text(
        "INSERT INTO raw.quality_report "
        "(run_id, run_timestamp, check_name, passed, failed_rows, total_rows, message) "
        "VALUES (:run_id, :run_timestamp, :check_name, :passed, :failed_rows, "
        ":total_rows, :message)"
    )
    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM raw.quality_report WHERE run_id = :run_id"),
            {"run_id": report["run_id"]},
        )
        if rows:
            connection.execute(insert_sql, rows)
    return len(rows)


def load_warehouse(engine: Engine, sql_dir: str | Path = config.SQL_DIR) -> int:
    """Upsert dimensions and facts from the landing table."""
    return run_sql_file(engine, Path(sql_dir) / config.SQL_LOAD_WAREHOUSE_FILE)


def refresh_analytics(engine: Engine, sql_dir: str | Path = config.SQL_DIR) -> None:
    """Re-create the analytics views and refresh table statistics."""
    run_sql_file(engine, Path(sql_dir) / config.SQL_ANALYTICS_FILE)
    with engine.begin() as connection:
        connection.exec_driver_sql("ANALYZE warehouse.fact_weather")
    logger.info("Analytics views refreshed")

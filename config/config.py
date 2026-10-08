"""Central configuration for the weather data pipeline.

Values come from environment variables (optionally loaded from a local ``.env``
file). Everything has a safe default except the database password, which must
never be hard-coded.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:  # python-dotenv is optional (it may not exist inside the Airflow container)
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", Path(__file__).resolve().parents[1]))
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DATA_DIR = PROJECT_ROOT / "data" / "processed"
SQL_DIR = PROJECT_ROOT / "sql"
PROCESSED_LATEST_NAME = "weather_latest.parquet"

# SQL scripts executed (in order) to create the database objects.
SQL_SETUP_FILES = [
    "01_create_schemas.sql",
    "02_create_tables.sql",
    "03_create_dimensions.sql",
    "04_create_facts.sql",
    "05_create_analytics_views.sql",
]
SQL_LOAD_WAREHOUSE_FILE = "06_load_warehouse.sql"
SQL_ANALYTICS_FILE = "05_create_analytics_views.sql"

# --------------------------------------------------------------------------- #
# Open-Meteo API (no API key required)
# --------------------------------------------------------------------------- #
OPEN_METEO_URL = os.getenv("OPEN_METEO_URL", "https://api.open-meteo.com/v1/forecast")
TIMEZONE = os.getenv("WEATHER_TIMEZONE", "America/Sao_Paulo")
PAST_DAYS = int(os.getenv("WEATHER_PAST_DAYS", "7"))
FORECAST_DAYS = 1
REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2.0

HOURLY_VARIABLES = [
    "temperature_2m",
    "apparent_temperature",
    "precipitation",
    "wind_speed_10m",
    "relative_humidity_2m",
    "weather_code",
]

CITIES: dict[str, dict[str, Any]] = {
    "Curitiba": {"latitude": -25.4284, "longitude": -49.2733, "state": "PR"},
    "São Paulo": {"latitude": -23.5505, "longitude": -46.6333, "state": "SP"},
    "Rio de Janeiro": {"latitude": -22.9068, "longitude": -43.1729, "state": "RJ"},
    "Belo Horizonte": {"latitude": -19.9167, "longitude": -43.9345, "state": "MG"},
    "Brasília": {"latitude": -15.7939, "longitude": -47.8828, "state": "DF"},
}

# --------------------------------------------------------------------------- #
# Business rules used by the transformation and quality layers
# --------------------------------------------------------------------------- #
RAINY_THRESHOLD_MM = 0.1       # hourly precipitation that counts as rain
HIGH_WIND_THRESHOLD_KMH = 40.0
EXTREME_HOT_CELSIUS = 35.0
EXTREME_COLD_CELSIUS = 5.0

TEMPERATURE_RANGE = (-90.0, 60.0)   # physically plausible bounds on Earth
HUMIDITY_RANGE = (0.0, 100.0)
WIND_SPEED_RANGE = (0.0, 250.0)

# WMO weather interpretation codes used by Open-Meteo.
VALID_WEATHER_CODES = frozenset(
    {0, 1, 2, 3, 45, 48, 51, 53, 55, 56, 57, 61, 63, 65, 66, 67,
     71, 73, 75, 77, 80, 81, 82, 85, 86, 95, 96, 99}
)
RAIN_WEATHER_CODES = frozenset(
    {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99}
)


# --------------------------------------------------------------------------- #
# Database
# --------------------------------------------------------------------------- #
def get_db_settings() -> dict[str, Any]:
    """Read PostgreSQL settings from the environment at call time."""
    return {
        "host": os.getenv("WEATHER_DB_HOST", "localhost"),
        "port": int(os.getenv("WEATHER_DB_PORT", "5432")),
        "database": os.getenv("WEATHER_DB_NAME", "weather_dw"),
        "user": os.getenv("WEATHER_DB_USER", "weather_user"),
        "password": os.getenv("WEATHER_DB_PASSWORD", ""),
    }

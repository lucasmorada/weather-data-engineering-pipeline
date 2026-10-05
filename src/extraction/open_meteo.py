"""Extraction layer: download hourly weather data from the Open-Meteo API.

Raw API responses are stored untouched as JSON files in ``data/raw/`` so the
pipeline can always be re-run from the original data.

Layout:  data/raw/date=YYYY-MM-DD/<city_slug>_<run_id>.json
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import requests

from config import config
from src.utils import slugify

logger = logging.getLogger(__name__)


class ExtractionError(RuntimeError):
    """Raised when weather data cannot be downloaded."""


def build_params(
    latitude: float,
    longitude: float,
    past_days: int = config.PAST_DAYS,
    forecast_days: int = config.FORECAST_DAYS,
) -> dict[str, Any]:
    """Build the query string for the Open-Meteo forecast endpoint."""
    return {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": ",".join(config.HOURLY_VARIABLES),
        "past_days": past_days,
        "forecast_days": forecast_days,
        "timezone": config.TIMEZONE,
        "temperature_unit": "celsius",
        "wind_speed_unit": "kmh",
        "precipitation_unit": "mm",
    }


def fetch_city_weather(
    city: str,
    latitude: float,
    longitude: float,
    past_days: int = config.PAST_DAYS,
    session: requests.Session | None = None,
    max_retries: int = config.MAX_RETRIES,
    backoff_seconds: float = config.RETRY_BACKOFF_SECONDS,
) -> dict[str, Any]:
    """Download hourly weather for one city, retrying on temporary failures."""
    http = session or requests
    params = build_params(latitude, longitude, past_days)
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            response = http.get(
                config.OPEN_METEO_URL,
                params=params,
                timeout=config.REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
            if "hourly" not in payload:
                raise ValueError("API response has no 'hourly' section")
            logger.info("Fetched weather for %s (attempt %d)", city, attempt)
            return payload
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            logger.warning(
                "Attempt %d/%d failed for %s: %s", attempt, max_retries, city, exc
            )
            if attempt < max_retries:
                time.sleep(backoff_seconds * attempt)

    raise ExtractionError(
        f"Could not fetch weather for {city} after {max_retries} attempts"
    ) from last_error


def save_raw_payload(
    payload: dict[str, Any],
    city: str,
    run_id: str,
    raw_dir: Path = config.RAW_DATA_DIR,
) -> Path:
    """Save one API response to ``data/raw`` and return the file path."""
    extracted_at = datetime.now(timezone.utc)
    partition = Path(raw_dir) / f"date={extracted_at.date().isoformat()}"
    partition.mkdir(parents=True, exist_ok=True)

    document = dict(payload)
    document["_metadata"] = {
        "city": city,
        "run_id": run_id,
        "extracted_at": extracted_at.isoformat(),
        "source": config.OPEN_METEO_URL,
    }
    file_path = partition / f"{slugify(city)}_{run_id}.json"
    file_path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    logger.info("Saved raw data to %s", file_path)
    return file_path


def extract_all_cities(
    run_id: str,
    cities: dict[str, dict[str, Any]] | None = None,
    past_days: int = config.PAST_DAYS,
    raw_dir: Path = config.RAW_DATA_DIR,
) -> list[Path]:
    """Extract every configured city. A failing city is logged and skipped."""
    cities = cities or config.CITIES
    saved: list[Path] = []

    for city, info in cities.items():
        try:
            payload = fetch_city_weather(
                city, info["latitude"], info["longitude"], past_days
            )
            saved.append(save_raw_payload(payload, city, run_id, raw_dir))
        except ExtractionError:
            logger.exception("Skipping %s because extraction failed", city)

    if not saved:
        raise ExtractionError("No city could be extracted")
    return saved


def hourly_to_dataframe(payload: dict[str, Any], city: str) -> pd.DataFrame:
    """Flatten the ``hourly`` section of a payload into one row per hour."""
    df = pd.DataFrame(payload["hourly"]).rename(columns={"time": "timestamp"})
    df.insert(0, "city", city)
    df.insert(1, "latitude", payload.get("latitude"))
    df.insert(2, "longitude", payload.get("longitude"))
    return df


def load_raw_files(paths: Iterable[str | Path]) -> pd.DataFrame:
    """Read saved raw JSON files and return a single DataFrame."""
    frames = []
    for path in paths:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        city = payload.get("_metadata", {}).get("city", "Unknown")
        frames.append(hourly_to_dataframe(payload, city))
    if not frames:
        raise ExtractionError("No raw files to load")
    return pd.concat(frames, ignore_index=True)

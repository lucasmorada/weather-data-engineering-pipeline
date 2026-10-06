"""Transformation layer: clean raw weather data and create derived metrics."""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from config import config
from src.utils import strip_accents

logger = logging.getLogger(__name__)

COLUMN_RENAMES = {
    "timestamp": "observation_timestamp",
    "temperature_2m": "temperature_celsius",
    "apparent_temperature": "apparent_temperature_celsius",
    "precipitation": "precipitation_mm",
    "wind_speed_10m": "wind_speed_kmh",
    "relative_humidity_2m": "humidity_pct",
}
NUMERIC_COLUMNS = [
    "latitude",
    "longitude",
    "temperature_celsius",
    "apparent_temperature_celsius",
    "precipitation_mm",
    "wind_speed_kmh",
    "humidity_pct",
]
# Smooth, continuous variables can be interpolated over short gaps.
INTERPOLATE_COLUMNS = [
    "temperature_celsius",
    "apparent_temperature_celsius",
    "wind_speed_kmh",
    "humidity_pct",
]
MAX_INTERPOLATION_GAP_HOURS = 3


def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Use lower-case snake_case names and explicit units."""
    out = df.copy()
    out.columns = [str(c).strip().lower() for c in out.columns]
    return out.rename(columns=COLUMN_RENAMES)


def clean_city_names(df: pd.DataFrame) -> pd.DataFrame:
    """Trim spaces and map spelling variants to the canonical city names."""
    lookup = {strip_accents(name).lower(): name for name in config.CITIES}
    out = df.copy()

    def canonical(value: object) -> object:
        if pd.isna(value):
            return value
        text = " ".join(str(value).split())
        return lookup.get(strip_accents(text).lower(), text)

    out["city"] = out["city"].map(canonical)
    return out


def convert_types(df: pd.DataFrame) -> pd.DataFrame:
    """Convert timestamps and numbers; invalid values become NaN/NaT."""
    out = df.copy()
    out["observation_timestamp"] = pd.to_datetime(
        out["observation_timestamp"], errors="coerce"
    )
    for column in NUMERIC_COLUMNS:
        out[column] = pd.to_numeric(out[column], errors="coerce")
    out["weather_code"] = pd.to_numeric(out["weather_code"], errors="coerce").astype(
        "Int64"
    )
    return out


def remove_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """Keep the latest row for each (city, observation_timestamp)."""
    before = len(df)
    out = df.drop_duplicates(subset=["city", "observation_timestamp"], keep="last")
    logger.info("Removed %d duplicate rows", before - len(out))
    return out.reset_index(drop=True)


def handle_missing_values(df: pd.DataFrame) -> pd.DataFrame:
    """Drop rows without key fields and fill small gaps.

    * rows without city or timestamp are dropped (they cannot be identified);
    * temperature, humidity and wind are interpolated over short gaps per city;
    * missing precipitation is assumed to be 0 mm (documented assumption).
    """
    out = df.dropna(subset=["city", "observation_timestamp"])
    out = out.sort_values(["city", "observation_timestamp"]).reset_index(drop=True)
    out[INTERPOLATE_COLUMNS] = out.groupby("city")[INTERPOLATE_COLUMNS].transform(
        lambda s: s.interpolate(
            limit=MAX_INTERPOLATION_GAP_HOURS, limit_direction="both"
        )
    )
    out["precipitation_mm"] = out["precipitation_mm"].fillna(0.0)
    return out


def add_derived_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Create date parts and business flags."""
    out = df.copy()
    temp = out["temperature_celsius"]
    out["date"] = out["observation_timestamp"].dt.date
    out["hour"] = out["observation_timestamp"].dt.hour
    out["temperature_difference"] = (
        temp - out["apparent_temperature_celsius"]
    ).round(2)
    out["precipitation_flag"] = out["precipitation_mm"] > 0
    out["high_wind_flag"] = out["wind_speed_kmh"] >= config.HIGH_WIND_THRESHOLD_KMH
    out["is_rainy"] = (out["precipitation_mm"] >= config.RAINY_THRESHOLD_MM) | out[
        "weather_code"
    ].isin(config.RAIN_WEATHER_CODES)
    out["is_extreme_temperature"] = (temp >= config.EXTREME_HOT_CELSIUS) | (
        temp <= config.EXTREME_COLD_CELSIUS
    )
    return out


def _min_max(series: pd.Series) -> pd.Series:
    """Scale a series to the 0-1 range (0 when all values are equal)."""
    span = series.max() - series.min()
    if pd.isna(span) or span == 0:
        return pd.Series(0.0, index=series.index)
    return (series - series.min()) / span


def normalize_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Round measurements and add 0-1 scaled columns for comparison/plots."""
    out = df.copy()
    for column in NUMERIC_COLUMNS[2:]:
        out[column] = out[column].round(2)
    out["temperature_norm"] = _min_max(out["temperature_celsius"]).round(4)
    out["humidity_norm"] = _min_max(out["humidity_pct"]).round(4)
    out["wind_speed_norm"] = _min_max(out["wind_speed_kmh"]).round(4)
    return out


def transform_weather(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Run the complete transformation and return the processed DataFrame."""
    if raw_df.empty:
        raise ValueError("Cannot transform an empty DataFrame")

    df = standardize_columns(raw_df)
    df = clean_city_names(df)
    df = convert_types(df)
    df = remove_duplicates(df)
    df = handle_missing_values(df)
    df = add_derived_metrics(df)
    df = normalize_metrics(df)
    logger.info("Transformation finished with %d rows", len(df))
    return df


def save_processed(
    df: pd.DataFrame, run_id: str, processed_dir: Path = config.PROCESSED_DATA_DIR
) -> Path:
    """Save the processed data as Parquet (timestamped copy + latest copy)."""
    processed_dir = Path(processed_dir)
    processed_dir.mkdir(parents=True, exist_ok=True)
    path = processed_dir / f"weather_processed_{run_id}.parquet"
    df.to_parquet(path, index=False)
    df.to_parquet(processed_dir / config.PROCESSED_LATEST_NAME, index=False)
    logger.info("Saved processed data to %s", path)
    return path

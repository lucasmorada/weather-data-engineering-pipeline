"""Tests for the transformation layer."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.transformation.transform_weather import (
    clean_city_names,
    save_processed,
    transform_weather,
)


def test_columns_are_standardized(raw_df):
    df = transform_weather(raw_df)
    for column in [
        "observation_timestamp",
        "temperature_celsius",
        "apparent_temperature_celsius",
        "precipitation_mm",
        "wind_speed_kmh",
        "humidity_pct",
    ]:
        assert column in df.columns
    assert "temperature_2m" not in df.columns


def test_types_are_converted(raw_df):
    df = transform_weather(raw_df)
    assert pd.api.types.is_datetime64_any_dtype(df["observation_timestamp"])
    assert str(df["weather_code"].dtype) == "Int64"
    assert pd.api.types.is_float_dtype(df["temperature_celsius"])


def test_duplicates_are_removed(raw_df):
    doubled = pd.concat([raw_df, raw_df], ignore_index=True)
    df = transform_weather(doubled)
    assert len(df) == len(raw_df)


def test_rows_without_timestamp_are_dropped(raw_df):
    raw_df.loc[0, "timestamp"] = None
    df = transform_weather(raw_df)
    assert len(df) == 2


def test_missing_temperature_is_interpolated(raw_df):
    raw_df.loc[1, "temperature_2m"] = np.nan
    df = transform_weather(raw_df)
    assert df["temperature_celsius"].notna().all()
    # halfway between 20.1 and 19.0
    assert df.loc[1, "temperature_celsius"] == pytest.approx(19.55, abs=0.01)


def test_missing_precipitation_becomes_zero(raw_df):
    raw_df.loc[0, "precipitation"] = np.nan
    df = transform_weather(raw_df)
    assert df.loc[0, "precipitation_mm"] == 0.0


def test_derived_flags(raw_df):
    raw_df["temperature_2m"] = [36.0, 25.0, 3.0]          # hot, normal, cold
    raw_df["precipitation"] = [0.0, 2.0, 0.0]
    raw_df["wind_speed_10m"] = [10.0, 45.0, 5.0]
    raw_df["weather_code"] = [0, 61, 3]
    df = transform_weather(raw_df)

    assert list(df["is_extreme_temperature"]) == [True, False, True]
    assert list(df["precipitation_flag"]) == [False, True, False]
    assert list(df["is_rainy"]) == [False, True, False]
    assert list(df["high_wind_flag"]) == [False, True, False]


def test_rain_weather_code_makes_hour_rainy_even_without_precipitation(raw_df):
    raw_df["precipitation"] = [0.0, 0.0, 0.0]
    raw_df["weather_code"] = [0, 63, 3]
    df = transform_weather(raw_df)
    assert list(df["is_rainy"]) == [False, True, False]


def test_temperature_difference(raw_df):
    df = transform_weather(raw_df)
    expected = (df["temperature_celsius"] - df["apparent_temperature_celsius"]).round(2)
    assert df["temperature_difference"].equals(expected)


def test_normalized_columns_are_between_zero_and_one(raw_df):
    df = transform_weather(raw_df)
    for column in ["temperature_norm", "humidity_norm", "wind_speed_norm"]:
        assert df[column].between(0, 1).all()


def test_city_names_are_canonicalized():
    df = pd.DataFrame({"city": ["  sao paulo ", "BRASILIA", "Atlantis"]})
    result = clean_city_names(df)
    assert list(result["city"]) == ["São Paulo", "Brasília", "Atlantis"]


def test_empty_dataframe_is_rejected():
    with pytest.raises(ValueError):
        transform_weather(pd.DataFrame())


def test_save_processed_writes_parquet(raw_df, tmp_path):
    pytest.importorskip("pyarrow")
    df = transform_weather(raw_df)
    path = save_processed(df, "RUN1", processed_dir=tmp_path)
    assert path.exists()
    assert (tmp_path / "weather_latest.parquet").exists()
    assert len(pd.read_parquet(path)) == len(df)

"""Shared fixtures. No test here calls the real API or a real database."""
from __future__ import annotations

import pytest

from src.extraction.open_meteo import hourly_to_dataframe


@pytest.fixture
def sample_payload() -> dict:
    """A tiny Open-Meteo style response with 3 hourly records."""
    return {
        "latitude": -25.4,
        "longitude": -49.3,
        "hourly": {
            "time": ["2025-01-01T00:00", "2025-01-01T01:00", "2025-01-01T02:00"],
            "temperature_2m": [20.1, 19.5, 19.0],
            "apparent_temperature": [21.0, 20.2, 19.5],
            "precipitation": [0.0, 0.2, 0.0],
            "wind_speed_10m": [10.0, 12.5, 8.0],
            "relative_humidity_2m": [80, 85, 90],
            "weather_code": [1, 61, 3],
        },
    }


@pytest.fixture
def raw_df(sample_payload):
    """The sample payload flattened as the extraction layer does."""
    return hourly_to_dataframe(sample_payload, "Curitiba")

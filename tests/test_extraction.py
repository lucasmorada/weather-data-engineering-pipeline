"""Tests for the extraction layer (HTTP calls are mocked)."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
import requests

from config import config
from src.extraction import open_meteo
from src.extraction.open_meteo import (
    ExtractionError,
    build_params,
    extract_all_cities,
    fetch_city_weather,
    hourly_to_dataframe,
    load_raw_files,
    save_raw_payload,
)
from src.utils import slugify


def _ok_response(payload: dict) -> MagicMock:
    response = MagicMock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def test_slugify_removes_accents_and_spaces():
    assert slugify("São Paulo") == "sao_paulo"
    assert slugify("Rio de Janeiro") == "rio_de_janeiro"


def test_build_params_requests_all_hourly_variables():
    params = build_params(-25.4, -49.3, past_days=3)
    assert params["past_days"] == 3
    assert params["timezone"] == config.TIMEZONE
    for variable in config.HOURLY_VARIABLES:
        assert variable in params["hourly"].split(",")


def test_hourly_to_dataframe_has_one_row_per_hour(sample_payload):
    df = hourly_to_dataframe(sample_payload, "Curitiba")
    assert len(df) == 3
    assert set(df["city"]) == {"Curitiba"}
    assert "timestamp" in df.columns
    assert df["latitude"].iloc[0] == -25.4


def test_fetch_city_weather_returns_payload(sample_payload):
    session = MagicMock()
    session.get.return_value = _ok_response(sample_payload)
    result = fetch_city_weather("Curitiba", -25.4, -49.3, session=session)
    assert result == sample_payload
    session.get.assert_called_once()


def test_fetch_retries_after_temporary_error(sample_payload):
    session = MagicMock()
    session.get.side_effect = [
        requests.ConnectionError("boom"),
        _ok_response(sample_payload),
    ]
    result = fetch_city_weather(
        "Curitiba", -25.4, -49.3, session=session, max_retries=3, backoff_seconds=0
    )
    assert result == sample_payload
    assert session.get.call_count == 2


def test_fetch_raises_after_all_retries_fail():
    session = MagicMock()
    session.get.side_effect = requests.Timeout("slow")
    with pytest.raises(ExtractionError):
        fetch_city_weather(
            "Curitiba", -25.4, -49.3, session=session, max_retries=2, backoff_seconds=0
        )
    assert session.get.call_count == 2


def test_fetch_rejects_payload_without_hourly_section():
    session = MagicMock()
    session.get.return_value = _ok_response({"error": True})
    with pytest.raises(ExtractionError):
        fetch_city_weather(
            "Curitiba", -25.4, -49.3, session=session, max_retries=1, backoff_seconds=0
        )


def test_save_and_load_raw_files_roundtrip(tmp_path, sample_payload):
    path = save_raw_payload(sample_payload, "São Paulo", "RUN1", raw_dir=tmp_path)
    assert path.exists()
    assert path.name == "sao_paulo_RUN1.json"
    assert path.parent.name.startswith("date=")

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["_metadata"]["city"] == "São Paulo"

    df = load_raw_files([path])
    assert len(df) == 3
    assert set(df["city"]) == {"São Paulo"}


def test_extract_all_cities_skips_failed_city(monkeypatch, tmp_path, sample_payload):
    def fake_fetch(city, latitude, longitude, past_days):
        if city == "Curitiba":
            raise ExtractionError("down")
        return sample_payload

    monkeypatch.setattr(open_meteo, "fetch_city_weather", fake_fetch)
    paths = extract_all_cities("RUN2", raw_dir=tmp_path)
    assert len(paths) == len(config.CITIES) - 1


def test_extract_all_cities_fails_when_nothing_is_extracted(monkeypatch, tmp_path):
    def always_fail(*args, **kwargs):
        raise ExtractionError("down")

    monkeypatch.setattr(open_meteo, "fetch_city_weather", always_fail)
    with pytest.raises(ExtractionError):
        extract_all_cities("RUN3", raw_dir=tmp_path)

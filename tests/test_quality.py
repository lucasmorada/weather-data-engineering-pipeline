"""Tests for the data quality layer."""
from __future__ import annotations

import json

import pandas as pd
import pytest

from src.quality.quality_checks import (
    DataQualityError,
    run_quality_checks,
    save_report,
    validate_raw_files,
    validate_raw_payload,
)
from src.transformation.transform_weather import transform_weather

EXPECTED = ["Curitiba"]


@pytest.fixture
def good_df(raw_df) -> pd.DataFrame:
    return transform_weather(raw_df)


def _check(report, name):
    return next(check for check in report.checks if check.name == name)


def test_clean_data_passes(good_df):
    report = run_quality_checks(good_df, expected_cities=EXPECTED, run_id="t1")
    assert report.passed
    assert report.to_dict()["status"] == "PASSED"
    assert report.failed_checks == []


@pytest.mark.parametrize(
    "column, value, check_name",
    [
        ("temperature_celsius", 999.0, "temperature_range"),
        ("apparent_temperature_celsius", -120.0, "temperature_range"),
        ("humidity_pct", 150.0, "humidity_range"),
        ("wind_speed_kmh", -5.0, "wind_speed_range"),
        ("precipitation_mm", -1.0, "precipitation_range"),
        ("latitude", 95.0, "latitude_range"),
        ("longitude", 200.0, "longitude_range"),
        ("city", "Atlantis", "unexpected_cities"),
        ("weather_code", 7, "weather_codes_valid"),
    ],
)
def test_invalid_values_fail_the_expected_check(good_df, column, value, check_name):
    good_df = good_df.astype({column: object}) if column == "weather_code" else good_df
    good_df.loc[0, column] = value
    report = run_quality_checks(good_df, expected_cities=EXPECTED, run_id="t2")
    assert not report.passed
    assert not _check(report, check_name).passed
    assert report.to_dict()["status"] == "FAILED"


def test_duplicates_are_detected(good_df):
    duplicated = pd.concat([good_df, good_df.iloc[[0]]], ignore_index=True)
    report = run_quality_checks(duplicated, expected_cities=EXPECTED)
    check = _check(report, "duplicate_records")
    assert not check.passed
    assert check.failed_rows == 1


def test_null_values_are_detected(good_df):
    good_df.loc[1, "temperature_celsius"] = None
    report = run_quality_checks(good_df, expected_cities=EXPECTED)
    assert not _check(report, "null_values").passed


def test_missing_timestamp_is_detected(good_df):
    good_df.loc[0, "observation_timestamp"] = pd.NaT
    report = run_quality_checks(good_df, expected_cities=EXPECTED)
    assert not _check(report, "missing_timestamps").passed


def test_missing_expected_city_is_detected(good_df):
    report = run_quality_checks(good_df, expected_cities=["Curitiba", "São Paulo"])
    assert not _check(report, "missing_cities").passed


def test_empty_dataframe_fails(good_df):
    report = run_quality_checks(good_df.iloc[0:0], expected_cities=EXPECTED)
    assert not report.passed
    assert not _check(report, "dataset_not_empty").passed


def test_summary_mentions_status(good_df):
    good_df.loc[0, "humidity_pct"] = 150.0
    report = run_quality_checks(good_df, expected_cities=EXPECTED)
    assert "FAILED" in report.summary()
    assert "humidity_range" in report.summary()


def test_save_report_writes_json(good_df, tmp_path):
    report = run_quality_checks(good_df, expected_cities=EXPECTED, run_id="t3")
    path = save_report(report, tmp_path / "reports" / "report.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["run_id"] == "t3"
    assert data["status"] == "PASSED"
    assert len(data["checks"]) >= 10


def test_data_quality_error_is_an_exception():
    assert issubclass(DataQualityError, RuntimeError)


# --------------------------------------------------------------------------- #
# Raw validation
# --------------------------------------------------------------------------- #
def test_validate_raw_payload_returns_record_count(sample_payload):
    assert validate_raw_payload(sample_payload) == 3


def test_validate_raw_payload_rejects_missing_variable(sample_payload):
    del sample_payload["hourly"]["precipitation"]
    with pytest.raises(ValueError, match="precipitation"):
        validate_raw_payload(sample_payload)


def test_validate_raw_payload_rejects_length_mismatch(sample_payload):
    sample_payload["hourly"]["weather_code"] = [1]
    with pytest.raises(ValueError, match="different length"):
        validate_raw_payload(sample_payload)


def test_validate_raw_files(tmp_path, sample_payload):
    good = tmp_path / "good.json"
    good.write_text(json.dumps(sample_payload), encoding="utf-8")
    assert validate_raw_files([good]) == 3

    with pytest.raises(ValueError, match="not found"):
        validate_raw_files([tmp_path / "missing.json"])

    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON"):
        validate_raw_files([broken])

    with pytest.raises(ValueError):
        validate_raw_files([])

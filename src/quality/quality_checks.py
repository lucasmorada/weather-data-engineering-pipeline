"""Data quality layer: validate raw files and processed data.

Every check returns a ``CheckResult``. The ``QualityReport`` says clearly if
the whole run PASSED or FAILED, and can be saved as JSON.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from config import config

logger = logging.getLogger(__name__)

CRITICAL_COLUMNS = [
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
]


class DataQualityError(RuntimeError):
    """Raised when a quality report has at least one failed check."""


@dataclass
class CheckResult:
    """Result of a single data quality check."""

    name: str
    passed: bool
    failed_rows: int
    total_rows: int
    message: str


@dataclass
class QualityReport:
    """Collection of check results for one pipeline run."""

    run_id: str
    total_rows: int
    checks: list[CheckResult] = field(default_factory=list)
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def failed_checks(self) -> list[CheckResult]:
        return [check for check in self.checks if not check.passed]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "status": "PASSED" if self.passed else "FAILED",
            "total_rows": self.total_rows,
            "checks": [asdict(check) for check in self.checks],
        }

    def summary(self) -> str:
        """Human-readable summary, one line per check."""
        status = "PASSED" if self.passed else "FAILED"
        lines = [f"Data quality {status} ({self.total_rows} rows, run {self.run_id})"]
        for check in self.checks:
            mark = "OK  " if check.passed else "FAIL"
            lines.append(f"  [{mark}] {check.name}: {check.message}")
        return "\n".join(lines)


def _result(name: str, failed: int, total: int, description: str) -> CheckResult:
    """Build a CheckResult from a number of failing rows."""
    passed = failed == 0
    message = "no problems found" if passed else f"{failed} problem(s): {description}"
    return CheckResult(name, passed, int(failed), int(total), message)


def _out_of_range(series: pd.Series, low: float, high: float) -> int:
    """Count non-null values outside [low, high]."""
    valid = series.dropna()
    return int((~valid.between(low, high)).sum())


# --------------------------------------------------------------------------- #
# Individual checks (processed DataFrame)
# --------------------------------------------------------------------------- #
def check_not_empty(df: pd.DataFrame) -> CheckResult:
    return _result("dataset_not_empty", int(df.empty), len(df), "dataset has no rows")


def check_duplicates(df: pd.DataFrame) -> CheckResult:
    failed = df.duplicated(subset=["city", "observation_timestamp"]).sum()
    return _result("duplicate_records", failed, len(df), "repeated city + timestamp")


def check_null_values(df: pd.DataFrame) -> CheckResult:
    failed = df[CRITICAL_COLUMNS].isna().any(axis=1).sum()
    return _result("null_values", failed, len(df), "nulls in critical columns")


def check_temperature(df: pd.DataFrame) -> CheckResult:
    low, high = config.TEMPERATURE_RANGE
    failed = _out_of_range(df["temperature_celsius"], low, high) + _out_of_range(
        df["apparent_temperature_celsius"], low, high
    )
    return _result("temperature_range", failed, len(df), f"outside {low}..{high} C")


def check_humidity(df: pd.DataFrame) -> CheckResult:
    low, high = config.HUMIDITY_RANGE
    failed = _out_of_range(df["humidity_pct"], low, high)
    return _result("humidity_range", failed, len(df), f"outside {low}..{high} %")


def check_wind_speed(df: pd.DataFrame) -> CheckResult:
    low, high = config.WIND_SPEED_RANGE
    failed = _out_of_range(df["wind_speed_kmh"], low, high)
    return _result("wind_speed_range", failed, len(df), f"outside {low}..{high} km/h")


def check_precipitation(df: pd.DataFrame) -> CheckResult:
    failed = int((df["precipitation_mm"].dropna() < 0).sum())
    return _result("precipitation_range", failed, len(df), "negative precipitation")


def check_latitude(df: pd.DataFrame) -> CheckResult:
    failed = _out_of_range(df["latitude"], -90, 90)
    return _result("latitude_range", failed, len(df), "outside -90..90")


def check_longitude(df: pd.DataFrame) -> CheckResult:
    failed = _out_of_range(df["longitude"], -180, 180)
    return _result("longitude_range", failed, len(df), "outside -180..180")


def check_missing_timestamps(df: pd.DataFrame) -> CheckResult:
    failed = df["observation_timestamp"].isna().sum()
    return _result("missing_timestamps", failed, len(df), "timestamp is missing")


def check_unexpected_cities(df: pd.DataFrame, expected: Iterable[str]) -> CheckResult:
    failed = (~df["city"].isin(set(expected))).sum()
    return _result("unexpected_cities", failed, len(df), "city not in expected list")


def check_missing_cities(df: pd.DataFrame, expected: Iterable[str]) -> CheckResult:
    missing = sorted(set(expected) - set(df["city"].dropna()))
    return _result(
        "missing_cities", len(missing), len(df), f"no data for {', '.join(missing)}"
    )


def check_weather_codes(df: pd.DataFrame) -> CheckResult:
    invalid = ~df["weather_code"].isin(config.VALID_WEATHER_CODES)
    return _result("weather_codes_valid", invalid.sum(), len(df), "invalid WMO code")


def run_quality_checks(
    df: pd.DataFrame,
    expected_cities: Iterable[str] | None = None,
    run_id: str = "manual",
) -> QualityReport:
    """Run every check and return a ``QualityReport``."""
    expected = list(expected_cities or config.CITIES)
    report = QualityReport(run_id=run_id, total_rows=len(df))
    report.checks.append(check_not_empty(df))
    if df.empty:
        logger.error(report.summary())
        return report

    report.checks.extend(
        [
            check_duplicates(df),
            check_null_values(df),
            check_temperature(df),
            check_humidity(df),
            check_wind_speed(df),
            check_precipitation(df),
            check_latitude(df),
            check_longitude(df),
            check_missing_timestamps(df),
            check_unexpected_cities(df, expected),
            check_missing_cities(df, expected),
            check_weather_codes(df),
        ]
    )
    log = logger.info if report.passed else logger.error
    log(report.summary())
    return report


def save_report(report: QualityReport, path: str | Path) -> Path:
    """Write the quality report to a JSON file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# Raw file validation (first gate, before transformation)
# --------------------------------------------------------------------------- #
def validate_raw_payload(payload: dict[str, Any]) -> int:
    """Check that a raw API payload has the expected structure.

    Returns the number of hourly records or raises ``ValueError``.
    """
    hourly = payload.get("hourly")
    if not isinstance(hourly, dict) or "time" not in hourly:
        raise ValueError("payload has no 'hourly.time' section")

    size = len(hourly["time"])
    if size == 0:
        raise ValueError("payload has no hourly records")
    for variable in config.HOURLY_VARIABLES:
        if variable not in hourly:
            raise ValueError(f"variable '{variable}' is missing")
        if len(hourly[variable]) != size:
            raise ValueError(f"variable '{variable}' has a different length")
    return size


def validate_raw_files(paths: Iterable[str | Path]) -> int:
    """Validate every raw JSON file and return the total number of records."""
    total = 0
    paths = list(paths)
    if not paths:
        raise ValueError("no raw files were provided")
    for path in paths:
        file_path = Path(path)
        if not file_path.exists():
            raise ValueError(f"raw file not found: {file_path}")
        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON in {file_path}: {exc}") from exc
        total += validate_raw_payload(payload)
    logger.info("Raw validation OK: %d files, %d records", len(paths), total)
    return total

"""Pipeline orchestration helpers.

Each ``run_*`` function is one step. They are used by the command line
(``python -m src.pipeline``) and by the Airflow DAG, one task per step.
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from config import config
from src.database import postgres
from src.extraction.open_meteo import extract_all_cities, load_raw_files
from src.quality.quality_checks import (
    DataQualityError,
    run_quality_checks,
    save_report,
    validate_raw_files,
)
from src.transformation.transform_weather import save_processed, transform_weather

logger = logging.getLogger(__name__)


def new_run_id() -> str:
    """Return an id such as ``20250101T120000`` (UTC)."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")


def run_extraction(run_id: str, past_days: int = config.PAST_DAYS) -> list[str]:
    """Step 1: download raw data. Returns the saved file paths."""
    paths = extract_all_cities(run_id, past_days=past_days)
    return [str(path) for path in paths]


def run_validate_raw(raw_files: list[str]) -> int:
    """Step 2: validate raw files. Returns the number of records."""
    return validate_raw_files(raw_files)


def run_transformation(raw_files: list[str], run_id: str) -> str:
    """Step 3: clean the data and save Parquet. Returns the file path."""
    processed = transform_weather(load_raw_files(raw_files))
    return str(save_processed(processed, run_id))


def run_quality_check(processed_path: str, run_id: str) -> str:
    """Step 4: run quality checks, save the report, fail if checks fail."""
    df = pd.read_parquet(processed_path)
    report = run_quality_checks(df, run_id=run_id)

    report_path = save_report(
        report, config.PROCESSED_DATA_DIR / f"quality_report_{run_id}.json"
    )
    save_report(report, config.PROCESSED_DATA_DIR / "quality_report_latest.json")

    if not report.passed:
        raise DataQualityError(report.summary())
    return str(report_path)


def run_load_postgres(processed_path: str, report_path: str, run_id: str) -> int:
    """Step 5: load landing table, quality report, dimensions and facts."""
    engine = postgres.get_engine()
    postgres.init_database(engine)
    df = pd.read_parquet(processed_path)
    rows = postgres.load_landing_table(engine, df, run_id)
    report: dict[str, Any] = json.loads(Path(report_path).read_text(encoding="utf-8"))
    postgres.load_quality_report(engine, report)
    postgres.load_warehouse(engine)
    return rows


def run_refresh_analytics() -> None:
    """Step 6: re-create analytics views."""
    postgres.refresh_analytics(postgres.get_engine())


def run_pipeline(past_days: int = config.PAST_DAYS, skip_db: bool = False) -> dict[str, Any]:
    """Run all steps in order and return a small summary."""
    run_id = new_run_id()
    logger.info("Starting pipeline run %s", run_id)

    raw_files = run_extraction(run_id, past_days)
    records = run_validate_raw(raw_files)
    processed_path = run_transformation(raw_files, run_id)
    report_path = run_quality_check(processed_path, run_id)

    summary: dict[str, Any] = {
        "run_id": run_id,
        "raw_files": len(raw_files),
        "raw_records": records,
        "processed_file": processed_path,
        "quality_report": report_path,
    }
    if skip_db:
        logger.info("Skipping PostgreSQL steps (--skip-db)")
    else:
        summary["rows_loaded"] = run_load_postgres(processed_path, report_path, run_id)
        run_refresh_analytics()

    logger.info("Pipeline finished: %s", summary)
    return summary


def main(argv: list[str] | None = None) -> None:
    """Command line entry point."""
    parser = argparse.ArgumentParser(description="Run the weather data pipeline")
    parser.add_argument("--past-days", type=int, default=config.PAST_DAYS)
    parser.add_argument(
        "--skip-db", action="store_true", help="stop after the quality check"
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    run_pipeline(past_days=args.past_days, skip_db=args.skip_db)


if __name__ == "__main__":
    main()

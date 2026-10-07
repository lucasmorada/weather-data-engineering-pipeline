"""Airflow DAG: weather_data_pipeline.

extract -> validate_raw -> transform -> quality_check -> load_postgres -> refresh_analytics

Each step is its own task (calling a small function from ``src.pipeline``), so
a failure is easy to find and a single task can be retried or re-run alone.
Paths are passed between tasks with XCom (small strings only, never the data).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

from src import pipeline

logger = logging.getLogger(__name__)

DEFAULT_ARGS = {
    "owner": "data-engineering-student",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


def _extract(run_id: str, **_) -> list[str]:
    logger.info("Extracting weather data (run %s)", run_id)
    return pipeline.run_extraction(run_id)


def _validate_raw(ti, **_) -> int:
    raw_files = ti.xcom_pull(task_ids="extract")
    records = pipeline.run_validate_raw(raw_files)
    logger.info("Raw files are valid: %d records", records)
    return records


def _transform(run_id: str, ti, **_) -> str:
    raw_files = ti.xcom_pull(task_ids="extract")
    path = pipeline.run_transformation(raw_files, run_id)
    logger.info("Processed file: %s", path)
    return path


def _quality_check(run_id: str, ti, **_) -> str:
    processed_path = ti.xcom_pull(task_ids="transform")
    report_path = pipeline.run_quality_check(processed_path, run_id)
    logger.info("Quality PASSED. Report: %s", report_path)
    return report_path


def _load_postgres(run_id: str, ti, **_) -> int:
    processed_path = ti.xcom_pull(task_ids="transform")
    report_path = ti.xcom_pull(task_ids="quality_check")
    rows = pipeline.run_load_postgres(processed_path, report_path, run_id)
    logger.info("Loaded %d rows", rows)
    return rows


def _refresh_analytics(**_) -> None:
    pipeline.run_refresh_analytics()
    logger.info("Analytics views refreshed")


with DAG(
    dag_id="weather_data_pipeline",
    description="Open-Meteo -> Pandas -> quality checks -> PostgreSQL -> analytics views",
    default_args=DEFAULT_ARGS,
    start_date=datetime(2026, 1, 1),
    schedule="@daily",
    catchup=False,
    max_active_runs=1,
    tags=["weather", "portfolio", "data-engineering"],
) as dag:
    run_id_template = "{{ ts_nodash }}"

    extract = PythonOperator(
        task_id="extract",
        python_callable=_extract,
        op_kwargs={"run_id": run_id_template},
    )
    validate_raw = PythonOperator(task_id="validate_raw", python_callable=_validate_raw)
    transform = PythonOperator(
        task_id="transform",
        python_callable=_transform,
        op_kwargs={"run_id": run_id_template},
    )
    quality_check = PythonOperator(
        task_id="quality_check",
        python_callable=_quality_check,
        op_kwargs={"run_id": run_id_template},
    )
    load_postgres = PythonOperator(
        task_id="load_postgres",
        python_callable=_load_postgres,
        op_kwargs={"run_id": run_id_template},
    )
    refresh_analytics = PythonOperator(
        task_id="refresh_analytics", python_callable=_refresh_analytics
    )

    extract >> validate_raw >> transform >> quality_check >> load_postgres >> refresh_analytics

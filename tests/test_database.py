"""Tests for the database layer.

No real PostgreSQL is needed: SQL files are checked as text, a throw-away SQLite
engine runs the file helper, and ``to_sql`` is mocked for the loaders.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest
from sqlalchemy import create_engine, text

from config import config
from src.database import postgres
from src.database.postgres import (
    LANDING_COLUMNS,
    DatabaseConfigError,
    build_database_url,
    load_landing_table,
    load_quality_report,
    prepare_landing_dataframe,
    run_sql_file,
    split_sql_statements,
)
from src.transformation.transform_weather import transform_weather


def test_build_database_url_uses_environment(monkeypatch):
    monkeypatch.setenv("WEATHER_DB_HOST", "db.local")
    monkeypatch.setenv("WEATHER_DB_PORT", "6543")
    monkeypatch.setenv("WEATHER_DB_NAME", "mydb")
    monkeypatch.setenv("WEATHER_DB_USER", "me")
    monkeypatch.setenv("WEATHER_DB_PASSWORD", "p@ss/word")
    url = build_database_url()
    assert url.host == "db.local"
    assert url.port == 6543
    assert url.database == "mydb"
    assert url.username == "me"
    assert url.password == "p@ss/word"  # special characters are kept safely


def test_build_database_url_requires_password(monkeypatch):
    monkeypatch.delenv("WEATHER_DB_PASSWORD", raising=False)
    with pytest.raises(DatabaseConfigError):
        build_database_url()


def test_split_sql_statements_ignores_comments_and_blank_parts():
    sql = """
    -- a comment; with a semicolon
    CREATE TABLE a (id INT);   -- trailing comment
    INSERT INTO a VALUES (1);
    """
    assert split_sql_statements(sql) == [
        "CREATE TABLE a (id INT)",
        "INSERT INTO a VALUES (1)",
    ]


def test_run_sql_file_executes_all_statements(tmp_path):
    sql_file = tmp_path / "script.sql"
    sql_file.write_text(
        "-- demo\nCREATE TABLE t (id INTEGER);\nINSERT INTO t VALUES (1);\n"
        "INSERT INTO t VALUES (2);\n",
        encoding="utf-8",
    )
    engine = create_engine("sqlite://")
    assert run_sql_file(engine, sql_file) == 3
    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM t")).scalar() == 2


def test_all_sql_files_exist():
    names = config.SQL_SETUP_FILES + [config.SQL_LOAD_WAREHOUSE_FILE]
    for name in names:
        assert (config.SQL_DIR / name).is_file(), name


def test_sql_defines_schemas_and_dimensional_model():
    schemas = (config.SQL_DIR / "01_create_schemas.sql").read_text(encoding="utf-8")
    for schema in ("raw", "warehouse", "analytics"):
        assert f"CREATE SCHEMA IF NOT EXISTS {schema}" in schemas

    dims = (config.SQL_DIR / "03_create_dimensions.sql").read_text(encoding="utf-8")
    assert "warehouse.dim_city" in dims and "warehouse.dim_date" in dims

    facts = (config.SQL_DIR / "04_create_facts.sql").read_text(encoding="utf-8")
    assert "warehouse.fact_weather" in facts
    for keyword in ("PRIMARY KEY", "REFERENCES", "NOT NULL", "UNIQUE", "CHECK"):
        assert keyword in facts


def test_sql_defines_required_analytics_views():
    views = (config.SQL_DIR / "05_create_analytics_views.sql").read_text(encoding="utf-8")
    for view in (
        "vw_daily_weather",
        "vw_city_weather_summary",
        "vw_temperature_analysis",
        "vw_precipitation_analysis",
        "vw_weather_quality",
    ):
        assert f"analytics.{view}" in views


def test_sql_scripts_are_safe_for_the_statement_splitter():
    """Scripts must not rely on '$$' blocks, which the simple splitter can't handle."""
    for name in config.SQL_SETUP_FILES + [config.SQL_LOAD_WAREHOUSE_FILE]:
        content = (config.SQL_DIR / name).read_text(encoding="utf-8")
        assert "$$" not in content, name
        assert split_sql_statements(content), name


def test_prepare_landing_dataframe_adds_run_id(raw_df):
    processed = transform_weather(raw_df)
    landing = prepare_landing_dataframe(processed, "RUN1")
    assert list(landing.columns) == ["run_id"] + LANDING_COLUMNS
    assert set(landing["run_id"]) == {"RUN1"}


def test_prepare_landing_dataframe_rejects_missing_columns():
    with pytest.raises(ValueError, match="missing columns"):
        prepare_landing_dataframe(pd.DataFrame({"city": ["Curitiba"]}), "RUN1")


def test_load_landing_table_deletes_old_batch_then_appends(monkeypatch, raw_df):
    processed = transform_weather(raw_df)
    engine = MagicMock()
    connection = engine.begin.return_value.__enter__.return_value
    to_sql = MagicMock()
    monkeypatch.setattr(pd.DataFrame, "to_sql", to_sql)

    rows = load_landing_table(engine, processed, "RUN1")

    assert rows == len(processed)
    delete_sql = str(connection.execute.call_args.args[0])
    assert "DELETE FROM raw.weather_hourly" in delete_sql
    kwargs = to_sql.call_args.kwargs
    assert kwargs["schema"] == "raw"
    assert kwargs["if_exists"] == "append"


def test_load_quality_report_inserts_one_row_per_check():
    engine = MagicMock()
    connection = engine.begin.return_value.__enter__.return_value
    report = {
        "run_id": "RUN1",
        "generated_at": "2025-01-01T00:00:00+00:00",
        "checks": [
            {"name": "a", "passed": True, "failed_rows": 0, "total_rows": 10, "message": "ok"},
            {"name": "b", "passed": True, "failed_rows": 0, "total_rows": 10, "message": "ok"},
        ],
    }
    assert load_quality_report(engine, report) == 2
    inserted_rows = connection.execute.call_args_list[-1].args[1]
    assert [row["check_name"] for row in inserted_rows] == ["a", "b"]


def test_init_database_runs_scripts_in_order(monkeypatch):
    executed = []
    monkeypatch.setattr(
        postgres, "run_sql_file", lambda engine, path: executed.append(path.name)
    )
    postgres.init_database(MagicMock())
    assert executed == config.SQL_SETUP_FILES

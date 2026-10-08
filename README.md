# Weather Data Engineering Pipeline

End-to-end weather data pipeline using Python, Open-Meteo, PostgreSQL, Airflow, Docker and Power BI.

## Project Overview

This is a learning project that I built to practice the main steps of a data
pipeline: collecting data from a public REST API, cleaning it with Pandas,
checking its quality, storing it in a PostgreSQL data warehouse and exposing
analytics views to Power BI. An Apache Airflow DAG orchestrates the whole flow
and Docker Compose provides the infrastructure.

Cities: Curitiba, São Paulo, Rio de Janeiro, Belo Horizonte and Brasília.

## Business Problem

Imagine a company that needs to follow the weather in several Brazilian cities
(for logistics, retail demand or field work). Today the analyst would have to
check websites by hand. This pipeline automates it: weather data is collected
every day, validated, stored in a clean model and ready for dashboards that
answer questions such as:

* Which city is warmer, rainier or windier?
* How many rainy days and extreme-temperature days happened?
* Can I trust the data? (quality report per run)

## Architecture

```
REST API (Open-Meteo)
        ↓
Extraction        → data/raw/ (JSON, untouched)
        ↓
Transformation    → data/processed/ (Parquet)
        ↓
Data Quality      → quality report (JSON + table)
        ↓
PostgreSQL        → schema raw (landing zone)
        ↓
Data Warehouse    → schema warehouse (dim_city, dim_date, fact_weather)
        ↓
Analytics Views   → schema analytics
        ↓
Power BI
```

Airflow runs the steps as separate tasks:
`extract → validate_raw → transform → quality_check → load_postgres → refresh_analytics`.

## Tech Stack

| Area | Tools |
|------|-------|
| Language | Python 3 |
| Data processing | Pandas, PyArrow (Parquet) |
| API | Requests, Open-Meteo (no API key) |
| Database | PostgreSQL 16, SQL, SQLAlchemy, psycopg2 |
| Orchestration | Apache Airflow 2.9 |
| Infrastructure | Docker, Docker Compose |
| Tests | Pytest |
| Visualisation | Matplotlib (notebook), Power BI |
| Version control | Git / GitHub |

## Project Structure

```
weather-data-engineering-pipeline/
├── README.md
├── .gitignore
├── .env.example
├── requirements.txt
├── pytest.ini
├── docker-compose.yml
├── Makefile
├── config/config.py             # paths, cities, thresholds, DB settings (env vars)
├── data/
│   ├── raw/                     # API responses (JSON)
│   ├── processed/               # Parquet files + quality reports
│   └── sample/
├── src/
│   ├── extraction/open_meteo.py
│   ├── transformation/transform_weather.py
│   ├── quality/quality_checks.py
│   ├── database/postgres.py
│   ├── utils.py
│   └── pipeline.py              # step functions + command line
├── sql/
│   ├── 01_create_schemas.sql
│   ├── 02_create_tables.sql
│   ├── 03_create_dimensions.sql
│   ├── 04_create_facts.sql
│   ├── 05_create_analytics_views.sql
│   └── 06_load_warehouse.sql
├── airflow/dags/weather_pipeline.py
├── tests/
├── notebooks/exploratory_analysis.ipynb
└── dashboard/README.md
```

## Data Source

[Open-Meteo](https://open-meteo.com/) is a free weather API that does not need
an API key. The project calls the forecast endpoint with `past_days` (default
7) plus the current day and requests these hourly variables:

`temperature_2m`, `apparent_temperature`, `precipitation`, `wind_speed_10m`,
`relative_humidity_2m` and `weather_code`. Units are °C, mm and km/h.
Timestamps are in local time (`America/Sao_Paulo`). Please check Open-Meteo's
terms of use before using the data commercially.

## Pipeline

Each step is a small function in `src/pipeline.py`. The command line runs all
of them in order, and Airflow runs each one as a task. Every run has a
`run_id` (a UTC timestamp) that is used in file names and database rows, so a
run can be traced and safely repeated.

## Extraction

`src/extraction/open_meteo.py`

* `fetch_city_weather()` works for any latitude/longitude and retries on temporary errors.
* Raw responses are saved unchanged (plus a small `_metadata` block) as `data/raw/date=YYYY-MM-DD/<city>_<run_id>.json`.
* If one city fails, it is logged and the others continue. If all fail, the step fails.

## Transformation

`src/transformation/transform_weather.py`

* Standardises column names and units (`temperature_celsius`, `precipitation_mm`, ...).
* Maps city spelling variants to the official names.
* Converts types and dates (invalid values become `NaN`/`NaT`).
* Removes duplicates by city + timestamp.
* Missing values: rows without city/timestamp are dropped; temperature, humidity and wind are interpolated over gaps of up to 3 hours; missing precipitation is assumed to be 0 mm.
* Derived metrics: `temperature_difference`, `precipitation_flag`, `high_wind_flag` (≥ 40 km/h), `is_rainy` (≥ 0.1 mm or a rain weather code), `is_extreme_temperature` (≥ 35 °C or ≤ 5 °C), plus 0–1 normalised columns.
* Output: Parquet in `data/processed/` (a timestamped file and `weather_latest.parquet`).

Thresholds live in `config/config.py`, so they are easy to change.

## Data Quality

`src/quality/quality_checks.py`

Before transformation, `validate_raw` checks that each raw file has all
expected variables with consistent lengths. After transformation, the quality
step runs these checks:

duplicates · null values · temperature range · humidity range · wind speed range · precipitation range · latitude · longitude · missing timestamps · unexpected cities · missing cities · invalid weather codes · empty dataset

The report says **PASSED** or **FAILED**, is saved as JSON and is also loaded
into PostgreSQL (`raw.quality_report`). If any check fails, the pipeline stops
before loading the database (`DataQualityError`).

## PostgreSQL

SQL scripts in `sql/` are written to be re-run safely (`IF NOT EXISTS`, `ON CONFLICT`).

| Schema | Purpose |
|--------|---------|
| `raw` | landing zone: `weather_hourly` (rows from each run) and `quality_report` |
| `warehouse` | dimensional model |
| `analytics` | views for Power BI |

Note: the files in `data/raw/` hold the original API responses, while the
`raw` schema holds the cleaned rows of each run (a landing table).

## Data Warehouse

Simple star schema:

* `warehouse.dim_city`: one row per city (unique name, latitude/longitude checks).
* `warehouse.dim_date`: calendar from 2020 to 2035 (pre-populated).
* `warehouse.fact_weather`: one row per city and hour, with foreign keys, `NOT NULL`, `CHECK` constraints (temperature, humidity 0–100, precipitation ≥ 0, ...), a unique key on city + timestamp and indexes on date, city and timestamp.

`06_load_warehouse.sql` upserts the data from the landing table, so running the
pipeline twice does not duplicate facts.

**Analytics views** (schema `analytics`): `vw_daily_weather`,
`vw_city_weather_summary`, `vw_temperature_analysis`, `vw_precipitation_analysis`
and `vw_weather_quality`. They include average/max/min temperature, average
humidity, total precipitation, average wind speed, rainy days and extreme
temperature days. A *rainy day* has at least 1 mm of precipitation.

## Airflow

DAG `weather_data_pipeline` (`airflow/dags/weather_pipeline.py`), scheduled `@daily`:

```
extract → validate_raw → transform → quality_check → load_postgres → refresh_analytics
```

* Each step is a separate task with dependencies.
* `retries=2`, `retry_delay=5 minutes`.
* Tasks log what they do and pass only file paths through XCom.
* `catchup=False` and `max_active_runs=1`.

## Docker

`docker-compose.yml` starts:

* `weather-postgres`: the data warehouse (port 5432 for Power BI / DBeaver).
* `airflow-postgres`: Airflow metadata database.
* `airflow-init`, `airflow-webserver` (http://localhost:8080) and `airflow-scheduler`.

The project folders are mounted into the Airflow container. It is a local
development setup, not hardened for production.

## Power BI

Power BI reads the `analytics` views. The suggested report (3 pages: Executive
Overview, City Comparison, Weather Analysis), the DAX measures and the
connection steps are in [`dashboard/README.md`](dashboard/README.md). The
`.pbix` file is not included.

## Testing

Tests use pytest and do not need internet or a real database:

* **Extraction:** parameters, retries, error handling, raw file saving.
* **Transformation:** types, duplicates, missing values, flags, normalisation, Parquet output.
* **Quality:** one test per invalid scenario plus the pass case and raw validation.
* **Database:** URL building, SQL splitting/execution (SQLite), SQL files content, loaders with mocks.

```bash
make test        # or: python -m pytest
```

## Installation / Setup Instructions

Requirements: Python 3.10+, Docker and Docker Compose (only for PostgreSQL/Airflow), Power BI Desktop (optional, Windows).

```bash
git clone https://github.com/<your-user>/weather-data-engineering-pipeline.git
cd weather-data-engineering-pipeline

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env             # then edit the passwords
```

## Usage

**1. Run only the data steps (no database):**

```bash
make run-local                   # python -m src.pipeline --skip-db
```

**2. Start PostgreSQL and Airflow:**

```bash
make init-airflow                # one time
make up
```

**3. Run the full pipeline from your machine** (needs `WEATHER_DB_HOST=localhost` in `.env`):

```bash
make run
```

**4. Or let Airflow run it:** open http://localhost:8080, enable `weather_data_pipeline` and trigger it.

**5. Explore:** open `notebooks/exploratory_analysis.ipynb` (it reads `data/processed/weather_latest.parquet`) and connect Power BI using `dashboard/README.md`.

Useful: `python -m src.pipeline --past-days 3`, `make down`, `make clean`.

## Future Improvements

* Store failed quality reports in PostgreSQL too (today only passing runs are loaded).
* Add historical backfill with the Open-Meteo archive API.
* Add data freshness checks and alerts (email/Slack) when a DAG fails.
* Use a custom Airflow Docker image instead of installing packages at start-up.
* Add CI with GitHub Actions (tests and linting).
* Add integration tests with a PostgreSQL test container.
* Incremental loading and table partitioning.
* Add more cities and weather variables.

## Author

**[Your Name]**: Software Engineering student looking for an internship in Data Engineering / Data Analytics.

* GitHub: https://github.com/your-user
* LinkedIn: https://linkedin.com/in/your-profile

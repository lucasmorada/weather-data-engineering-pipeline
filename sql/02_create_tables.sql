-- 02_create_tables.sql
-- Landing tables. They are append-only: every pipeline run adds a batch (run_id).

CREATE TABLE IF NOT EXISTS raw.weather_hourly (
    ingestion_id                  BIGSERIAL PRIMARY KEY,
    run_id                        TEXT         NOT NULL,
    city                          TEXT         NOT NULL,
    latitude                      NUMERIC(8,5),
    longitude                     NUMERIC(8,5),
    observation_timestamp         TIMESTAMP    NOT NULL,
    temperature_celsius           NUMERIC(6,2),
    apparent_temperature_celsius  NUMERIC(6,2),
    precipitation_mm              NUMERIC(7,2),
    wind_speed_kmh                NUMERIC(7,2),
    humidity_pct                  NUMERIC(6,2),
    weather_code                  SMALLINT,
    temperature_difference        NUMERIC(6,2),
    precipitation_flag            BOOLEAN,
    high_wind_flag                BOOLEAN,
    is_rainy                      BOOLEAN,
    is_extreme_temperature        BOOLEAN,
    ingested_at                   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_raw_weather_hourly_run
    ON raw.weather_hourly (run_id);
CREATE INDEX IF NOT EXISTS idx_raw_weather_hourly_city_time
    ON raw.weather_hourly (city, observation_timestamp);

-- One row per quality check and per pipeline run.
CREATE TABLE IF NOT EXISTS raw.quality_report (
    report_id      BIGSERIAL PRIMARY KEY,
    run_id         TEXT        NOT NULL,
    run_timestamp  TIMESTAMPTZ NOT NULL,
    check_name     TEXT        NOT NULL,
    passed         BOOLEAN     NOT NULL,
    failed_rows    INTEGER     NOT NULL CHECK (failed_rows >= 0),
    total_rows     INTEGER     NOT NULL CHECK (total_rows >= 0),
    message        TEXT,
    CONSTRAINT uq_quality_report_run_check UNIQUE (run_id, check_name)
);

CREATE INDEX IF NOT EXISTS idx_quality_report_run_timestamp
    ON raw.quality_report (run_timestamp);

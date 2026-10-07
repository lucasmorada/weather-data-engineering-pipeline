-- 04_create_facts.sql
-- Fact table: one row per city per hour.

CREATE TABLE IF NOT EXISTS warehouse.fact_weather (
    weather_key                   BIGSERIAL PRIMARY KEY,
    city_key                      INTEGER      NOT NULL REFERENCES warehouse.dim_city (city_key),
    date_key                      INTEGER      NOT NULL REFERENCES warehouse.dim_date (date_key),
    observation_timestamp         TIMESTAMP    NOT NULL,
    hour_of_day                   SMALLINT     NOT NULL CHECK (hour_of_day BETWEEN 0 AND 23),
    temperature_celsius           NUMERIC(5,2) NOT NULL CHECK (temperature_celsius BETWEEN -90 AND 60),
    apparent_temperature_celsius  NUMERIC(5,2) NOT NULL CHECK (apparent_temperature_celsius BETWEEN -90 AND 60),
    temperature_difference        NUMERIC(5,2) NOT NULL,
    precipitation_mm              NUMERIC(6,2) NOT NULL CHECK (precipitation_mm >= 0),
    wind_speed_kmh                NUMERIC(6,2) NOT NULL CHECK (wind_speed_kmh >= 0),
    humidity_pct                  NUMERIC(5,2) NOT NULL CHECK (humidity_pct BETWEEN 0 AND 100),
    weather_code                  SMALLINT     NOT NULL CHECK (weather_code BETWEEN 0 AND 99),
    precipitation_flag            BOOLEAN      NOT NULL DEFAULT FALSE,
    high_wind_flag                BOOLEAN      NOT NULL DEFAULT FALSE,
    is_rainy                      BOOLEAN      NOT NULL DEFAULT FALSE,
    is_extreme_temperature        BOOLEAN      NOT NULL DEFAULT FALSE,
    loaded_at                     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_fact_weather_city_time UNIQUE (city_key, observation_timestamp)
);

CREATE INDEX IF NOT EXISTS idx_fact_weather_date ON warehouse.fact_weather (date_key);
CREATE INDEX IF NOT EXISTS idx_fact_weather_city ON warehouse.fact_weather (city_key);
CREATE INDEX IF NOT EXISTS idx_fact_weather_timestamp ON warehouse.fact_weather (observation_timestamp);

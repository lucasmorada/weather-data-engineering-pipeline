-- 06_load_warehouse.sql
-- Upsert dimensions and facts from the landing table (idempotent).
-- If the same city + hour was loaded in several runs, the newest ingestion wins.

INSERT INTO warehouse.dim_city (city_name, latitude, longitude)
SELECT DISTINCT ON (city) city, latitude, longitude
FROM raw.weather_hourly
WHERE latitude IS NOT NULL AND longitude IS NOT NULL
ORDER BY city, ingested_at DESC
ON CONFLICT (city_name) DO UPDATE
SET latitude   = EXCLUDED.latitude,
    longitude  = EXCLUDED.longitude,
    updated_at = NOW();

INSERT INTO warehouse.fact_weather (
    city_key, date_key, observation_timestamp, hour_of_day,
    temperature_celsius, apparent_temperature_celsius, temperature_difference,
    precipitation_mm, wind_speed_kmh, humidity_pct, weather_code,
    precipitation_flag, high_wind_flag, is_rainy, is_extreme_temperature
)
SELECT
    c.city_key,
    CAST(TO_CHAR(l.observation_timestamp, 'YYYYMMDD') AS INTEGER),
    l.observation_timestamp,
    CAST(EXTRACT(HOUR FROM l.observation_timestamp) AS SMALLINT),
    l.temperature_celsius,
    l.apparent_temperature_celsius,
    l.temperature_difference,
    l.precipitation_mm,
    l.wind_speed_kmh,
    l.humidity_pct,
    l.weather_code,
    COALESCE(l.precipitation_flag, FALSE),
    COALESCE(l.high_wind_flag, FALSE),
    COALESCE(l.is_rainy, FALSE),
    COALESCE(l.is_extreme_temperature, FALSE)
FROM (
    SELECT DISTINCT ON (city, observation_timestamp) *
    FROM raw.weather_hourly
    ORDER BY city, observation_timestamp, ingested_at DESC, ingestion_id DESC
) AS l
JOIN warehouse.dim_city AS c ON c.city_name = l.city
ON CONFLICT (city_key, observation_timestamp) DO UPDATE
SET temperature_celsius          = EXCLUDED.temperature_celsius,
    apparent_temperature_celsius = EXCLUDED.apparent_temperature_celsius,
    temperature_difference       = EXCLUDED.temperature_difference,
    precipitation_mm             = EXCLUDED.precipitation_mm,
    wind_speed_kmh               = EXCLUDED.wind_speed_kmh,
    humidity_pct                 = EXCLUDED.humidity_pct,
    weather_code                 = EXCLUDED.weather_code,
    precipitation_flag           = EXCLUDED.precipitation_flag,
    high_wind_flag               = EXCLUDED.high_wind_flag,
    is_rainy                     = EXCLUDED.is_rainy,
    is_extreme_temperature       = EXCLUDED.is_extreme_temperature,
    loaded_at                    = NOW();

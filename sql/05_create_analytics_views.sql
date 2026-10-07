-- 05_create_analytics_views.sql
-- Views for Power BI. Definitions used in the metrics:
--   rainy day                = total precipitation of the day >= 1.0 mm
--   extreme temperature day  = at least one hour at or above 35 C or at or below 5 C
--   (hourly flags come from the transformation step)

CREATE OR REPLACE VIEW analytics.vw_daily_weather AS
SELECT
    c.city_name,
    c.latitude,
    c.longitude,
    d.full_date,
    d.year_number,
    d.month_number,
    d.month_name,
    d.day_name,
    COUNT(*)                                          AS observation_count,
    ROUND(AVG(f.temperature_celsius), 2)              AS avg_temperature_celsius,
    MAX(f.temperature_celsius)                        AS max_temperature_celsius,
    MIN(f.temperature_celsius)                        AS min_temperature_celsius,
    ROUND(AVG(f.apparent_temperature_celsius), 2)     AS avg_apparent_temperature_celsius,
    ROUND(AVG(f.humidity_pct), 2)                     AS avg_humidity_pct,
    ROUND(SUM(f.precipitation_mm), 2)                 AS total_precipitation_mm,
    MAX(f.precipitation_mm)                           AS max_hourly_precipitation_mm,
    ROUND(AVG(f.wind_speed_kmh), 2)                   AS avg_wind_speed_kmh,
    MAX(f.wind_speed_kmh)                             AS max_wind_speed_kmh,
    COUNT(*) FILTER (WHERE f.is_rainy)                AS rainy_hours,
    COUNT(*) FILTER (WHERE f.high_wind_flag)          AS high_wind_hours,
    COUNT(*) FILTER (WHERE f.is_extreme_temperature)  AS extreme_temperature_hours,
    SUM(f.precipitation_mm) >= 1.0                    AS is_rainy_day,
    COUNT(*) FILTER (WHERE f.is_extreme_temperature) > 0 AS is_extreme_temperature_day
FROM warehouse.fact_weather AS f
JOIN warehouse.dim_city AS c ON c.city_key = f.city_key
JOIN warehouse.dim_date AS d ON d.date_key = f.date_key
GROUP BY
    c.city_name, c.latitude, c.longitude,
    d.full_date, d.year_number, d.month_number, d.month_name, d.day_name;

CREATE OR REPLACE VIEW analytics.vw_city_weather_summary AS
WITH hourly AS (
    SELECT
        c.city_name,
        MIN(d.full_date)                              AS first_date,
        MAX(d.full_date)                              AS last_date,
        COUNT(*)                                      AS observation_count,
        ROUND(AVG(f.temperature_celsius), 2)          AS avg_temperature_celsius,
        MAX(f.temperature_celsius)                    AS max_temperature_celsius,
        MIN(f.temperature_celsius)                    AS min_temperature_celsius,
        ROUND(AVG(f.humidity_pct), 2)                 AS avg_humidity_pct,
        ROUND(SUM(f.precipitation_mm), 2)             AS total_precipitation_mm,
        ROUND(AVG(f.wind_speed_kmh), 2)               AS avg_wind_speed_kmh
    FROM warehouse.fact_weather AS f
    JOIN warehouse.dim_city AS c ON c.city_key = f.city_key
    JOIN warehouse.dim_date AS d ON d.date_key = f.date_key
    GROUP BY c.city_name
),
daily AS (
    SELECT
        city_name,
        COUNT(*)                                          AS days_covered,
        COUNT(*) FILTER (WHERE is_rainy_day)              AS rainy_days,
        COUNT(*) FILTER (WHERE is_extreme_temperature_day) AS extreme_temperature_days
    FROM analytics.vw_daily_weather
    GROUP BY city_name
)
SELECT
    h.city_name,
    h.first_date,
    h.last_date,
    dl.days_covered,
    h.observation_count,
    h.avg_temperature_celsius,
    h.max_temperature_celsius,
    h.min_temperature_celsius,
    h.avg_humidity_pct,
    h.total_precipitation_mm,
    h.avg_wind_speed_kmh,
    dl.rainy_days,
    dl.extreme_temperature_days
FROM hourly AS h
JOIN daily AS dl ON dl.city_name = h.city_name;

CREATE OR REPLACE VIEW analytics.vw_temperature_analysis AS
SELECT
    city_name,
    full_date,
    avg_temperature_celsius,
    max_temperature_celsius,
    min_temperature_celsius,
    max_temperature_celsius - min_temperature_celsius AS temperature_range_celsius,
    avg_apparent_temperature_celsius,
    ROUND(avg_temperature_celsius - avg_apparent_temperature_celsius, 2) AS avg_temperature_difference,
    extreme_temperature_hours,
    is_extreme_temperature_day,
    ROUND(
        AVG(avg_temperature_celsius) OVER (
            PARTITION BY city_name
            ORDER BY full_date
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ), 2
    ) AS moving_avg_7d_temperature_celsius
FROM analytics.vw_daily_weather;

CREATE OR REPLACE VIEW analytics.vw_precipitation_analysis AS
SELECT
    city_name,
    full_date,
    year_number,
    month_number,
    month_name,
    total_precipitation_mm,
    max_hourly_precipitation_mm,
    rainy_hours,
    is_rainy_day,
    avg_humidity_pct,
    ROUND(
        SUM(total_precipitation_mm) OVER (
            PARTITION BY city_name, year_number, month_number
            ORDER BY full_date
        ), 2
    ) AS month_to_date_precipitation_mm
FROM analytics.vw_daily_weather;

-- Quality results of every pipeline run (is_latest_run = TRUE for the newest run).
CREATE OR REPLACE VIEW analytics.vw_weather_quality AS
SELECT
    q.run_id,
    q.run_timestamp,
    q.check_name,
    q.passed,
    q.failed_rows,
    q.total_rows,
    CASE
        WHEN q.total_rows > 0
        THEN ROUND(100.0 * (q.total_rows - q.failed_rows) / q.total_rows, 2)
        ELSE NULL
    END AS valid_rows_pct,
    q.message,
    BOOL_AND(q.passed) OVER (PARTITION BY q.run_id) AS run_passed,
    q.run_id = (
        SELECT r.run_id
        FROM raw.quality_report AS r
        ORDER BY r.run_timestamp DESC, r.report_id DESC
        LIMIT 1
    ) AS is_latest_run
FROM raw.quality_report AS q;

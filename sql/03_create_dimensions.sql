-- 03_create_dimensions.sql
-- Dimension tables of the star schema.

CREATE TABLE IF NOT EXISTS warehouse.dim_city (
    city_key    SERIAL PRIMARY KEY,
    city_name   VARCHAR(100)  NOT NULL,
    latitude    NUMERIC(8,5)  NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude   NUMERIC(8,5)  NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    created_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_dim_city_name UNIQUE (city_name)
);

CREATE TABLE IF NOT EXISTS warehouse.dim_date (
    date_key       INTEGER      PRIMARY KEY,   -- format YYYYMMDD
    full_date      DATE         NOT NULL,
    year_number    SMALLINT     NOT NULL,
    quarter_number SMALLINT     NOT NULL CHECK (quarter_number BETWEEN 1 AND 4),
    month_number   SMALLINT     NOT NULL CHECK (month_number BETWEEN 1 AND 12),
    month_name     VARCHAR(20)  NOT NULL,
    day_of_month   SMALLINT     NOT NULL CHECK (day_of_month BETWEEN 1 AND 31),
    day_of_week    SMALLINT     NOT NULL CHECK (day_of_week BETWEEN 1 AND 7),  -- 1 = Monday
    day_name       VARCHAR(20)  NOT NULL,
    week_of_year   SMALLINT     NOT NULL CHECK (week_of_year BETWEEN 1 AND 53),
    is_weekend     BOOLEAN      NOT NULL,
    CONSTRAINT uq_dim_date_full_date UNIQUE (full_date)
);

-- Pre-populate the calendar (2020-2035). Facts outside this range need new dates.
INSERT INTO warehouse.dim_date (
    date_key, full_date, year_number, quarter_number, month_number, month_name,
    day_of_month, day_of_week, day_name, week_of_year, is_weekend
)
SELECT
    CAST(TO_CHAR(d, 'YYYYMMDD') AS INTEGER),
    CAST(d AS DATE),
    CAST(EXTRACT(YEAR FROM d) AS SMALLINT),
    CAST(EXTRACT(QUARTER FROM d) AS SMALLINT),
    CAST(EXTRACT(MONTH FROM d) AS SMALLINT),
    TRIM(TO_CHAR(d, 'Month')),
    CAST(EXTRACT(DAY FROM d) AS SMALLINT),
    CAST(EXTRACT(ISODOW FROM d) AS SMALLINT),
    TRIM(TO_CHAR(d, 'Day')),
    CAST(EXTRACT(WEEK FROM d) AS SMALLINT),
    EXTRACT(ISODOW FROM d) IN (6, 7)
FROM generate_series(DATE '2020-01-01', DATE '2035-12-31', INTERVAL '1 day') AS d
ON CONFLICT (date_key) DO NOTHING;

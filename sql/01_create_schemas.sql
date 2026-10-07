-- 01_create_schemas.sql
-- Three layers:
--   raw       landing zone: validated rows exactly as produced by the Pandas step
--   warehouse dimensional model (dim_city, dim_date, fact_weather)
--   analytics views that Power BI reads

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS warehouse;
CREATE SCHEMA IF NOT EXISTS analytics;

COMMENT ON SCHEMA raw IS 'Landing zone: rows loaded by the pipeline, one batch per run_id';
COMMENT ON SCHEMA warehouse IS 'Dimensional model used for analysis';
COMMENT ON SCHEMA analytics IS 'Views consumed by Power BI';

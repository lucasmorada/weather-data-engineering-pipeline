# Power BI Dashboard Guide

This folder documents how to build the dashboard. There is no `.pbix` file in
the repository on purpose: the report must be built on top of **your own** data.

## 1. Connect Power BI to PostgreSQL

1. Start the stack (`make up`) and run the pipeline at least once.
2. In Power BI Desktop: **Get Data → PostgreSQL database**.
3. Server: `localhost:5432` (use the port from your `.env`). Database: `weather_dw`.
4. Choose **Import** mode (the data is small and refreshes daily).
5. Authenticate with the user/password from your `.env` file.
6. In the Navigator, select the views from the `analytics` schema:

| View | Grain | Used for |
|------|-------|----------|
| `analytics.vw_daily_weather` | city + day | main fact table of the report |
| `analytics.vw_city_weather_summary` | city | KPIs and city comparison |
| `analytics.vw_temperature_analysis` | city + day | temperature trends |
| `analytics.vw_precipitation_analysis` | city + day | rain analysis |
| `analytics.vw_weather_quality` | run + check | data quality page/tooltip |

> Tip: Power BI may ask for the Npgsql driver the first time. Install it from
> the Microsoft prompt if needed.

## 2. Suggested model

Relate `vw_city_weather_summary[city_name]` (one) to each daily view
`[city_name]` (many) and use it as the city slicer table.

## 3. Suggested DAX measures

```DAX
Avg Temperature = AVERAGE ( vw_daily_weather[avg_temperature_celsius] )
Max Temperature = MAX ( vw_daily_weather[max_temperature_celsius] )
Min Temperature = MIN ( vw_daily_weather[min_temperature_celsius] )
Avg Humidity    = AVERAGE ( vw_daily_weather[avg_humidity_pct] )
Total Precipitation = SUM ( vw_daily_weather[total_precipitation_mm] )
Avg Wind Speed  = AVERAGE ( vw_daily_weather[avg_wind_speed_kmh] )
Rainy Days      = CALCULATE ( COUNTROWS ( vw_daily_weather ), vw_daily_weather[is_rainy_day] = TRUE () )
Extreme Temperature Days =
    CALCULATE ( COUNTROWS ( vw_daily_weather ), vw_daily_weather[is_extreme_temperature_day] = TRUE () )
```

Metric definitions (also documented in `sql/05_create_analytics_views.sql`):

* **Rainy day**: total precipitation of the day ≥ 1.0 mm.
* **Extreme temperature day**: at least one hour ≥ 35 °C or ≤ 5 °C.

## 4. Suggested pages

### Page 1 – Executive Overview

* **KPI cards:** Average Temperature, Total Precipitation, Average Humidity, Average Wind Speed.
* Line chart: average temperature by day.
* Slicers: city and date range.
* Small card: latest data quality status (from `vw_weather_quality`, filter `is_latest_run = TRUE`, field `run_passed`).

### Page 2 – City Comparison

* Clustered bar: average temperature by city.
* Clustered bar: total precipitation by city.
* Table with `vw_city_weather_summary` columns (min/max/avg temperature, humidity, wind, rainy days, extreme temperature days).
* Optional map using `latitude` and `longitude` from `vw_daily_weather`.

### Page 3 – Weather Analysis

* **Temperature:** daily min/avg/max plus `moving_avg_7d_temperature_celsius` from `vw_temperature_analysis`.
* **Precipitation:** daily columns and `month_to_date_precipitation_mm` from `vw_precipitation_analysis`.
* **Humidity:** line chart of `avg_humidity_pct`.
* **Wind:** line chart of `avg_wind_speed_kmh` and `max_wind_speed_kmh`.
* **Rainy days:** card or bar chart with the `Rainy Days` measure by city.

## 5. Refreshing

The Airflow DAG recreates the views and loads new data every day. In Power BI
Desktop click **Refresh**. In the Power BI Service you would need an on-premises
data gateway to reach a local PostgreSQL (not covered in this project).

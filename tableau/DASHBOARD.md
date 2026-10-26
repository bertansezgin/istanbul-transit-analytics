# Tableau Public dashboard

The CSV files in `tableau/data/` are produced by `python analysis/report.py`. Each is one mart table.

## Data sources

| File | Grain | Used for |
|---|---|---|
| `mart_monthly_kpis.csv` | month | KPI cards, recovery line, fare mix |
| `mart_daily.csv` | day | daily trend, weekday/weekend, holiday filter |
| `mart_mode_monthly.csv` | month x mode | mode share area chart |
| `mart_hourly_profile.csv` | year x mode x day type x hour | peak-hour chart |
| `mart_station_yearly.csv` | year x station x line | top stations bar |
| `mart_line_yearly.csv` | year x line | top lines table with growth |
| `mart_district_monthly.csv` | month x district | district ranking / map |
| `mart_holiday_effect.csv` | holiday day | holiday impact bar |

## Dashboard 1: Overview

1. **KPI cards** (latest full year, from `mart_monthly_kpis`): total boardings, average daily boardings,
   YoY change (`yoy_change`), transfer share, discounted share.
2. **Recovery line:** `year_month` vs. `recovery_index`, reference line at 100, band for the
   Covid restriction period (Mar 2020 to Jun 2021).
3. **Mode share:** stacked area of `share_of_month` by `mode` from `mart_mode_monthly`.
4. **Filters:** year (drives the cards), mode.

## Dashboard 2: When and where people travel

1. **Hourly profile:** `hour` vs. `avg_passages`, colour by `mode`, columns by `day_type`, filter on `year`.
2. **Top stations:** bar of `passages` from `mart_station_yearly`, top 15 by `rank_in_year`, colour by `mode`.
3. **Top lines:** table from `mart_line_yearly` with `passages`, `yoy_change` and a growth colour scale.
4. **Districts:** bar or map of `passages` by `district` (Tableau can geocode Istanbul districts by name).

## Dashboard 3: Calendar effects

1. **Holiday impact:** bar of average `change_vs_baseline` by `holiday_name` from `mart_holiday_effect`.
2. **Daily heatmap:** `mart_daily`, weekday on rows, week number on columns, colour by `passages`.

## Publishing

Tableau Public > File > Save to Tableau Public. Put the public link in the README and on the CV.

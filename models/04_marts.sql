-- Marts: business-facing tables. These feed the analysis and the Tableau extracts.
-- Main metric is `passages` (validated boardings, one per card tap). `passengers` is also kept.

-- Daily totals with calendar context, the base for most KPIs.
CREATE OR REPLACE TABLE mart_daily AS
SELECT
    f.date, d.year, d.month, d.year_month, d.weekday_name, d.day_type, d.holiday_name,
    d.covid_restriction_period,
    sum(f.passages)                                                       AS passages,
    sum(f.passengers)                                                     AS passengers,
    sum(f.passages) FILTER (WHERE f.is_transfer)                          AS transfer_passages,
    sum(f.passages) FILTER (WHERE fa.fare_segment = 'Discounted')         AS discounted_passages,
    sum(f.passages) FILTER (WHERE fa.fare_segment = 'Free')               AS free_passages,
    sum(f.passages) FILTER (WHERE m.mode = 'Bus')                         AS bus_passages,
    sum(f.passages) FILTER (WHERE m.mode = 'Rail')                        AS rail_passages,
    sum(f.passages) FILTER (WHERE m.mode = 'Sea')                         AS sea_passages
FROM fct_daily_ridership f
JOIN dim_date d USING (date)
LEFT JOIN (SELECT DISTINCT road_type, mode FROM dim_mode) m USING (road_type)
LEFT JOIN dim_fare fa USING (product_kind, transaction_type)
GROUP BY ALL;

-- Monthly KPIs. `days_with_data` exposes incomplete months instead of hiding them.
CREATE OR REPLACE TABLE mart_monthly_kpis AS
WITH m AS (
    SELECT
        year_month, min(year) AS year, min(month) AS month,
        count(*)                                                    AS days_with_data,
        day(last_day(min(date)))                                    AS days_in_month,
        sum(passages)                                               AS passages,
        sum(passages) / count(*)                                    AS avg_daily_passages,
        avg(passages) FILTER (WHERE day_type = 'Weekday')           AS avg_weekday_passages,
        avg(passages) FILTER (WHERE day_type = 'Weekend')           AS avg_weekend_passages,
        sum(transfer_passages)   / sum(passages)                    AS transfer_share,
        sum(discounted_passages) / sum(passages)                    AS discounted_share,
        sum(free_passages)       / sum(passages)                    AS free_share,
        sum(bus_passages)        / sum(passages)                    AS bus_share,
        sum(rail_passages)       / sum(passages)                    AS rail_share,
        sum(sea_passages)        / sum(passages)                    AS sea_share
    FROM mart_daily
    GROUP BY year_month
)
SELECT
    m.*,
    q.issue                                                               AS source_issue,
    days_with_data = days_in_month AND q.issue IS NULL                    AS is_complete_month,
    avg_weekend_passages / avg_weekday_passages                           AS weekend_to_weekday_ratio,
    avg_daily_passages / lag(avg_daily_passages) OVER (ORDER BY year_month) - 1   AS mom_change,
    avg_daily_passages / lag(avg_daily_passages, 12) OVER (ORDER BY year_month) - 1 AS yoy_change,
    -- Recovery index: average daily boardings vs. the pre-pandemic baseline (Jan-Feb 2020 = 100).
    100 * avg_daily_passages / (
        SELECT sum(passages) / count(*) FROM mart_daily WHERE date < DATE '2020-03-01'
    )                                                                     AS recovery_index
FROM m
LEFT JOIN dim_month_quality q USING (year_month)
ORDER BY year_month;

-- Monthly volume and share by mode.
CREATE OR REPLACE TABLE mart_mode_monthly AS
WITH t AS (
    SELECT d.year_month, m.mode, sum(f.passages) AS passages
    FROM fct_daily_ridership f
    JOIN dim_date d USING (date)
    JOIN (SELECT DISTINCT road_type, mode FROM dim_mode) m USING (road_type)
    GROUP BY d.year_month, m.mode
)
SELECT *, passages / sum(passages) OVER (PARTITION BY year_month) AS share_of_month
FROM t;

-- Average boardings per hour, by mode and day type (one average day).
CREATE OR REPLACE TABLE mart_hourly_profile AS
WITH per_day AS (
    SELECT h.date, h.hour, m.mode, d.day_type, d.year, sum(h.passages) AS passages
    FROM fct_hourly_ridership h
    JOIN dim_date d USING (date)
    JOIN (SELECT DISTINCT road_type, mode FROM dim_mode) m USING (road_type)
    WHERE NOT d.covid_restriction_period
    GROUP BY ALL
)
SELECT year, mode, day_type, hour, avg(passages) AS avg_passages
FROM per_day
GROUP BY ALL;

-- Yearly line ranking with growth vs. the previous year (same months only, so partial years compare fairly).
CREATE OR REPLACE TABLE mart_line_yearly AS
WITH y AS (
    SELECT d.year, f.line_code, f.road_type, list_distinct(list(l.route_name))[1] AS route_name,
           count(DISTINCT d.month) AS months, sum(f.passages) AS passages
    FROM fct_daily_ridership f
    JOIN dim_date d USING (date)
    JOIN dim_line l USING (line_key)
    WHERE f.line_code IS NOT NULL AND f.line_code <> ''
    GROUP BY ALL
)
SELECT
    y.*, m.mode,
    rank() OVER (PARTITION BY y.year ORDER BY y.passages DESC)                  AS rank_in_year,
    y.passages / lag(y.passages) OVER (PARTITION BY y.line_code, y.road_type ORDER BY y.year) - 1 AS yoy_change
FROM y
JOIN (SELECT DISTINCT road_type, mode FROM dim_mode) m USING (road_type);

-- District volume by month.
CREATE OR REPLACE TABLE mart_district_monthly AS
SELECT d.year_month, f.district, sum(f.passages) AS passages
FROM fct_daily_ridership f
JOIN dim_date d USING (date)
WHERE f.district IS NOT NULL AND f.district <> ''
GROUP BY ALL;

-- Busiest stations per year (rail and sea, where the source reports a station).
CREATE OR REPLACE TABLE mart_station_yearly AS
WITH t AS (
    SELECT year(s.date) AS year, s.station, s.line_code, m.mode,
           any_value(s.district) AS district, sum(s.passages) AS passages
    FROM fct_station_daily s
    JOIN (SELECT DISTINCT road_type, mode FROM dim_mode) m USING (road_type)
    GROUP BY year(s.date), s.station, s.line_code, m.mode
)
SELECT *, rank() OVER (PARTITION BY year ORDER BY passages DESC) AS rank_in_year
FROM t;

-- Holiday effect: each holiday day vs. the average of the same weekday in the 4 weeks around it
-- (non-holiday days only).
CREATE OR REPLACE TABLE mart_holiday_effect AS
WITH b AS (
    SELECT h.date, h.year, h.holiday_name, h.weekday_name, h.passages, avg(o.passages) AS baseline_passages
    FROM mart_daily h
    JOIN mart_daily o
      ON o.holiday_name IS NULL
     AND o.weekday_name = h.weekday_name
     AND o.date BETWEEN h.date - INTERVAL 28 DAY AND h.date + INTERVAL 28 DAY
    WHERE h.holiday_name IS NOT NULL
    GROUP BY ALL
)
SELECT *, passages / baseline_passages - 1 AS change_vs_baseline
FROM b;

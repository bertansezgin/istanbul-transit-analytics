-- Dimensions (star schema). Grain of each table is stated above it.

-- One row per calendar day in the data.
CREATE OR REPLACE TABLE dim_date AS
WITH days AS (
    SELECT unnest(range(min(date), max(date) + INTERVAL 1 DAY, INTERVAL 1 DAY))::DATE AS date
    FROM stg_daily_line
),
holidays(date, holiday) AS (
    VALUES
    -- Fixed national holidays
    ('2020-01-01','New Year'),('2021-01-01','New Year'),('2022-01-01','New Year'),('2023-01-01','New Year'),('2024-01-01','New Year'),
    ('2020-04-23','National Sovereignty Day'),('2021-04-23','National Sovereignty Day'),('2022-04-23','National Sovereignty Day'),('2023-04-23','National Sovereignty Day'),('2024-04-23','National Sovereignty Day'),
    ('2020-05-01','Labour Day'),('2021-05-01','Labour Day'),('2022-05-01','Labour Day'),('2023-05-01','Labour Day'),('2024-05-01','Labour Day'),
    ('2020-05-19','Youth and Sports Day'),('2021-05-19','Youth and Sports Day'),('2022-05-19','Youth and Sports Day'),('2023-05-19','Youth and Sports Day'),('2024-05-19','Youth and Sports Day'),
    ('2020-07-15','Democracy Day'),('2021-07-15','Democracy Day'),('2022-07-15','Democracy Day'),('2023-07-15','Democracy Day'),('2024-07-15','Democracy Day'),
    ('2020-08-30','Victory Day'),('2021-08-30','Victory Day'),('2022-08-30','Victory Day'),('2023-08-30','Victory Day'),('2024-08-30','Victory Day'),
    ('2020-10-29','Republic Day'),('2021-10-29','Republic Day'),('2022-10-29','Republic Day'),('2023-10-29','Republic Day'),('2024-10-29','Republic Day'),
    -- Ramadan Feast
    ('2020-05-24','Ramadan Feast'),('2020-05-25','Ramadan Feast'),('2020-05-26','Ramadan Feast'),
    ('2021-05-13','Ramadan Feast'),('2021-05-14','Ramadan Feast'),('2021-05-15','Ramadan Feast'),
    ('2022-05-02','Ramadan Feast'),('2022-05-03','Ramadan Feast'),('2022-05-04','Ramadan Feast'),
    ('2023-04-21','Ramadan Feast'),('2023-04-22','Ramadan Feast'),('2023-04-23','Ramadan Feast'),
    ('2024-04-10','Ramadan Feast'),('2024-04-11','Ramadan Feast'),('2024-04-12','Ramadan Feast'),
    -- Feast of Sacrifice
    ('2020-07-31','Feast of Sacrifice'),('2020-08-01','Feast of Sacrifice'),('2020-08-02','Feast of Sacrifice'),('2020-08-03','Feast of Sacrifice'),
    ('2021-07-20','Feast of Sacrifice'),('2021-07-21','Feast of Sacrifice'),('2021-07-22','Feast of Sacrifice'),('2021-07-23','Feast of Sacrifice'),
    ('2022-07-09','Feast of Sacrifice'),('2022-07-10','Feast of Sacrifice'),('2022-07-11','Feast of Sacrifice'),('2022-07-12','Feast of Sacrifice'),
    ('2023-06-28','Feast of Sacrifice'),('2023-06-29','Feast of Sacrifice'),('2023-06-30','Feast of Sacrifice'),('2023-07-01','Feast of Sacrifice'),
    ('2024-06-16','Feast of Sacrifice'),('2024-06-17','Feast of Sacrifice'),('2024-06-18','Feast of Sacrifice'),('2024-06-19','Feast of Sacrifice')
)
SELECT
    d.date,
    year(d.date)                                   AS year,
    month(d.date)                                  AS month,
    strftime(d.date, '%Y-%m')                      AS year_month,
    isodow(d.date)                                 AS iso_weekday,       -- 1 = Monday
    strftime(d.date, '%A')                         AS weekday_name,
    isodow(d.date) >= 6                            AS is_weekend,
    h.holiday IS NOT NULL                          AS is_holiday,
    h.holiday                                      AS holiday_name,
    CASE
        WHEN h.holiday IS NOT NULL THEN 'Holiday'
        WHEN isodow(d.date) >= 6 THEN 'Weekend'
        ELSE 'Weekday'
    END                                            AS day_type,
    -- Context flag for the 2020-2021 restriction period, used to read the recovery curve.
    d.date BETWEEN DATE '2020-03-16' AND DATE '2021-06-30' AS covid_restriction_period
FROM days d
LEFT JOIN (SELECT CAST(date AS DATE) AS date, any_value(holiday) AS holiday FROM holidays GROUP BY 1) h USING (date);

-- Known source issues, one row per affected month. Evidence is in docs/data_quality.md:
-- these files are 4-6x smaller than neighbouring months and daily boardings drop to 17-34%
-- of July 2024, while line and district coverage stays normal, so rows are missing, not riders.
CREATE OR REPLACE TABLE dim_month_quality AS
SELECT * FROM (VALUES
    ('2024-08', 'Partial publication: about 17% of normal daily volume'),
    ('2024-09', 'Partial publication: about 25% of normal daily volume'),
    ('2024-10', 'Partial publication: about 35% of normal daily volume, 18 days')
) AS t(year_month, issue);

-- One row per transport mode.
CREATE OR REPLACE TABLE dim_mode AS
SELECT DISTINCT
    transport_type_id,
    road_type,
    CASE
        WHEN road_type = 'OTOYOL'                   THEN 'Bus'
        WHEN road_type = 'RAYLI'                    THEN 'Rail'
        WHEN road_type IN ('DENİZ', 'DENIZ')        THEN 'Sea'
        ELSE 'Other'
    END AS mode
FROM stg_daily_line;

-- One row per line (code + route name). A code can serve several route names over time.
CREATE OR REPLACE TABLE dim_line AS
SELECT
    md5(concat_ws('|', road_type, line_code, line))  AS line_key,
    road_type,
    line_code,
    line                                            AS route_name,
    min(date)                                       AS first_seen,
    max(date)                                       AS last_seen
FROM stg_daily_line
GROUP BY ALL;

-- One row per card product / transaction combination.
-- product_kind is the card holder group; transaction_type is how the ride was paid.
CREATE OR REPLACE TABLE dim_fare AS
SELECT DISTINCT
    product_kind,
    transaction_type,
    CASE
        WHEN product_kind = 'TAM'                 THEN 'Full fare'
        WHEN product_kind LIKE 'INDIRIMLI%'       THEN 'Discounted'
        WHEN product_kind = 'UCRETSIZ'            THEN 'Free'
        ELSE 'Staff and service'                  -- PERSONEL, DENETIM, KULLANILMAYAN_GRUBU, GIRIS_CIKIS
    END AS fare_segment,
    CASE
        WHEN transaction_type ILIKE '%Aktarma%'   THEN 'Transfer'
        WHEN transaction_type ILIKE '%Abonman%'   THEN 'Subscription'
        WHEN transaction_type ILIKE '%Kontur%'    THEN 'Pay per ride'
        WHEN transaction_type ILIKE 'Ucretsiz%'   THEN 'Free ride'
        ELSE 'Single ticket'                      -- TekliBilet, Marmaray Bilet
    END AS payment_type
FROM stg_daily_line;

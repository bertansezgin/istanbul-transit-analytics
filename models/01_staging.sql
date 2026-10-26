-- Staging: read the monthly Parquet aggregates and give columns stable names and types.

CREATE OR REPLACE VIEW stg_daily_line AS
SELECT
    CAST(date AS DATE)                         AS date,
    CAST(transport_type_id AS INTEGER)         AS transport_type_id,
    upper(trim(road_type))                     AS road_type,
    trim(line)                                 AS line,
    upper(trim(line_name))                     AS line_code,
    trim(transfer_type)                        AS transfer_type,
    upper(trim(product_kind))                  AS product_kind,
    trim(transaction_type_desc)                AS transaction_type,
    upper(trim(town))                          AS district,
    CAST(passages AS BIGINT)                   AS passages,
    CAST(passengers AS BIGINT)                 AS passengers
FROM read_parquet('data/agg/daily_line/*.parquet');

CREATE OR REPLACE VIEW stg_hourly_mode AS
SELECT
    CAST(date AS DATE)                         AS date,
    CAST(hour AS INTEGER)                      AS hour,
    CAST(transport_type_id AS INTEGER)         AS transport_type_id,
    upper(trim(road_type))                     AS road_type,
    upper(trim(town))                          AS district,
    CAST(passages AS BIGINT)                   AS passages,
    CAST(passengers AS BIGINT)                 AS passengers
FROM read_parquet('data/agg/hourly_mode/*.parquet');

CREATE OR REPLACE VIEW stg_station_daily AS
SELECT
    CAST(date AS DATE)                         AS date,
    CAST(transport_type_id AS INTEGER)         AS transport_type_id,
    upper(trim(road_type))                     AS road_type,
    upper(trim(line_name))                     AS line_code,
    upper(trim(station))                       AS station,
    upper(trim(town))                          AS district,
    CAST(passages AS BIGINT)                   AS passages,
    CAST(passengers AS BIGINT)                 AS passengers
FROM read_parquet('data/agg/station_daily/*.parquet');

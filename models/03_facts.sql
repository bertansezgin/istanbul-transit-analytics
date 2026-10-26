-- Facts.

-- Grain: day x line x district x fare product x transaction type x transfer type.
CREATE OR REPLACE TABLE fct_daily_ridership AS
SELECT
    s.date,
    s.road_type,
    md5(concat_ws('|', s.road_type, s.line_code, s.line)) AS line_key,
    s.line_code,
    s.district,
    s.product_kind,
    s.transaction_type,
    s.transfer_type = 'Aktarma'                            AS is_transfer,
    s.passages,
    s.passengers
FROM stg_daily_line s;

-- Grain: day x hour x mode x district.
CREATE OR REPLACE TABLE fct_hourly_ridership AS
SELECT date, hour, road_type, district, passages, passengers
FROM stg_hourly_mode;

-- Grain: day x station x line.
CREATE OR REPLACE TABLE fct_station_daily AS
SELECT date, road_type, line_code, station, district, passages, passengers
FROM stg_station_daily;

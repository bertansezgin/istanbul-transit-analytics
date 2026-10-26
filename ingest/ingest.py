"""Download IBB hourly public transport files one month at a time, aggregate them with DuckDB
into three Parquet tables and delete the raw CSV. A month that already has all three outputs is
skipped, so the script can be stopped and restarted.

Source: Istanbul Metropolitan Municipality Open Data, "Hourly Public Transport Data Set"
https://data.ibb.gov.tr/dataset/hourly-public-transport-data-set
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
OUT_DIR = ROOT / "data" / "agg"
PACKAGE_URL = "https://data.ibb.gov.tr/api/3/action/package_show?id=hourly-public-transport-data-set"

# One row per day, line and fare attributes. Hour and station are dropped here.
DAILY_LINE_SQL = """
SELECT transition_date AS date, transport_type_id, road_type, line, line_name, transfer_type,
       product_kind, transaction_type_desc, town,
       SUM(number_of_passage) AS passages, SUM(number_of_passenger) AS passengers
FROM raw GROUP BY ALL
"""

# One row per day, hour, mode and district: the input for peak-hour analysis.
HOURLY_MODE_SQL = """
SELECT transition_date AS date, transition_hour AS hour, transport_type_id, road_type, town,
       SUM(number_of_passage) AS passages, SUM(number_of_passenger) AS passengers
FROM raw GROUP BY ALL
"""

# Station-level daily totals, only where the source reports a station (mostly rail and sea).
STATION_DAILY_SQL = """
SELECT transition_date AS date, transport_type_id, road_type, line_name,
       station_poi_desc_cd AS station, town,
       SUM(number_of_passage) AS passages, SUM(number_of_passenger) AS passengers
FROM raw WHERE station_poi_desc_cd IS NOT NULL AND trim(station_poi_desc_cd) <> ''
GROUP BY ALL
"""

TABLES = {"daily_line": DAILY_LINE_SQL, "hourly_mode": HOURLY_MODE_SQL, "station_daily": STATION_DAILY_SQL}


def month_urls() -> dict[str, str]:
    with urllib.request.urlopen(PACKAGE_URL, timeout=60) as resp:
        resources = json.load(resp)["result"]["resources"]
    urls = {}
    for r in resources:
        url = r["url"]
        stem = url.rsplit("hourly_transportation_", 1)[-1].removesuffix(".csv")
        if stem.isdigit() and len(stem) == 6:
            urls[stem] = url
    return dict(sorted(urls.items()))


def done(month: str) -> bool:
    return all((OUT_DIR / name / f"{month}.parquet").exists() for name in TABLES)


def download(url: str, dest: Path, attempts: int = 5) -> None:
    """The portal cuts connections after about 100 seconds and ignores Range requests, so a
    plain download of a 1.5 GB file never finishes. Asking for gzip makes the transfer about
    6x smaller, which fits in the window. The gzip stream is verified before use."""
    for attempt in range(1, attempts + 1):
        subprocess.run(
            ["curl", "-sSL", "-H", "Accept-Encoding: gzip", "-o", str(dest), url],
            capture_output=True, text=True,
        )
        if dest.exists() and subprocess.run(["gzip", "-t", str(dest)], capture_output=True).returncode == 0:
            return
        print(f"  attempt {attempt} incomplete, retrying", flush=True)
        dest.unlink(missing_ok=True)
        time.sleep(10 * attempt)
    raise RuntimeError(f"could not download {url}")


def aggregate(csv_path: Path, month: str) -> dict[str, int]:
    con = duckdb.connect()
    path = str(csv_path).replace("'", "''")
    # Load once into memory; the three aggregations then read the table, not the gzip file.
    con.execute(
        f"""
        CREATE TEMP TABLE raw AS SELECT * FROM read_csv('{path}', header=true,
            types={{'transition_date':'DATE','transition_hour':'INTEGER','transport_type_id':'INTEGER',
                    'number_of_passage':'BIGINT','number_of_passenger':'BIGINT',
                    'line':'VARCHAR','line_name':'VARCHAR','station_poi_desc_cd':'VARCHAR','town':'VARCHAR'}},
            ignore_errors=true)
        """
    )
    counts = {"raw_rows": con.execute("SELECT count(*) FROM raw").fetchone()[0]}
    for name, sql in TABLES.items():
        out = OUT_DIR / name / f"{month}.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".tmp")
        con.execute(f"COPY ({sql}) TO '{tmp}' (FORMAT parquet, COMPRESSION zstd)")
        tmp.rename(out)
        counts[name] = con.execute(f"SELECT count(*) FROM '{out}'").fetchone()[0]
    con.close()
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="202001", help="first month, YYYYMM")
    parser.add_argument("--end", default="202407", help="last month, YYYYMM")
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    log_path = OUT_DIR / "ingest_log.jsonl"
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for month, url in month_urls().items():
        if not (args.start <= month <= args.end) or done(month):
            continue
        csv_path = RAW_DIR / f"{month}.csv.gz"
        t0 = time.time()
        print(f"{month}: downloading", flush=True)
        download(url, csv_path)
        size = csv_path.stat().st_size
        print(f"{month}: aggregating {size / 1e6:.0f} MB gzip", flush=True)
        counts = aggregate(csv_path, month)
        csv_path.unlink()
        entry = {"month": month, "bytes": size, "seconds": round(time.time() - t0), **counts}
        with log_path.open("a") as f:
            f.write(json.dumps(entry) + "\n")
        print(f"{month}: done {entry}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

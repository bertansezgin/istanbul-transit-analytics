"""Build the DuckDB warehouse from the aggregated Parquet files: run models/*.sql in order."""

from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "warehouse.duckdb"


def build(db_path: Path = DB_PATH) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(db_path))
    con.execute(f"SET file_search_path = '{ROOT}'")
    for sql_file in sorted((ROOT / "models").glob("*.sql")):
        con.execute(sql_file.read_text())
        print(f"ran {sql_file.name}")
    return con


if __name__ == "__main__":
    build().close()

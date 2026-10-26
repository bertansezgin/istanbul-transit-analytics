"""Data quality checks on the warehouse. Run after `python build.py`:  pytest -q

Hard checks fail the build. Soft checks (known gaps in the source) are reported in
docs/data_quality.md by analysis/report.py instead of failing here.
"""

from pathlib import Path

import duckdb
import pytest

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "warehouse.duckdb"


@pytest.fixture(scope="module")
def con():
    if not DB_PATH.exists():
        pytest.skip("warehouse not built; run python build.py")
    c = duckdb.connect(str(DB_PATH), read_only=True)
    yield c
    c.close()


def scalar(con, sql):
    return con.execute(sql).fetchone()[0]


def test_no_negative_counts(con):
    assert scalar(con, "SELECT count(*) FROM fct_daily_ridership WHERE passages < 0 OR passengers < 0") == 0


def test_passengers_never_exceed_passages(con):
    # A card counted as one passenger can tap several times, never the other way round.
    assert scalar(con, "SELECT count(*) FROM fct_daily_ridership WHERE passengers > passages") == 0


def test_every_mode_is_known(con):
    assert scalar(con, "SELECT count(*) FROM dim_mode WHERE mode = 'Other'") == 0


def test_fare_segments_are_known(con):
    allowed = "('Full fare','Discounted','Free','Staff and service')"
    assert scalar(con, f"SELECT count(*) FROM dim_fare WHERE fare_segment NOT IN {allowed}") == 0


def test_fact_rows_join_to_dimensions(con):
    assert scalar(con, "SELECT count(*) FROM fct_daily_ridership f ANTI JOIN dim_date USING (date)") == 0
    assert scalar(con, "SELECT count(*) FROM fct_daily_ridership f ANTI JOIN dim_line USING (line_key)") == 0


def test_daily_and_hourly_totals_agree(con):
    # Both tables come from the same raw rows, so day totals must match exactly.
    diff = scalar(
        con,
        """
        SELECT count(*) FROM (
            SELECT date, sum(passages) AS p FROM fct_daily_ridership GROUP BY 1
        ) d FULL JOIN (
            SELECT date, sum(passages) AS p FROM fct_hourly_ridership GROUP BY 1
        ) h USING (date)
        WHERE d.p IS DISTINCT FROM h.p
        """,
    )
    assert diff == 0


def test_hours_in_range(con):
    assert scalar(con, "SELECT count(*) FROM fct_hourly_ridership WHERE hour NOT BETWEEN 0 AND 23") == 0


def test_monthly_kpi_keys_unique(con):
    assert scalar(con, "SELECT count(*) - count(DISTINCT year_month) FROM mart_monthly_kpis") == 0


def test_shares_are_valid(con):
    bad = scalar(
        con,
        """
        SELECT count(*) FROM mart_monthly_kpis
        WHERE NOT (transfer_share BETWEEN 0 AND 1 AND discounted_share BETWEEN 0 AND 1
                   AND abs(bus_share + rail_share + sea_share - 1) < 1e-9)
        """,
    )
    assert bad == 0


def test_flagged_months_are_not_complete(con):
    # Months with a known source issue must never count as complete in KPIs.
    assert scalar(con, "SELECT count(*) FROM mart_monthly_kpis WHERE source_issue IS NOT NULL AND is_complete_month") == 0

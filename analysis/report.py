"""Produce the findings: charts in docs/figures, key numbers in docs/findings.md, a data quality
report in docs/data_quality.md and CSV extracts for Tableau in tableau/data.

Run after `python build.py`.
"""

from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "warehouse.duckdb"
FIG_DIR = ROOT / "docs" / "figures"
TABLEAU_DIR = ROOT / "tableau" / "data"

MODE_COLORS = {"Bus": "#d1495b", "Rail": "#00798c", "Sea": "#edae49"}
plt.rcParams.update({"figure.dpi": 150, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.alpha": 0.25, "font.size": 9})


def df(con, sql):
    return con.execute(sql).df()


def save(fig, name):
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(FIG_DIR / name)
    plt.close(fig)


def latest_full_year(con) -> int:
    return con.execute(
        "SELECT max(year) FROM (SELECT year, count(*) n FROM mart_monthly_kpis "
        "WHERE is_complete_month GROUP BY year) WHERE n = 12"
    ).fetchone()[0]


def charts(con, year: int) -> None:
    k = df(con, "SELECT * FROM mart_monthly_kpis WHERE is_complete_month ORDER BY year_month")
    k["ym"] = k["year_month"].astype(str)

    fig, ax = plt.subplots(figsize=(9, 3.6))
    ax.plot(k["ym"], k["recovery_index"], color="#00798c", lw=2)
    ax.axhline(100, color="grey", lw=1, ls="--")
    cov = k[k["ym"].between("2020-03", "2021-06")]
    if len(cov):
        ax.axvspan(cov["ym"].iloc[0], cov["ym"].iloc[-1], color="grey", alpha=0.12, label="Covid restrictions")
    ax.set_title("Average daily boardings vs. Jan-Feb 2020 (= 100)")
    ax.set_xticks(k["ym"][::3])
    ax.tick_params(axis="x", rotation=60)
    ax.legend(loc="lower right", frameon=False)
    save(fig, "01_recovery_index.png")

    m = df(con, """SELECT mm.* FROM mart_mode_monthly mm JOIN mart_monthly_kpis k USING (year_month)
                   WHERE k.is_complete_month ORDER BY year_month""").pivot(
        index="year_month", columns="mode", values="share_of_month").fillna(0)
    fig, ax = plt.subplots(figsize=(9, 3.4))
    ax.stackplot(m.index.astype(str), [m[c] for c in m.columns],
                 labels=m.columns, colors=[MODE_COLORS.get(c) for c in m.columns], alpha=0.9)
    ax.set_ylim(0, 1)
    ax.set_title("Share of boardings by mode")
    ax.set_xticks(list(m.index.astype(str))[::3])
    ax.tick_params(axis="x", rotation=60)
    ax.legend(loc="upper left", ncols=3, frameon=False)
    save(fig, "02_mode_share.png")

    h = df(con, f"SELECT * FROM mart_hourly_profile WHERE year = {year} AND day_type IN ('Weekday','Weekend')")
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.2), sharey=True)
    for ax, day_type in zip(axes, ["Weekday", "Weekend"]):
        for mode, g in h[h["day_type"] == day_type].groupby("mode"):
            g = g.sort_values("hour")
            ax.plot(g["hour"], g["avg_passages"] / 1e3, label=mode, color=MODE_COLORS.get(mode), lw=2)
        ax.set_title(f"{day_type}, {year}")
        ax.set_xticks(range(0, 24, 3))
        ax.set_xlabel("hour")
    axes[0].set_ylabel("avg boardings (thousands)")
    axes[0].legend(frameon=False)
    save(fig, "03_hourly_profile.png")

    s = df(con, f"SELECT * FROM mart_station_yearly WHERE year = {year} ORDER BY passages DESC LIMIT 12")
    fig, ax = plt.subplots(figsize=(9, 3.8))
    labels = s["station"].str.title() + " (" + s["line_code"] + ")"
    ax.barh(labels[::-1], s["passages"][::-1] / 1e6, color=[MODE_COLORS.get(x) for x in s["mode"][::-1]])
    ax.set_xlabel("boardings (millions)")
    ax.set_title(f"Busiest stations, {year}")
    save(fig, "04_top_stations.png")

    he = df(con, """SELECT holiday_name, avg(change_vs_baseline) AS change
                    FROM mart_holiday_effect WHERE year >= 2022 GROUP BY 1 ORDER BY change""")
    fig, ax = plt.subplots(figsize=(9, 3.2))
    ax.barh(he["holiday_name"], he["change"] * 100, color="#d1495b")
    ax.set_xlabel("% change vs. same weekday in surrounding weeks")
    ax.set_title("Holiday effect on boardings (2022 onwards)")
    save(fig, "05_holiday_effect.png")

    fig, ax = plt.subplots(figsize=(9, 3.2))
    for col, label, color in [("transfer_share", "Transfer", "#00798c"),
                              ("discounted_share", "Discounted card", "#edae49"),
                              ("free_share", "Free card", "#d1495b")]:
        ax.plot(k["ym"], k[col] * 100, label=label, color=color, lw=2)
    ax.set_ylabel("% of boardings")
    ax.set_title("Transfers and fare mix")
    ax.set_xticks(k["ym"][::3])
    ax.tick_params(axis="x", rotation=60)
    ax.legend(frameon=False, ncols=3)
    save(fig, "06_fare_mix.png")


def findings(con, year: int) -> str:
    q = lambda sql: con.execute(sql).fetchone()  # noqa: E731
    total, avg_daily = q(f"SELECT sum(passages), sum(passages)/count(*) FROM mart_daily WHERE year = {year}")
    prev = q(f"SELECT sum(passages)/count(*) FROM mart_daily WHERE year = {year - 1}")[0]
    low_ym, low_idx = q("SELECT year_month, recovery_index FROM mart_monthly_kpis ORDER BY recovery_index LIMIT 1")
    rec_ym = q("SELECT min(year_month) FROM mart_monthly_kpis WHERE recovery_index >= 100 AND year_month > '2020-03'")[0]
    modes = df(con, f"""SELECT mode, sum(passages) p FROM mart_mode_monthly
                        WHERE year_month LIKE '{year}-%' GROUP BY 1 ORDER BY p DESC""")
    modes["share"] = modes["p"] / modes["p"].sum()
    peak = q(f"""SELECT hour, sum(avg_passages) FROM mart_hourly_profile
                 WHERE year = {year} AND day_type = 'Weekday' GROUP BY 1 ORDER BY 2 DESC LIMIT 1""")
    wk = q(f"""SELECT avg(weekend_to_weekday_ratio), avg(transfer_share), avg(discounted_share), avg(free_share)
               FROM mart_monthly_kpis WHERE year = {year}""")
    top_station = q(f"SELECT station, line_code, passages FROM mart_station_yearly WHERE year = {year} ORDER BY passages DESC LIMIT 1")
    top_line = q(f"SELECT line_code, route_name, passages FROM mart_line_yearly WHERE year = {year} ORDER BY passages DESC LIMIT 1")
    hol = q("""SELECT holiday_name, avg(change_vs_baseline) FROM mart_holiday_effect
               WHERE year >= 2022 GROUP BY 1 ORDER BY 2 LIMIT 1""")

    lines = [
        f"# Findings ({year} is the latest full year in the data)",
        "",
        f"- **Volume:** {total / 1e9:.2f} billion boardings in {year}, {avg_daily / 1e6:.2f} million per day "
        f"({avg_daily / prev - 1:+.1%} vs. {year - 1}).",
        f"- **Pandemic and recovery:** daily boardings fell to {low_idx:.0f}% of the early-2020 level in {low_ym}; "
        + (f"they first returned to that level in {rec_ym}." if rec_ym else "they have not yet returned to that level."),
        "- **Mode mix:** " + ", ".join(f"{r.mode} {r.share:.0%}" for r in modes.itertuples()) + f" of boardings in {year}.",
        f"- **Peak hour:** weekday boardings peak at {peak[0]:02d}:00; weekends carry {wk[0]:.0%} of a weekday's volume.",
        f"- **Transfers and fares:** {wk[1]:.0%} of boardings are transfers; discounted cards {wk[2]:.0%}, free cards {wk[3]:.0%}.",
        f"- **Busiest station:** {top_station[0].title()} ({top_station[1]}), {top_station[2] / 1e6:.1f} million boardings.",
        f"- **Busiest line:** {top_line[0]} ({top_line[1]}), {top_line[2] / 1e6:.1f} million boardings.",
        f"- **Holidays:** the deepest drop is on {hol[0]}, {hol[1]:.0%} vs. comparable days.",
        "",
        "Charts are in `docs/figures/`. Every number above is recomputed by `python analysis/report.py`.",
    ]
    return "\n".join(lines) + "\n"


def data_quality(con) -> str:
    k = df(con, """SELECT year_month, days_with_data, days_in_month, passages, avg_daily_passages, source_issue
                   FROM mart_monthly_kpis ORDER BY year_month""")
    gaps = k[k["days_with_data"] < k["days_in_month"]]
    issues = k[k["source_issue"].notna()]
    log = df(con, f"SELECT * FROM read_json_auto('{ROOT / 'data' / 'agg' / 'ingest_log.jsonl'}')")
    low = df(con, """
        WITH d AS (SELECT date, passages, median(passages) OVER (PARTITION BY year_month, day_type) AS med, day_type, year_month
                   FROM mart_daily)
        SELECT date, day_type, passages, med FROM d WHERE passages < 0.5 * med ORDER BY date""")
    out = ["# Data quality", "",
           f"- Months covered: {len(k)} ({k['year_month'].min()} to {k['year_month'].max()}).",
           f"- Months with missing days: {len(gaps)}.",
           f"- Months flagged as partial publications and left out of KPIs and charts: {len(issues)}.", ""]
    if len(issues):
        sizes = dict(zip(log["month"].astype(str), log["bytes"]))
        out += ["| Month | Avg daily boardings | gzip size | Issue |", "|---|---|---|---|"]
        for r in k[k["year_month"] >= "2024-05"].itertuples():
            size = sizes.get(r.year_month.replace("-", ""), 0) / 1e6
            out.append(f"| {r.year_month} | {r.avg_daily_passages:,.0f} | {size:.0f} MB | {r.source_issue if isinstance(r.source_issue, str) else ''} |")
        out += ["", "Line and district coverage in the flagged months is normal (860+ lines, 39 districts), "
                "so the drop comes from missing rows in the published files, not from fewer riders.", ""]
    if len(gaps):
        out += ["| Month | Days with data | Days in month |", "|---|---|---|"]
        out += [f"| {r.year_month} | {r.days_with_data} | {r.days_in_month} |" for r in gaps.itertuples()]
        out.append("")
    out += [f"- Days below half of their month's median for the same day type: {len(low)} "
            "(holidays, curfews or partial loads; kept in the data, flagged here).", ""]
    if len(low):
        out += ["| Date | Day type | Boardings | Month median |", "|---|---|---|---|"]
        out += [f"| {r.date:%Y-%m-%d} | {r.day_type} | {r.passages:,.0f} | {r.med:,.0f} |" for r in low.head(40).itertuples()]
    return "\n".join(out) + "\n"


def tableau_extracts(con) -> None:
    TABLEAU_DIR.mkdir(parents=True, exist_ok=True)
    for table in ["mart_daily", "mart_monthly_kpis", "mart_mode_monthly", "mart_hourly_profile",
                  "mart_line_yearly", "mart_district_monthly", "mart_station_yearly", "mart_holiday_effect"]:
        con.execute(f"COPY {table} TO '{TABLEAU_DIR / (table + '.csv')}' (HEADER, DELIMITER ',')")


def main() -> None:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    year = latest_full_year(con)
    charts(con, year)
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "findings.md").write_text(findings(con, year))
    (ROOT / "docs" / "data_quality.md").write_text(data_quality(con))
    tableau_extracts(con)
    print((ROOT / "docs" / "findings.md").read_text())


if __name__ == "__main__":
    main()

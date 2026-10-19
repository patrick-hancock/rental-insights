"""C3.T5 feasibility probe: answer eval queries E01, E02 and E06 on DuckDB from the Parquet snapshot.

Loads snapshot/<table>.parquet as DuckDB views named like the BigQuery gold tables, transpiles
each eval reference query (packs/eval/questions.md, trace rows T01, T02, T06) with sqlglot
(read="bigquery", write="duckdb"), runs it and appends a dated block to scripts/probe_duckdb.log
with the original SQL, the transpiled SQL, the result and PASS/FAIL. No timings are recorded.

The SQL below is copied verbatim from questions.md. T01 returns only the median; its 749-metro
count comes from site/data/trends.json in the eval set, so E01 adds one count query over the
same filter (COUNT(zori) for the same month) to check the "across 749 metros" part on DuckDB.

Exit 0 when every query matches, 1 on any FAIL, 2 when the snapshot is missing.
Usage: python scripts/probe_duckdb.py
"""
import datetime
import json
import pathlib
import sys

import duckdb
import sqlglot

ROOT = pathlib.Path(__file__).resolve().parents[1]
SNAP = ROOT / "snapshot"
LOG = pathlib.Path(__file__).with_name("probe_duckdb.log")

# (id, description, [(label, BigQuery SQL)], check(results) -> (passed, expected text, got text))
QUERIES = [
    (
        "E01",
        "median typical rent across US metros, August 2026",
        [
            ("T01 (verbatim)", "SELECT ANY_VALUE(m) AS median_zori FROM (SELECT PERCENTILE_CONT(zori, 0.5) OVER () AS m "
             "FROM fct_metro_month WHERE month_end = DATE '2026-08-31' AND zori IS NOT NULL)"),
            ("metro count (same filter)", "SELECT COUNT(zori) AS metros FROM fct_metro_month WHERE month_end = DATE '2026-08-31'"),
        ],
        lambda r: (
            round(r[0][0][0]) == 1388 and r[1][0][0] == 749,
            "$1,388 across 749 metros",
            f"${round(r[0][0][0]):,} ({r[0][0][0]}) across {r[1][0][0]} metros",
        ),
    ),
    (
        "E02",
        "metros with rents falling year over year, August 2026",
        [("T02 (verbatim)", "SELECT COUNTIF(zori_yoy < 0) AS falling, COUNT(zori_yoy) AS with_yoy "
          "FROM fct_metro_month WHERE month_end = DATE '2026-08-31'")],
        lambda r: (tuple(r[0][0]) == (27, 602), "27 of 602", f"{r[0][0][0]} of {r[0][0][1]}"),
    ),
    (
        "E06",
        "metro areas with typical rent above the 2-bedroom FMR",
        [("T06 (verbatim)", "SELECT COUNTIF(zori_to_fmr_2br > 1) AS above, COUNT(zori_to_fmr_2br) AS total "
          "FROM fct_cbsa_affordability")],
        lambda r: (tuple(r[0][0]) == (299, 381), "299 of 381", f"{r[0][0][0]} of {r[0][0][1]}"),
    ),
]


def main():
    manifest = SNAP / "manifest.json"
    if not manifest.exists():
        print("ERROR: snapshot/manifest.json missing; run scripts/export_parquet.py first", file=sys.stderr)
        return 2
    tables = json.loads(manifest.read_text(encoding="utf-8"))["tables"]
    con = duckdb.connect()
    for name in tables:
        path = (SNAP / f"{name}.parquet").as_posix()
        con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{path}')")

    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"=== {stamp} | probe_duckdb | duckdb {duckdb.__version__} | sqlglot {sqlglot.__version__} | "
             f"snapshot exported_at {min(t['exported_at'] for t in tables.values())} ==="]
    all_pass = True
    for qid, desc, parts, check in QUERIES:
        lines.append(f"--- {qid}: {desc}")
        results = []
        error = None
        for label, bq_sql in parts:
            duck_sql = sqlglot.transpile(bq_sql, read="bigquery", write="duckdb")[0]
            lines += [f"  [{label}]", f"  bigquery: {bq_sql}", f"  duckdb:   {duck_sql}"]
            try:
                rows = con.execute(duck_sql).fetchall()
            except Exception as e:
                error = f"{type(e).__name__}: {e}"
                lines.append(f"  error:    {error}")
                break
            results.append(rows)
            lines.append(f"  result:   {rows}")
        if error:
            passed, expected, got = False, "(see check)", error
        else:
            passed, expected, got = check(results)
        all_pass &= passed
        lines.append(f"  {'PASS' if passed else 'FAIL'} | expected {expected} | got {got}")
    lines.append(f"=== overall: {'PASS' if all_pass else 'FAIL'} ===\n")

    text = "\n".join(lines) + "\n"
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(text)
    print(text)
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())

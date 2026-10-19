"""C1.T5: write reports/data_quality.md with row counts, duplicate keys and nulls for every gold table.

Usage:
  python scripts/dq_report.py           query BigQuery and (re)write the report
  python scripts/dq_report.py --check   exit 0 only if the report has a section for every gold table,
                                        its row counts equal the live counts, and no table has duplicate keys
"""
import datetime
import pathlib
import re
import sys

from google.cloud import bigquery

ROOT = pathlib.Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "data_quality.md"
PROJECT = "rental-insights-511513"
GOLD = f"{PROJECT}.gold"

# The column (or columns) that should identify one row: the grain stated in models/gold/schema.yml.
KEYS = {
    "dim_date": ["month_end"],
    "dim_metro": ["zillow_region_id"],
    "fct_metro_month": ["metro_month_key"],
    "fct_cbsa_affordability": ["cbsa_code"],
}

# Why some nulls are expected, so a reader can tell a gap in the source from a pipeline bug.
NULL_NOTES = {
    ("dim_metro", "cbsa_code"): "Zillow metro with no CBSA name match (43 of 910 on 2026-10-13, all size rank 275 or lower).",
    ("dim_metro", "match_method"): "Same rows as cbsa_code: no match.",
    ("dim_metro", "cbsa_name"): "Same rows as cbsa_code: no match.",
    ("dim_metro", "cbsa_type"): "Same rows as cbsa_code: no match.",
    ("dim_metro", "population"): "Same rows as cbsa_code: no match.",
    ("dim_metro", "state_code"): "Zillow leaves the state blank for some metros.",
    ("fct_metro_month", "zori"): "ZORI starts 2015-01 and covers fewer metros than ZHVI.",
    ("fct_metro_month", "zhvi"): "Metro-months with a rent value but no home value.",
    ("fct_metro_month", "zori_yoy"): "No ZORI value this month or 12 months earlier.",
    ("fct_metro_month", "zhvi_yoy"): "No ZHVI value this month or 12 months earlier.",
    ("fct_metro_month", "gross_rent_yield"): "Needs both ZORI and ZHVI in the same month.",
    ("fct_cbsa_affordability", "hud_fmr_2br_weighted"): "HUD gives a CBSA code only for metro areas; micro areas are null.",
    ("fct_cbsa_affordability", "hud_county_count"): "Same rows as hud_fmr_2br_weighted.",
    ("fct_cbsa_affordability", "zori_to_fmr_2br"): "Needs both a matched Zillow rent and a HUD FMR.",
    ("fct_cbsa_affordability", "latest_zori"): "CBSA with no matched Zillow metro that has rent data.",
    ("fct_cbsa_affordability", "zori_month"): "Same rows as latest_zori.",
}


def profile(client, table):
    cols = [f.name for f in client.get_table(f"{GOLD}.{table}").schema]
    key = KEYS[table]
    null_exprs = ", ".join(f"COUNTIF(`{c}` IS NULL) AS `{c}`" for c in cols)
    nulls = dict(next(iter(client.query(f"SELECT COUNT(*) AS __rows, {null_exprs} FROM `{GOLD}.{table}`").result())).items())
    rows = nulls.pop("__rows")
    key_list = ", ".join(f"`{k}`" for k in key)
    dup = next(iter(client.query(
        f"SELECT COUNT(*) AS n FROM (SELECT {key_list} FROM `{GOLD}.{table}` GROUP BY {key_list} HAVING COUNT(*) > 1)"
    ).result())).n
    return {"rows": rows, "key": key, "dup_keys": dup, "nulls": nulls}


def outliers(client):
    sql = f"""SELECT m.metro_name, f.month_end, ROUND(f.zori_yoy, 3) AS zori_yoy, m.size_rank
              FROM `{GOLD}.fct_metro_month` f JOIN `{GOLD}.dim_metro` m USING (zillow_region_id)
              WHERE ABS(f.zori_yoy) > 0.4 ORDER BY ABS(f.zori_yoy) DESC LIMIT 10"""
    return [dict(r.items()) for r in client.query(sql).result()]


def gold_tables(client):
    return sorted(t.table_id for t in client.list_tables(GOLD))


def write(client):
    tables = gold_tables(client)
    missing = [t for t in tables if t not in KEYS]
    if missing:
        print(f"ERROR: no key defined for {missing}; add it to KEYS")
        return 1
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    out = [
        "# Data quality report: gold tables",
        "",
        f"Generated {now} by `scripts/dq_report.py` from BigQuery dataset `{GOLD}`. "
        "Rerun the script after every `dbt build`; `--check` fails when this file is stale.",
        "",
    ]
    for t in tables:
        p = profile(client, t)
        out += [
            f"## {t}",
            "",
            f"- Rows: {p['rows']:,}",
            f"- Key: `{', '.join(p['key'])}`",
            f"- Duplicate keys: {p['dup_keys']}",
            "",
            "| Column | Nulls | Null % | Why |",
            "|---|---:|---:|---|",
        ]
        for col, n in p["nulls"].items():
            pct = 100 * n / p["rows"] if p["rows"] else 0
            note = NULL_NOTES.get((t, col), "" if n == 0 else "UNEXPLAINED: check before use")
            out.append(f"| {col} | {n:,} | {pct:.1f} | {note} |")
        out.append("")
    out += ["## Outliers to review", "", "Metro-months where rent moved more than 40% in a year (largest 10):", "",
            "| Metro | Month | ZORI YoY | Size rank |", "|---|---|---:|---:|"]
    for o in outliers(client):
        out.append(f"| {o['metro_name']} | {o['month_end']} | {o['zori_yoy']} | {o['size_rank']} |")
    out.append("")
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text("\n".join(out), encoding="utf-8")
    print(f"wrote {REPORT.relative_to(ROOT)}: {len(tables)} tables")
    return 0


def check(client):
    if not REPORT.exists():
        print("FAIL: report missing")
        return 1
    text = REPORT.read_text(encoding="utf-8")
    bad = 0
    for t in gold_tables(client):
        m = re.search(rf"^## {t}\n\n- Rows: ([\d,]+)\n- Key: .*\n- Duplicate keys: (\d+)\n", text, re.M)
        if not m:
            print(f"FAIL {t}: no section with rows, key and duplicate figures")
            bad += 1
            continue
        live = profile(client, t)
        shown = int(m.group(1).replace(",", ""))
        has_nulls = f"| Column | Nulls |" in text.split(f"## {t}")[1].split("\n## ")[0]
        problems = []
        if shown != live["rows"]:
            problems.append(f"stale rows {shown} vs live {live['rows']}")
        if live["dup_keys"]:
            problems.append(f"{live['dup_keys']} duplicate keys")
        if not has_nulls:
            problems.append("no null table")
        unexplained = [c for c, n in live["nulls"].items() if n and (t, c) not in NULL_NOTES]
        if unexplained:
            problems.append(f"unexplained nulls in {unexplained}")
        bad += bool(problems)
        print(f"{'FAIL' if problems else 'PASS'} {t}: rows={live['rows']} dup_keys={live['dup_keys']}"
              + (f" ({'; '.join(problems)})" if problems else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    c = bigquery.Client(project=PROJECT)
    sys.exit(check(c) if "--check" in sys.argv else write(c))

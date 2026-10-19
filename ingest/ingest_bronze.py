"""C1.T3: land each source as one bronze table in BigQuery and record its row count in ingest/manifest.json.

Usage: python ingest/ingest_bronze.py [source ...]   (default: every source)
Bronze keeps the raw values: every column is loaded as STRING so codes keep leading zeros.
Column names are sanitized for BigQuery (non-alphanumerics become _, a leading digit gets a c_ prefix).
Each load is WRITE_TRUNCATE, so a rerun replaces the table rather than appending.
The Census key is read from CENSUS_API_KEY and is never printed or logged.
"""
import csv
import datetime
import hashlib
import io
import json
import os
import pathlib
import re
import sys
import urllib.parse
import urllib.request

from google.cloud import bigquery

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
MANIFEST = ROOT / "ingest" / "manifest.json"
PROJECT = "rental-insights-511513"
DATASET = "bronze"

# ACS 2024 5-year is the newest vintage (2025 returned 404 on 2026-10-13).
ACS_YEAR = 2024
ACS_VARS = {
    "B01003_001E": "total population",
    "B19013_001E": "median household income",
    "B25064_001E": "median gross rent",
    "B25077_001E": "median home value (owner-occupied)",
    "B25003_001E": "occupied housing units",
    "B25003_002E": "owner-occupied units",
    "B25003_003E": "renter-occupied units",
    "B25070_001E": "renter households, gross rent as % of income: total",
    "B25070_007E": "30.0 to 34.9 percent",
    "B25070_008E": "35.0 to 39.9 percent",
    "B25070_009E": "40.0 to 49.9 percent",
    "B25070_010E": "50.0 percent or more",
    "B25070_011E": "not computed",
}

SOURCES = {
    "zillow_zori_metro": {
        "kind": "csv_url",
        "url": "https://files.zillowstatic.com/research/public_csvs/zori/Metro_zori_uc_sfrcondomfr_sm_month.csv",
        "file": "zillow_zori_metro.csv",
    },
    "zillow_zhvi_metro": {
        "kind": "csv_url",
        "url": "https://files.zillowstatic.com/research/public_csvs/zhvi/Metro_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv",
        "file": "zillow_zhvi_metro.csv",
    },
    "census_acs5_cbsa": {
        "kind": "census",
        "url": f"https://api.census.gov/data/{ACS_YEAR}/acs/acs5",
        "geo": "metropolitan statistical area/micropolitan statistical area:*",
        "file": f"census_acs5_{ACS_YEAR}_cbsa.csv",
    },
    "hud_fmr_fy27": {
        # huduser.gov answers scripted requests with an empty 202 (bot check), so Patrick downloads this by hand.
        "kind": "xlsx_manual",
        "url": "https://www.huduser.gov/portal/datasets/fmr/fmr2027/FY27_FMRs.xlsx",
        "file": "FY27_FMRs.xlsx",
    },
}


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "rental-insights-ingest"})
    with urllib.request.urlopen(req, timeout=120) as r:
        if r.status != 200:
            raise RuntimeError(f"HTTP {r.status}")
        return r.read()


def clean_name(name, seen):
    n = re.sub(r"[^A-Za-z0-9_]", "_", name.strip()) or "col"
    if n[0].isdigit():
        n = "c_" + n
    base, i = n, 2
    while n.lower() in seen:
        n, i = f"{base}_{i}", i + 1
    seen.add(n.lower())
    return n


def rows_from_source(name, spec):
    """Return (header, rows, raw_bytes) as read from the source, before any change."""
    path = RAW / spec["file"]
    if spec["kind"] == "csv_url":
        raw = fetch(spec["url"])
        path.write_bytes(raw)
        table = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline="")))
    elif spec["kind"] == "census":
        q = urllib.parse.urlencode({"get": "NAME," + ",".join(ACS_VARS), "for": spec["geo"],
                                    "key": os.environ["CENSUS_API_KEY"]})
        table = json.loads(fetch(spec["url"] + "?" + q))
        buf = io.StringIO()
        csv.writer(buf, lineterminator="\n").writerows(table)
        raw = buf.getvalue().encode("utf-8")
        path.write_bytes(raw)  # saved without the request URL, so the key never lands on disk
    elif spec["kind"] == "xlsx_manual":
        if not path.exists():
            raise FileNotFoundError(f"download {spec['url']} by hand to data/raw/{spec['file']}")
        import openpyxl
        raw = path.read_bytes()
        ws = openpyxl.load_workbook(path, read_only=True, data_only=True).worksheets[0]
        table = [["" if v is None else str(v) for v in row] for row in ws.iter_rows(values_only=True)]
        while table and not any(table[-1]):
            table.pop()  # trailing blank rows that Excel keeps
    return table[0], table[1:], raw


def load(client, name, header, rows):
    seen = set()
    cols = [clean_name(h, seen) for h in header]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cols)
    w.writerows(rows)
    table_id = f"{PROJECT}.{DATASET}.{name}"
    cfg = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.CSV, skip_leading_rows=1,
        schema=[bigquery.SchemaField(c, "STRING") for c in cols],
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    client.load_table_from_file(io.BytesIO(buf.getvalue().encode("utf-8")), table_id, job_config=cfg).result()
    return table_id, dict(zip(header, cols))


def main():
    names = sys.argv[1:] or list(SOURCES)
    RAW.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    client = bigquery.Client(project=PROJECT)
    client.create_dataset(bigquery.Dataset(f"{PROJECT}.{DATASET}"), exists_ok=True)
    failed = 0
    for name in names:
        spec = SOURCES[name]
        try:
            header, rows, raw = rows_from_source(name, spec)
            table_id, colmap = load(client, name, header, rows)
        except Exception as e:  # one source failing does not stop the others; no retry, loads are writes
            msg = str(e).replace(os.environ.get("CENSUS_API_KEY", "\0"), "***")
            print(f"FAIL {name}: {type(e).__name__}: {msg}")
            failed += 1
            continue
        manifest[name] = {
            "table": table_id,
            "source_url": spec["url"],
            "raw_file": f"data/raw/{spec['file']}",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "source_rows": len(rows),
            "columns": len(header),
            "renamed_columns": {k: v for k, v in colmap.items() if k != v},
            "retrieved_at": datetime.datetime.now().isoformat(timespec="seconds"),
        }
        if spec["kind"] == "census":
            manifest[name]["variables"] = ACS_VARS
        print(f"OK {name}: {len(rows)} rows -> {table_id}")
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

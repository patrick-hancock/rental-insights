"""Check that every bronze table's COUNT(*) equals the source row count in ingest/manifest.json.

Exit 0 only when all expected sources are in the manifest and every count matches.
"""
import json
import pathlib
import sys

from google.cloud import bigquery

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXPECTED = ["zillow_zori_metro", "zillow_zhvi_metro", "census_acs5_cbsa", "hud_fmr_fy27"]


def main():
    manifest = json.loads((ROOT / "ingest" / "manifest.json").read_text())
    client = bigquery.Client(project="rental-insights-511513")
    bad = 0
    for name in EXPECTED:
        entry = manifest.get(name)
        if not entry:
            print(f"MISSING {name}: not in manifest")
            bad += 1
            continue
        n = next(iter(client.query(f"SELECT COUNT(*) AS n FROM `{entry['table']}`").result())).n
        ok = n == entry["source_rows"]
        bad += not ok
        print(f"{'PASS' if ok else 'FAIL'} {name}: source_rows={entry['source_rows']} bq_count={n}")
    print(f"{len(EXPECTED) - bad} of {len(EXPECTED)} sources match")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

"""C3.T5 feasibility: export every gold table from BigQuery to snapshot/<table>.parquet.

Writes snapshot/manifest.json with, per table, the Parquet row count, the BigQuery COUNT(*)
and the export timestamp. Exit 0 when every pair matches, 1 when any differs, 2 on auth or
read error.

Read-only: lists tables, reads rows (tabledata.list, or a SELECT for a view) and runs COUNT(*).
Auth is the same path as mcp/tools/query_gold.py: the local Application Default Credentials
login impersonates the read-only ri-reader service account (no key file is read or printed).

Usage: python scripts/export_parquet.py
"""
import datetime
import json
import pathlib
import sys

import pyarrow.parquet as pq

PROJECT = "rental-insights-511513"  # same as mcp/guard.py
DATASET = "gold"
READER = f"ri-reader@{PROJECT}.iam.gserviceaccount.com"
SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]
ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "snapshot"


def client():
    import google.auth
    from google.auth import impersonated_credentials
    from google.cloud import bigquery

    source, _ = google.auth.default(scopes=SCOPES)
    creds = impersonated_credentials.Credentials(
        source_credentials=source, target_principal=READER, target_scopes=SCOPES
    )
    return bigquery.Client(project=PROJECT, credentials=creds)


def main():
    try:
        bq = client()
        tables = sorted(bq.list_tables(f"{PROJECT}.{DATASET}"), key=lambda t: t.table_id)
    except Exception as e:  # stop on auth or listing error; nothing written yet
        print(f"ERROR listing {PROJECT}.{DATASET}: {type(e).__name__}: {e}", file=sys.stderr)
        return 2

    OUT.mkdir(exist_ok=True)
    manifest = {"project": PROJECT, "dataset": DATASET, "tables": {}}
    ok = True
    for t in tables:
        name = t.table_id
        fq = f"{PROJECT}.{DATASET}.{name}"
        try:
            if t.table_type == "TABLE":
                arrow = bq.list_rows(fq).to_arrow()
            else:  # a view has no stored rows to list, so read it with a SELECT
                arrow = bq.query(f"SELECT * FROM `{fq}`").result().to_arrow()
            exported_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
            bq_count = next(iter(bq.query(f"SELECT COUNT(*) AS n FROM `{fq}`").result())).n
        except Exception as e:
            print(f"ERROR reading {fq}: {type(e).__name__}: {e}", file=sys.stderr)
            return 2
        path = OUT / f"{name}.parquet"
        pq.write_table(arrow, path)
        pq_count = pq.ParquetFile(path).metadata.num_rows  # re-read from disk, not the in-memory table
        match = pq_count == bq_count
        ok &= match
        manifest["tables"][name] = {
            "table_type": t.table_type,
            "parquet_rows": pq_count,
            "bigquery_count": bq_count,
            "match": match,
            "exported_at": exported_at,
            "file": f"snapshot/{name}.parquet",
        }
        print(f"{'OK  ' if match else 'DIFF'} {name}: parquet={pq_count} bigquery={bq_count}")

    manifest["all_match"] = ok
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"{len(tables)} tables; all_match={ok}; manifest at snapshot/manifest.json")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

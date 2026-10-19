"""C3.T2: show the MCP query identity (ri-reader) is read-only and limited to gold.

Impersonates ri-reader from your Application Default Credentials (no key file) and runs,
N times each: one gold read (expect allowed), one write into gold (expect denied) and one
silver read (expect denied). Exit 0 only if every attempt lands on its expected outcome.

    python scripts/probe_readonly.py [--runs 5]

A write that unexpectedly succeeds is dropped afterwards with your own credentials.
"""

import argparse
import sys
import uuid

import google.auth
from google.api_core.exceptions import Forbidden
from google.auth import impersonated_credentials
from google.cloud import bigquery

PROJECT = "rental-insights-511513"
READER = f"ri-reader@{PROJECT}.iam.gserviceaccount.com"
SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]


def reader_client() -> bigquery.Client:
    source, _ = google.auth.default(scopes=SCOPES)
    creds = impersonated_credentials.Credentials(
        source_credentials=source, target_principal=READER, target_scopes=SCOPES, lifetime=600
    )
    return bigquery.Client(project=PROJECT, credentials=creds)


def attempt(client: bigquery.Client, sql: str) -> str:
    try:
        client.query(sql, job_config=bigquery.QueryJobConfig(use_query_cache=False)).result(timeout=60)
        return "allowed"
    except Forbidden:
        return "denied"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args()

    run_id = uuid.uuid4().hex[:8]
    probe_table = f"{PROJECT}.gold.ri_write_probe_{run_id}"
    probes = [
        ("gold read", f"SELECT COUNT(*) FROM `{PROJECT}.gold.dim_metro`", "allowed"),
        ("gold write", f"CREATE TABLE `{probe_table}` AS SELECT 1 AS x", "denied"),
        ("silver read", f"SELECT COUNT(*) FROM `{PROJECT}.silver.stg_zori_metro_month`", "denied"),
    ]

    client = reader_client()
    print(f"run {run_id} as {READER}")
    failures = 0
    try:
        for name, sql, expected in probes:
            outcomes = [attempt(client, sql) for _ in range(args.runs)]
            hits = outcomes.count(expected)
            failures += args.runs - hits
            print(f"{name}: expected {expected}, {hits} of {args.runs}  {outcomes}")
    finally:
        # Cleanup registered before any write: drop the probe table if a write got through.
        owner = bigquery.Client(project=PROJECT)
        owner.delete_table(probe_table, not_found_ok=True)
        leftovers = [t.table_id for t in owner.list_tables(f"{PROJECT}.gold") if t.table_id.startswith("ri_write_probe")]
        print(f"leftover probe tables: {len(leftovers)}")
        failures += len(leftovers)

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

"""C1.T1 feasibility probe: load one Zillow ZORI CSV into the BigQuery sandbox and
check that COUNT(*) equals the CSV data-row count. Appends one result line to probe_bq.log.

Usage: python probe_bq.py <csv_path> [--project rental-insights-511513]
Exit 0 when counts match, 1 when they don't, 2 on load or auth error.
Auth comes from Application Default Credentials (gcloud auth application-default login),
which Patrick runs himself; this script never reads or prints a credential.
"""
import argparse
import csv
import datetime
import hashlib
import pathlib
import sys

from google.cloud import bigquery

DATASET = "probe"
TABLE = "zori_metro"


def csv_data_rows(path):
    with open(path, encoding="utf-8", newline="") as f:
        return sum(1 for _ in csv.reader(f)) - 1  # minus header


def log(line):
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(pathlib.Path(__file__).with_name("probe_bq.log"), "a", encoding="utf-8") as f:
        f.write(f"{stamp} | {line}\n")
    print(line)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--project", default="rental-insights-511513")
    args = ap.parse_args()

    expected = csv_data_rows(args.csv_path)
    sha = hashlib.sha256(pathlib.Path(args.csv_path).read_bytes()).hexdigest()[:12]
    table_id = f"{args.project}.{DATASET}.{TABLE}"
    try:
        client = bigquery.Client(project=args.project)
        client.create_dataset(bigquery.Dataset(f"{args.project}.{DATASET}"), exists_ok=True)
        # WRITE_TRUNCATE keeps a rerun idempotent: the table always holds exactly one load.
        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.CSV,
            skip_leading_rows=1,
            autodetect=True,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        )
        with open(args.csv_path, "rb") as f:
            client.load_table_from_file(f, table_id, job_config=job_config).result()
        actual = next(iter(client.query(f"SELECT COUNT(*) AS n FROM `{table_id}`").result())).n
    except Exception as e:  # report and stop; no retry, the load is a write
        log(f"ERROR | {table_id} | csv_rows={expected} sha={sha} | {type(e).__name__}: {e}")
        return 2

    status = "PASS" if actual == expected else "FAIL"
    log(f"{status} | {table_id} | csv_rows={expected} bq_count={actual} sha={sha}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

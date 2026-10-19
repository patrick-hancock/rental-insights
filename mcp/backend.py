"""Backend choice for query_gold (C3.T6): BigQuery (default) or DuckDB over the Parquet snapshot.

    RI_BACKEND=duckdb python mcp/server.py

The client still writes BigQuery SQL, and mcp/guard.py still checks that SQL first. Under
duckdb, only SQL the guard passed is transpiled (sqlglot, read="bigquery", write="duckdb") and
run on in-memory copies of snapshot/<table>.parquet (scripts/export_parquet.py, C3.T5). This
lets the server and its tests run where nobody has BigQuery credentials (the public mirror).

DuckDB has no service account, so the read-only wall is the connection itself: the tables are
loaded into memory, then file and network access is switched off and the setting is locked, so
a query cannot read files (read_csv, read_text) or turn access back on.
"""

import json
import os
import threading
from datetime import datetime
from pathlib import Path

import sqlglot
from sqlglot import exp

from guard import ALLOWED_TABLES, DIALECT, check_sql

BACKEND_ENV = "RI_BACKEND"
BACKENDS = ("bigquery", "duckdb")
SNAPSHOT_DIR = Path(__file__).resolve().parents[1] / "snapshot"


def backend_name() -> str:
    """The backend RI_BACKEND names (read at each call); bigquery when unset."""
    name = (os.environ.get(BACKEND_ENV) or "bigquery").strip().lower()
    if name not in BACKENDS:
        raise ValueError(f"{BACKEND_ENV}={name!r} is not one of {list(BACKENDS)}")
    return name


def transpile(sql: str) -> str:
    """BigQuery SQL to DuckDB SQL. Gold table names lose their project and dataset qualifiers,
    since the snapshot tables live unqualified in DuckDB's main schema."""
    tree = sqlglot.parse_one(sql, read=DIALECT)
    for table in tree.find_all(exp.Table):
        if table.name.lower() in ALLOWED_TABLES:
            table.set("db", None)
            table.set("catalog", None)
    return tree.sql(dialect="duckdb")


class DuckDBRunner:
    """Runs guarded SQL on the Parquet snapshot. Same run() shape as BigQueryRunner."""

    backend = "duckdb"

    def __init__(self, row_cap: int, timeout_s: float, snapshot_dir: Path = SNAPSHOT_DIR):
        self.row_cap, self.timeout_s, self.snapshot_dir = row_cap, timeout_s, Path(snapshot_dir)
        self._con = None
        self._exported_at = {}  # table -> export time from manifest.json, the snapshot's as-of
        self.last_job = None  # no BigQuery job, so the log has no bytes_processed/bytes_billed/cache_hit

    def _connect(self):
        if self._con is None:
            import duckdb

            tables = json.loads((self.snapshot_dir / "manifest.json").read_text(encoding="utf-8"))["tables"]
            con = duckdb.connect(":memory:")
            for name in sorted(ALLOWED_TABLES):
                path = (self.snapshot_dir / f"{name}.parquet").as_posix()
                con.execute(f"CREATE TABLE {name} AS SELECT * FROM read_parquet('{path}')")
                self._exported_at[name] = datetime.fromisoformat(tables[name]["exported_at"])
            con.execute("SET enable_external_access = false")
            con.execute("SET lock_configuration = true")
            self._con = con
        return self._con

    def _execute(self, duck_sql: str, params=None):
        con = self._connect()
        # DuckDB has no per-query timeout setting; interrupt() from a timer stops the query.
        timer = threading.Timer(self.timeout_s, con.interrupt)
        timer.start()
        try:
            cur = con.execute(duck_sql, params) if params else con.execute(duck_sql)
            columns = [d[0] for d in cur.description]
            rows = [list(r) for r in cur.fetchmany(self.row_cap + 1)]
        finally:
            timer.cancel()
        return columns, rows

    def run(self, sql: str, tables: tuple[str, ...], params=None):
        # query_gold already guarded this SQL; checking again here keeps the rule "only guarded
        # SQL is transpiled" true for any caller that reaches the runner directly.
        guard = check_sql(sql)
        if not guard.ok:
            raise PermissionError(f"guard refused the SQL ({guard.code}); it was not transpiled")
        columns, rows = self._execute(transpile(sql), params)
        as_of = max(self._exported_at[t] for t in tables) if tables else None
        return columns, rows, as_of

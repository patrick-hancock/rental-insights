"""query_gold: run one guarded, read-only SELECT on the gold tables (C3.T3).

The SQL comes from the client's model. It passes mcp/guard.py first, then runs as the
read-only ri-reader service account (D-003) with a row cap, a timeout and a byte cap.
With RI_BACKEND=duckdb it runs on the Parquet snapshot instead (mcp/backend.py, C3.T6); the
log rows then have no bytes_processed, bytes_billed or cache_hit fields, since there is no job.
"""

import json
import re
import time
from datetime import date, datetime
from decimal import Decimal

from backend import DuckDBRunner, backend_name
from guard import PROJECT, DATASET, RETRYABLE, check_sql
from tools.contract import log_call, response
from tools.wiki import suspicious

# 200 rows keeps a response readable in a chat client; aggregate in SQL for more.
ROW_CAP = 200
# Gold queries took a few seconds in C1/C2 checks; 30 s leaves room without hanging the client.
TIMEOUT_S = 30
# All of gold is a few tens of MB (fct_metro_month 237,686 rows); 1 GB stops a runaway scan.
MAX_BYTES_BILLED = 1_000_000_000

# A string value that looks like planted instructions is replaced with this marker (T-09). The
# check is tools/wiki.py suspicious(), the one the wiki tools use, so data and wiki get one detector.
WITHHELD_VALUE = "[withheld: instruction-like text]"
# Response size cap as serialized JSON (T-15). Measured offline 2026-10-13: a full 200-row answer
# in the widest realistic shape (fct_cbsa_affordability joined to dim_metro, 16 columns, the 200
# longest real CBSA names, full-precision doubles) is 58,945 bytes. 250,000 is about 4x that, so
# normal answers never hit it, while 200 rows of REPEAT('x', 100000) (about 20 MB) are cut down.
MAX_RESPONSE_BYTES = 250_000

# BigQuery's two wordings for a column or alias the query names but the tables do not have, as
# raised by the live runner (google.api_core.exceptions.BadRequest, seen in the blind eval run 2
# log on 2026-10-13: "Name metro_id not found inside f at [1:100]"). Only the identifier the
# regex captures reaches the client, and only if the client's own SQL contains it; the raw driver
# message stays in the server log (T-11).
_IDENT = r"[A-Za-z_][A-Za-z0-9_]{0,127}"
# Under RI_BACKEND=duckdb the same mistake is a duckdb BinderException with its own two wordings
# (duckdb 1.5.6, probed 2026-10-19: 'Referenced column "metro_id" not found in FROM clause!' and
# 'Table "f" does not have a column named "metro_id"'). Keyed by the exception's type name.
_UNKNOWN_NAME = {
    "BadRequest": (
        re.compile(rf"^(?:400 )?Unrecognized name: (?P<column>{_IDENT})(?=[\s;]|$)"),
        re.compile(rf"^(?:400 )?Name (?P<column>{_IDENT}) not found inside (?P<alias>{_IDENT})(?=[\s;]|$)"),
    ),
    "BinderException": (
        re.compile(rf'^Binder Error: Referenced column "(?P<column>{_IDENT})" not found in FROM clause'),
        re.compile(rf'^Binder Error: Table "(?P<alias>{_IDENT})" does not have a column named "(?P<column>{_IDENT})"'),
    ),
}
UNKNOWN_COLUMN_HINT = "Check the column names with get_definition or search_wiki (wiki/data_dictionary.md)."


def _unknown_column(e: Exception, sql: str):
    """Return (column, alias or None) if e is the backend's unknown-name error for this SQL, else None."""
    text = str(getattr(e, "message", "") or e)
    for pattern in _UNKNOWN_NAME.get(type(e).__name__, ()):
        m = pattern.match(text)
        if m:
            column, alias = m.group("column"), m.groupdict().get("alias")
            # Echo only names the client wrote itself, so nothing server-side can leak through.
            if all(re.search(rf"\b{re.escape(n)}\b", sql) for n in (column, alias) if n):
                return column, alias
    return None


READER = f"ri-reader@{PROJECT}.iam.gserviceaccount.com"
SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]


class BigQueryRunner:
    """Runs SQL as ri-reader through impersonation of the local login (no key file)."""

    backend = "bigquery"

    def __init__(self):
        self._client = None
        self.last_job = None  # the QueryJob of the latest run, read by query_gold for the log

    def _bq(self):
        if self._client is None:
            import google.auth
            from google.auth import impersonated_credentials
            from google.cloud import bigquery

            source, _ = google.auth.default(scopes=SCOPES)
            creds = impersonated_credentials.Credentials(
                source_credentials=source, target_principal=READER, target_scopes=SCOPES
            )
            self._client = bigquery.Client(project=PROJECT, credentials=creds)
        return self._client

    def run(self, sql: str, tables: tuple[str, ...]):
        from google.cloud import bigquery

        bq = self._bq()
        config = bigquery.QueryJobConfig(maximum_bytes_billed=MAX_BYTES_BILLED, default_dataset=f"{PROJECT}.{DATASET}")
        self.last_job = None
        job = bq.query(sql, job_config=config, timeout=TIMEOUT_S)
        self.last_job = job
        rows_iter = job.result(timeout=TIMEOUT_S, max_results=ROW_CAP + 1)
        columns = [f.name for f in rows_iter.schema]
        rows = [list(r.values()) for r in rows_iter]
        # Freshness from the touched tables only: gold is rebuilt whole, so modified time is the as-of.
        as_of = max(bq.get_table(f"{PROJECT}.{DATASET}.{t}").modified for t in tables) if tables else None
        return columns, rows, as_of


_default_runner = None


def _runner_for_backend():
    """The shared runner for RI_BACKEND, rebuilt if the backend changed since it was made."""
    global _default_runner
    name = backend_name()
    if _default_runner is None or getattr(_default_runner, "backend", None) != name:
        _default_runner = DuckDBRunner(ROW_CAP, TIMEOUT_S) if name == "duckdb" else BigQueryRunner()
    return _default_runner


def _plain(v):
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    return v


def _withhold_suspicious(columns, rows) -> list[dict]:
    """Replace instruction-like string values in place; return where each one was (row, column)."""
    withheld = []
    for i, row in enumerate(rows):
        for j, v in enumerate(row):
            if isinstance(v, str) and suspicious(v):
                row[j] = WITHHELD_VALUE
                withheld.append({"row": i, "column": columns[j] if j < len(columns) else j})
    return withheld


def _job_stats(runner) -> dict:
    """BigQuery cost fields for the log from the runner's last job; {} if there is none."""
    job = getattr(runner, "last_job", None)
    if job is None:
        return {}
    try:
        return {"bytes_processed": job.total_bytes_processed, "bytes_billed": job.total_bytes_billed,
                "cache_hit": job.cache_hit}
    except Exception:
        return {}  # logging is additive; a missing stat must not change the answer


def _size(result: dict) -> int:
    return len(json.dumps(result, default=str))


def _cut_to_size(keys, columns, rows, extra):
    """Keep the leading rows that fit under MAX_RESPONSE_BYTES and say so; refuse if none fit."""
    total = len(rows)
    reason = (f"Response cut to {{kept}} of {total} rows to stay under {MAX_RESPONSE_BYTES:,} bytes. "
              "Select fewer or shorter columns, or aggregate in SQL.")

    def build(n):
        data = {"columns": columns, "rows": rows[:n], "row_count": n, "truncated": True}
        kept_extra = dict(extra)
        if "withheld" in kept_extra:
            kept_extra["withheld"] = [w for w in kept_extra["withheld"] if w["row"] < n]
            if not kept_extra["withheld"]:
                del kept_extra["withheld"]
        return response("answered", source_keys=keys, data=data, reason=reason.format(kept=n),
                        code="size_capped", **kept_extra)

    lo, hi = 0, total - 1  # largest n in [0, total) whose response fits; the full answer did not
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _size(build(mid)) <= MAX_RESPONSE_BYTES:
            lo = mid
        else:
            hi = mid - 1
    if lo == 0:
        result = response("refused", code="too_large", retryable=True,
                          reason=f"Even one row is over {MAX_RESPONSE_BYTES:,} bytes as JSON. "
                                 "Select fewer or shorter columns (for example SUBSTR on long text).")
        return result, []
    return build(lo), rows[:lo]


def query_gold(sql: str, runner=None) -> dict:
    started = time.perf_counter()
    guard = check_sql(sql)
    if not guard.ok:
        result = response("refused", reason=guard.reason, code=guard.code, retryable=guard.code in RETRYABLE)
        log_call("query_gold", started, result, sql=sql)
        return result
    if not guard.tables:
        # A constant query (SELECT 1) has no gold source to cite.
        result = response("refused", reason="The query reads no gold table, so there is nothing to cite.", code="no_source", retryable=False)
        log_call("query_gold", started, result, sql=sql)
        return result

    if runner is None:
        runner = _runner_for_backend()
    try:
        columns, rows, as_of = runner.run(sql, guard.tables)
    except Exception as e:  # detail to the log only; the client gets a plain reason
        unknown = _unknown_column(e, sql)
        if unknown:
            column, alias = unknown
            where = f" in {alias}" if alias else ""
            result = response("refused", code="unknown_column", retryable=True,
                              reason=f"Unknown column '{column}'{where}: no table in the query has it. "
                                     f"{UNKNOWN_COLUMN_HINT} Join keys are listed in the query_gold description.")
            log_call("query_gold", started, result, sql=sql, error=f"{type(e).__name__}: {e}", **_job_stats(runner))
            return result
        result = response("error", reason="The query failed to run. Details are in the server log.", code="execution_error")
        log_call("query_gold", started, result, sql=sql, error=f"{type(e).__name__}: {e}", **_job_stats(runner))
        return result

    keys = [f"gold.{t}" for t in guard.tables]
    extra = {"as_of": _plain(as_of) if as_of else None}
    if not rows:
        result = response("no_data", source_keys=keys, reason="The query returned no rows.", **extra)
    else:
        truncated = len(rows) > ROW_CAP
        rows = [[_plain(v) for v in r] for r in rows[:ROW_CAP]]
        withheld = _withhold_suspicious(columns, rows)
        if withheld:
            extra["withheld"] = withheld
        data = {"columns": columns, "rows": rows, "row_count": len(rows), "truncated": truncated}
        result = response("answered", source_keys=keys, data=data, **extra)
        if _size(result) > MAX_RESPONSE_BYTES:
            result, rows = _cut_to_size(keys, columns, rows, extra)
    log_call("query_gold", started, result, sql=sql, rows=len(rows), **_job_stats(runner))
    return result

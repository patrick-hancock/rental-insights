"""C3.T6: query_gold on DuckDB over the Parquet snapshot (RI_BACKEND=duckdb), offline.

Every test here runs with a trace of guard, transpile and DuckDB calls. After each test the
trace is checked: each transpile follows a guard pass for the same SQL, each DuckDB call follows
a transpile, and SQL the guard refused never reaches transpile or DuckDB. So the guard-first rule
holds in every case of this file, not only in the tests that name it.

Expected values are the C3.T5 probe results on the same snapshot (scripts/probe_duckdb.log,
2026-10-19) and K8 in wiki/kpis.md (323 of 935).
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import backend  # noqa: E402
import tools.query_gold as qg  # noqa: E402
from guard import check_sql as real_check_sql  # noqa: E402
from tools.contract import response_bytes, run_id  # noqa: E402

MANIFEST = json.loads((backend.SNAPSHOT_DIR / "manifest.json").read_text(encoding="utf-8"))["tables"]
JOB_FIELDS = ("bytes_processed", "bytes_billed", "cache_hit")


def _check_guard_first(calls):
    for i, (kind, sql, ok) in enumerate(calls):
        if kind == "transpile":
            last_guard = next((c for c in reversed(calls[:i]) if c[0] == "guard" and c[1] == sql), None)
            assert last_guard is not None and last_guard[2] is True, f"transpiled without a guard pass: {sql}"
        if kind == "duckdb":
            assert i > 0 and calls[i - 1][0] == "transpile", f"DuckDB ran SQL that was not just transpiled: {sql}"
    refused = {sql for kind, sql, ok in calls if kind == "guard" and not ok}
    assert not [c for c in calls if c[0] == "transpile" and c[1] in refused], "refused SQL was transpiled"


@pytest.fixture(autouse=True)
def trace(monkeypatch):
    """Spies on guard, transpile and DuckDB; selects the duckdb backend; checks the order afterwards."""
    calls = []
    real_transpile, real_execute = backend.transpile, backend.DuckDBRunner._execute

    def spy_check(sql):
        result = real_check_sql(sql)
        calls.append(("guard", sql, result.ok))
        return result

    def spy_transpile(sql):
        calls.append(("transpile", sql, None))
        return real_transpile(sql)

    def spy_execute(self, duck_sql, params=None):
        calls.append(("duckdb", duck_sql, None))
        return real_execute(self, duck_sql, params)

    monkeypatch.setattr(qg, "check_sql", spy_check)
    monkeypatch.setattr(backend, "check_sql", spy_check)
    monkeypatch.setattr(backend, "transpile", spy_transpile)
    monkeypatch.setattr(backend.DuckDBRunner, "_execute", spy_execute)
    monkeypatch.setenv(backend.BACKEND_ENV, "duckdb")
    monkeypatch.setattr(qg, "_default_runner", None)
    yield calls
    _check_guard_first(calls)


def _log_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


# --- backend_name ---

def test_backend_name_defaults_to_bigquery(monkeypatch):
    monkeypatch.delenv(backend.BACKEND_ENV, raising=False)
    assert backend.backend_name() == "bigquery"
    monkeypatch.setenv(backend.BACKEND_ENV, " DuckDB ")
    assert backend.backend_name() == "duckdb"


def test_unknown_backend_is_refused_by_name(monkeypatch):
    monkeypatch.setenv(backend.BACKEND_ENV, "sqlite")
    with pytest.raises(ValueError, match="sqlite"):
        backend.backend_name()


# --- transpile ---

@pytest.mark.parametrize("sql, expected", [
    ("SELECT COUNTIF(zori_to_fmr_2br > 1) AS above FROM fct_cbsa_affordability",
     "SELECT COUNT_IF(zori_to_fmr_2br > 1) AS above FROM fct_cbsa_affordability"),
    ("SELECT month_end FROM gold.dim_date", "SELECT month_end FROM dim_date"),
    ("SELECT metro_name FROM `rental-insights-511513.gold.dim_metro`", 'SELECT metro_name FROM "dim_metro"'),
])
def test_transpile_after_guard_drops_qualifiers(trace, sql, expected):
    assert backend.check_sql(sql).ok
    assert backend.transpile(sql) == expected
    assert [c[0] for c in trace] == ["guard", "transpile"]


@pytest.mark.parametrize("calls", [
    [("transpile", "SELECT 1", None)],  # no guard at all
    [("guard", "DROP TABLE dim_date", False), ("transpile", "DROP TABLE dim_date", None)],  # guard refused
    [("guard", "a", True), ("transpile", "a", None), ("guard", "b", True), ("duckdb", "b", None)],  # skipped transpile
])
def test_order_check_catches_a_bypass(calls):
    # The after-test check is only proof if it fails on a bypass; these traces must fail it.
    with pytest.raises(AssertionError):
        _check_guard_first(calls)


# --- DuckDBRunner ---

def test_runner_refuses_unguarded_sql_before_transpile(trace):
    runner = backend.DuckDBRunner(qg.ROW_CAP, qg.TIMEOUT_S)
    with pytest.raises(PermissionError, match="not_select"):
        runner.run("DROP TABLE dim_date", ("dim_date",))
    assert [c[0] for c in trace] == ["guard"] and runner._con is None  # snapshot never even opened


def test_runner_caps_rows_and_dates_as_of_from_manifest():
    runner = backend.DuckDBRunner(qg.ROW_CAP, qg.TIMEOUT_S)
    columns, rows, as_of = runner.run("SELECT month_end FROM dim_date", ("dim_date",))
    assert columns == ["month_end"] and len(rows) == qg.ROW_CAP + 1  # 320 in the table; cap + 1 marks truncation
    assert as_of == datetime.fromisoformat(MANIFEST["dim_date"]["exported_at"])
    assert runner.last_job is None


def test_runner_connection_cannot_read_files_or_unlock():
    runner = backend.DuckDBRunner(qg.ROW_CAP, qg.TIMEOUT_S)
    con = runner._connect()
    with pytest.raises(Exception, match="disabled by configuration"):
        con.execute("SELECT COUNT(*) FROM read_csv('README.md')")
    with pytest.raises(Exception, match="locked"):
        con.execute("SET enable_external_access = true")


def test_runner_timeout_interrupts_a_long_query():
    runner = backend.DuckDBRunner(qg.ROW_CAP, 0.5)
    started = time.perf_counter()
    result = qg.query_gold("SELECT COUNT(*) AS n FROM fct_metro_month a CROSS JOIN fct_metro_month b", runner)
    assert result["status"] == "error" and result["code"] == "execution_error"
    assert time.perf_counter() - started < 10  # 237,686 squared rows would take far longer


# --- query_gold on the duckdb backend ---

@pytest.mark.parametrize("sql, rows", [
    # E06 (T06 verbatim), E02 (T02 verbatim) and K8, as in the BigQuery answers.
    ("SELECT COUNTIF(zori_to_fmr_2br > 1) AS above, COUNT(zori_to_fmr_2br) AS total FROM fct_cbsa_affordability",
     [[299, 381]]),
    ("SELECT COUNTIF(zori_yoy < 0) AS falling, COUNT(zori_yoy) AS with_yoy FROM fct_metro_month "
     "WHERE month_end = DATE '2026-08-31'", [[27, 602]]),
    ("SELECT COUNTIF(rent_burdened_share >= 0.5) AS n, COUNT(*) AS total FROM gold.fct_cbsa_affordability",
     [[323, 935]]),
])
def test_query_gold_answers_from_snapshot(trace, sql, rows):
    result = qg.query_gold(sql)
    assert result["status"] == "answered" and result["data"]["rows"] == rows
    assert result["source_keys"] == [f"gold.{t}" for t in real_check_sql(sql).tables]
    assert [c[0] for c in trace] == ["guard", "guard", "transpile", "duckdb"]  # query_gold, then the runner


def test_e01_median_matches_bigquery_answer():
    sql = ("SELECT ANY_VALUE(m) AS median_zori FROM (SELECT PERCENTILE_CONT(zori, 0.5) OVER () AS m "
           "FROM fct_metro_month WHERE month_end = DATE '2026-08-31' AND zori IS NOT NULL)")
    result = qg.query_gold(sql)
    assert round(result["data"]["rows"][0][0]) == 1388


def test_join_answer_cites_both_tables_and_newest_export():
    sql = ("SELECT m.metro_name, f.zori FROM fct_metro_month f JOIN dim_metro m USING (zillow_region_id) "
           "WHERE f.month_end = DATE '2026-08-31' AND m.size_rank = 1")
    result = qg.query_gold(sql)
    assert result["status"] == "answered"
    assert result["source_keys"] == ["gold.dim_metro", "gold.fct_metro_month"]
    newest = max(MANIFEST[t]["exported_at"] for t in ("dim_metro", "fct_metro_month"))
    assert result["as_of"] == datetime.fromisoformat(newest).isoformat()


def test_row_cap_and_no_data():
    capped = qg.query_gold("SELECT month_end FROM dim_date")
    assert capped["data"]["row_count"] == qg.ROW_CAP and capped["data"]["truncated"] is True
    empty = qg.query_gold("SELECT month_end FROM dim_date WHERE year < 1900")
    assert empty["status"] == "no_data" and empty["source_keys"] == ["gold.dim_date"]


@pytest.mark.parametrize("sql, code", [
    ("DELETE FROM dim_date WHERE TRUE", "not_select"),
    ("SELECT * FROM dim_metro", "select_star"),
    ("SELECT COUNT(*) AS n FROM read_csv('README.md')", "table_not_allowed"),
    ("SELECT month_end FROM dim_date; DROP TABLE dim_date", "multi_statement"),
    ("SELECT zori FROM fct_metro_month WHERE zori > 1 AND zori < 2 OR zori IS NULL", "ambiguous_and_or"),
])
def test_refused_sql_never_reaches_transpile_or_duckdb(trace, sql, code):
    result = qg.query_gold(sql)
    assert result["status"] == "refused" and result["code"] == code
    assert [c[0] for c in trace] == ["guard"]
    assert qg._default_runner is None  # no snapshot was opened for it


def test_constant_query_is_refused_without_transpile(trace):
    result = qg.query_gold("SELECT 1")
    assert result["code"] == "no_source" and [c[0] for c in trace] == ["guard"]


@pytest.mark.parametrize("sql, column, alias", [
    ("SELECT metro_id, zori FROM fct_metro_month LIMIT 5", "metro_id", None),
    ("SELECT f.metro_id FROM fct_metro_month f LIMIT 5", "metro_id", "f"),
])
def test_unknown_column_is_retryable_on_duckdb(sql, column, alias):
    result = qg.query_gold(sql)
    assert result["status"] == "refused" and result["code"] == "unknown_column" and result["retryable"] is True
    assert f"'{column}'" in result["reason"]
    assert (f" in {alias}" in result["reason"]) == bool(alias)
    assert "zillow_region_id" not in result["reason"].split("Join keys")[0]  # DuckDB's candidate list stays out


def test_other_duckdb_errors_keep_the_plain_reason(_isolated_tool_log):
    result = qg.query_gold("SELECT CAST(year_month AS INT64) AS n FROM dim_date")
    assert result["status"] == "error" and result["code"] == "execution_error"
    assert result["reason"] == "The query failed to run. Details are in the server log."
    assert "Conversion Error" in _log_rows(_isolated_tool_log)[-1]["error"]


def test_log_row_has_run_id_and_size_but_no_job_fields(_isolated_tool_log):
    result = qg.query_gold("SELECT COUNT(*) AS n FROM dim_date")
    assert result["data"]["rows"] == [[MANIFEST["dim_date"]["parquet_rows"]]]
    (row,) = _log_rows(_isolated_tool_log)
    assert row["run_id"] == run_id() and row["response_bytes"] == response_bytes(result) > 0
    assert not any(f in row for f in JOB_FIELDS)


def test_default_runner_follows_the_backend(monkeypatch):
    qg.query_gold("SELECT COUNT(*) AS n FROM dim_date")
    assert isinstance(qg._default_runner, backend.DuckDBRunner)
    monkeypatch.setenv(backend.BACKEND_ENV, "bigquery")
    assert isinstance(qg._runner_for_backend(), qg.BigQueryRunner)  # built lazily; no cloud call yet

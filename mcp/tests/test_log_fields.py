"""C9.T2: tool-log rows carry run_id, response_bytes and the BigQuery cost fields, offline.

A fake runner exposes a fake job (the attributes BigQuery's QueryJob has), so no cloud access.
The last test checks the real log file is not touched by these calls (OI-237).
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import contract  # noqa: E402
from tools.query_gold import query_gold  # noqa: E402
from tools.wiki import get_definition, search_wiki  # noqa: E402


class FakeJob:
    total_bytes_processed = 12_345
    total_bytes_billed = 10_485_760
    cache_hit = False


class FakeRunner:
    def __init__(self, rows, job=None, error=None):
        self.rows, self.error = rows, error
        self.last_job = None
        self._job = job

    def run(self, sql, tables):
        self.last_job = self._job
        if self.error:
            raise self.error
        return ["n"], self.rows, datetime(2026, 10, 13, tzinfo=timezone.utc)


def _rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_query_gold_row_has_job_fields(_isolated_tool_log):
    result = query_gold("SELECT COUNT(*) AS n FROM dim_date", FakeRunner([[3653]], job=FakeJob()))
    assert result["status"] == "answered"
    (row,) = _rows(_isolated_tool_log)
    assert row["bytes_processed"] == 12_345
    assert row["bytes_billed"] == 10_485_760
    assert row["cache_hit"] is False
    assert row["response_bytes"] == contract.response_bytes(result) > 0
    assert row["run_id"] == contract.run_id()


def test_cache_hit_true_lands_in_row(_isolated_tool_log):
    class CachedJob(FakeJob):
        total_bytes_processed = 0
        total_bytes_billed = 0
        cache_hit = True

    query_gold("SELECT COUNT(*) AS n FROM dim_date", FakeRunner([[3653]], job=CachedJob()))
    (row,) = _rows(_isolated_tool_log)
    assert row["cache_hit"] is True and row["bytes_billed"] == 0


def test_failed_job_still_logs_job_fields(_isolated_tool_log):
    result = query_gold("SELECT COUNT(*) AS n FROM dim_date",
                        FakeRunner([], job=FakeJob(), error=RuntimeError("boom")))
    assert result["status"] == "error"
    (row,) = _rows(_isolated_tool_log)
    assert row["bytes_processed"] == 12_345 and "response_bytes" in row


def test_runner_without_job_logs_no_job_fields(_isolated_tool_log):
    # Refused before any job, or a runner with no job object: the row simply has no cost fields.
    query_gold("DELETE FROM dim_date WHERE TRUE", FakeRunner([]))
    (row,) = _rows(_isolated_tool_log)
    assert row["status"] == "refused"
    assert "bytes_processed" not in row and row["response_bytes"] > 0


def test_broken_job_does_not_change_answer(_isolated_tool_log):
    class BrokenJob:
        @property
        def total_bytes_processed(self):
            raise RuntimeError("stats unavailable")

    expected = query_gold("SELECT COUNT(*) AS n FROM dim_date", FakeRunner([[1]], job=FakeJob()))
    result = query_gold("SELECT COUNT(*) AS n FROM dim_date", FakeRunner([[1]], job=BrokenJob()))
    assert result == expected
    assert "bytes_processed" not in _rows(_isolated_tool_log)[-1]


def test_run_id_env_override(_isolated_tool_log, monkeypatch):
    monkeypatch.setenv("RI_RUN_ID", "eval-run-7")
    query_gold("SELECT COUNT(*) AS n FROM dim_date", FakeRunner([[1]], job=FakeJob()))
    assert _rows(_isolated_tool_log)[0]["run_id"] == "eval-run-7"
    monkeypatch.delenv("RI_RUN_ID")
    assert contract.run_id() == contract.PROCESS_RUN_ID


def test_wiki_rows_carry_response_bytes(_isolated_tool_log):
    results = [search_wiki("why github pages"), get_definition("K8"), search_wiki("")]
    rows = _rows(_isolated_tool_log)
    assert [r["tool"] for r in rows] == ["search_wiki", "get_definition", "search_wiki"]
    for row, result in zip(rows, results):
        assert row["response_bytes"] == contract.response_bytes(result) > 0
        assert row["run_id"] == contract.run_id()


def test_unwritable_log_does_not_change_answer(tmp_path, monkeypatch):
    # The log path is a directory, so the append fails; the tool still answers the same.
    monkeypatch.setenv("RI_TOOL_LOG", str(tmp_path))
    result = query_gold("SELECT COUNT(*) AS n FROM dim_date", FakeRunner([[1]], job=FakeJob()))
    assert result["status"] == "answered" and result["data"]["rows"] == [[1]]


def test_real_log_untouched(_isolated_tool_log):
    real = contract.DEFAULT_LOG_PATH
    before = real.read_bytes() if real.exists() else None
    assert contract.log_path() == _isolated_tool_log != real
    query_gold("SELECT COUNT(*) AS n FROM dim_date", FakeRunner([[1]], job=FakeJob()))
    search_wiki("why github pages")
    get_definition("K8")
    assert (real.read_bytes() if real.exists() else None) == before
    assert len(_rows(_isolated_tool_log)) == 3

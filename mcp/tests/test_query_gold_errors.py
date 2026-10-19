"""C8.T8: an unknown column comes back as a retryable refusal that names the column.

Blind eval run 2 (packs/eval/results.md) joined fct_metro_month to dim_metro on metro_id and got
only "execution_error", so the answerer could not fix the SQL. Offline: a fake runner raises the
same exception type and wording the live runner raised (google.api_core BadRequest, copied from
the run 2 server log). Tool logs go to a temp file.
"""

import json
import sys
from pathlib import Path

import pytest
from google.api_core.exceptions import BadRequest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tools.contract as contract  # noqa: E402
import tools.query_gold as qg  # noqa: E402

# Token-like but not an OAuth prefix, so test_t12_server_code_holds_no_key_material stays clean.
FAKE_TOKEN = "Bearer FAKE-TEST-TOKEN-not-a-secret"
RUN2_SQL = ("SELECT d.metro_name, f.zhvi FROM fct_metro_month f JOIN dim_metro d "
            "ON f.metro_id = d.metro_id WHERE f.month_end = '2026-08-31' LIMIT 5")


class RaisingRunner:
    def __init__(self, error):
        self.error = error

    def run(self, sql, tables):
        raise self.error


@pytest.fixture
def log_file(monkeypatch, tmp_path):
    path = tmp_path / "tool_calls.jsonl"
    monkeypatch.setattr(contract, "LOG_PATH", path)
    return path


def run2_error(tail=""):
    # The live message shape: "400 <text>; reason: invalidQuery, location: query, message: <text>".
    text = "Name metro_id not found inside f at [1:100]"
    return BadRequest(f"{text}; reason: invalidQuery, location: query, message: {text}{tail}")


def test_unknown_column_inside_alias_is_retryable_and_named(log_file):
    result = qg.query_gold(RUN2_SQL, RaisingRunner(run2_error()))
    assert result["status"] == "refused" and result["retryable"] is True
    assert result["code"] == "unknown_column"
    assert "'metro_id' in f" in result["reason"]
    assert "get_definition" in result["reason"] and "search_wiki" in result["reason"]
    assert "invalidQuery" not in result["reason"]  # the raw driver text stays out
    assert "BadRequest" in log_file.read_text(encoding="utf-8")


def test_unrecognized_name_wording_is_retryable_and_named(log_file):
    sql = "SELECT metro_id, zori FROM fct_metro_month LIMIT 5"
    result = qg.query_gold(sql, RaisingRunner(BadRequest("Unrecognized name: metro_id at [1:8]")))
    assert result["status"] == "refused" and result["retryable"] is True
    assert result["code"] == "unknown_column" and "'metro_id'" in result["reason"]


def test_token_like_text_in_unknown_column_error_is_not_echoed(log_file):
    result = qg.query_gold(RUN2_SQL, RaisingRunner(run2_error(f"\n\ncredentials token {FAKE_TOKEN}")))
    assert result["code"] == "unknown_column"
    assert FAKE_TOKEN not in json.dumps(result)
    assert FAKE_TOKEN in log_file.read_text(encoding="utf-8")  # kept in the local log by design (T-12)


def test_name_not_in_the_clients_sql_is_not_echoed(log_file):
    # A captured "name" the client never wrote could only come from the server side: no echo.
    sql = "SELECT zori FROM fct_metro_month LIMIT 5"
    result = qg.query_gold(sql, RaisingRunner(BadRequest("Unrecognized name: ya29_secret_value at [1:8]")))
    assert result["status"] == "error" and result["code"] == "execution_error"
    assert "ya29_secret_value" not in json.dumps(result)


@pytest.mark.parametrize("error", [
    BadRequest("Syntax error: Unexpected keyword FROM at [1:8]"),
    RuntimeError("Unrecognized name: zori at [1:8]"),  # right wording, wrong exception type
])
def test_other_execution_errors_keep_the_plain_reason(log_file, error):
    result = qg.query_gold("SELECT zori FROM fct_metro_month LIMIT 5", RaisingRunner(error))
    assert result["status"] == "error" and result["code"] == "execution_error"
    assert result["reason"] == "The query failed to run. Details are in the server log."

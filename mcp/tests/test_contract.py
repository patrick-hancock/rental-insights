"""C3.T3: every tool response has source_keys or an uncited status with a reason.

Offline by default (fake runner, no cloud access). Set RI_LIVE=1 to also run one query
through BigQuery as ri-reader.
"""

import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.contract import CITED, STATUSES, UNCITED, response  # noqa: E402
from tools.query_gold import ROW_CAP, query_gold  # noqa: E402


def assert_contract(result: dict):
    assert result["status"] in STATUSES
    if result["status"] in CITED:
        assert result["source_keys"], result
    else:
        assert result.get("reason") and "data" not in result, result


class FakeRunner:
    def __init__(self, rows=None, error=None):
        self.rows, self.error, self.calls = rows or [], error, []

    def run(self, sql, tables):
        self.calls.append(sql)
        if self.error:
            raise self.error
        return ["a", "b"], self.rows, datetime(2026, 10, 13, tzinfo=timezone.utc)


# --- the contract itself ---

def test_contract_rejects_answer_without_source():
    with pytest.raises(ValueError):
        response("answered", data={"x": 1})


def test_contract_rejects_refusal_with_data():
    with pytest.raises(ValueError):
        response("refused", reason="no", data={"x": 1})


# --- query_gold ---

def test_query_answered_cites_tables_and_as_of():
    runner = FakeRunner(rows=[[1, date(2026, 8, 31)]])
    result = query_gold("SELECT m.metro_name, f.month_end FROM fct_metro_month f JOIN dim_metro m USING (zillow_region_id)", runner)
    assert_contract(result)
    assert result["status"] == "answered"
    assert result["source_keys"] == ["gold.dim_metro", "gold.fct_metro_month"]
    assert result["data"]["rows"] == [[1, "2026-08-31"]]
    assert result["as_of"].startswith("2026-10-13")


def test_query_no_rows_is_no_data_with_sources():
    result = query_gold("SELECT cbsa_code FROM fct_cbsa_affordability WHERE cbsa_code = 'none'", FakeRunner(rows=[]))
    assert_contract(result)
    assert result["status"] == "no_data"
    assert result["source_keys"] == ["gold.fct_cbsa_affordability"]


def test_query_refused_never_runs():
    runner = FakeRunner(rows=[[1]])
    result = query_gold("DELETE FROM gold.dim_metro WHERE TRUE", runner)
    assert_contract(result)
    assert result["status"] == "refused" and result["code"] == "not_select"
    assert result["retryable"] is False
    assert runner.calls == []


def test_query_logic_refusal_is_retryable():
    result = query_gold("SELECT * FROM dim_metro", FakeRunner())
    assert_contract(result)
    assert result["code"] == "select_star" and result["retryable"] is True


def test_query_without_table_is_refused():
    runner = FakeRunner(rows=[[1]])
    result = query_gold("SELECT 1", runner)
    assert_contract(result)
    assert result["code"] == "no_source" and runner.calls == []


def test_query_error_hides_internal_detail():
    result = query_gold("SELECT month_end FROM dim_date", FakeRunner(error=RuntimeError("secret internal path C:/x")))
    assert_contract(result)
    assert result["status"] == "error"
    assert "C:/x" not in str(result)


def test_query_row_cap_marks_truncated():
    rows = [[i, i] for i in range(ROW_CAP + 1)]
    result = query_gold("SELECT month_end, year FROM dim_date", FakeRunner(rows=rows))
    assert_contract(result)
    assert result["data"]["row_count"] == ROW_CAP and result["data"]["truncated"] is True


@pytest.mark.skipif(os.environ.get("RI_LIVE") != "1", reason="live BigQuery check; set RI_LIVE=1")
def test_query_live_k8_count():
    # K8 in wiki/kpis.md: 323 of 935 CBSAs (measured 2026-10-13).
    result = query_gold("SELECT COUNTIF(rent_burdened_share >= 0.5) AS n, COUNT(*) AS total FROM fct_cbsa_affordability")
    assert_contract(result)
    assert result["data"]["rows"] == [[323, 935]]


def test_query_gold_over_mcp_returns_the_contract():
    # Through the MCP layer, as Claude Desktop sees it; a refused query needs no cloud access.
    import asyncio
    import json

    from mcp import Client
    from server import server

    async def call():
        async with Client(server, read_timeout_seconds=30) as client:
            return await client.call_tool("query_gold", {"sql": "SELECT * FROM dim_metro"})

    result = asyncio.run(call())
    payload = result.structured_content or json.loads(result.content[0].text)
    payload = payload.get("result", payload)
    assert_contract(payload)
    assert payload["code"] == "select_star"


# --- search_wiki and get_definition (read the real wiki/ folder) ---

from tools.wiki import get_definition, search_wiki  # noqa: E402


def test_search_answered_cites_sections():
    result = search_wiki("why github pages")
    assert_contract(result)
    assert result["status"] == "answered"
    assert result["source_keys"][0].startswith("wiki/decisions.md#d-002")


def test_search_off_topic_is_no_data_citing_corpus():
    result = search_wiki("bitcoin price")
    assert_contract(result)
    assert result["status"] == "no_data"
    assert "wiki/kpis.md" in result["source_keys"]


def test_search_stopwords_only_needs_clarification():
    result = search_wiki("what is the")
    assert_contract(result)
    assert result["status"] == "needs_clarification"


@pytest.mark.parametrize(
    "term, kpi, match",
    [
        ("K4", "K4", "exact"),
        ("zori_yoy", "K2", "exact"),
        ("Rent to income", "K6", "exact"),
        ("yield", "K3", "name_words"),
        ("gross rent yeild", "K3", "typo"),
        ("severly rent burdened share", "K5", "typo"),
    ],
)
def test_definition_answered(term, kpi, match):
    result = get_definition(term)
    assert_contract(result)
    assert result["data"]["id"] == kpi and result["data"]["match"] == match
    assert result["source_keys"][0].startswith(f"wiki/kpis.md#{kpi.lower()}-")


def test_definition_ambiguous_asks():
    result = get_definition("rent burdened")
    assert_contract(result)
    assert result["status"] == "needs_clarification"
    assert result["candidates"] == ["K4", "K5", "K8"]


@pytest.mark.parametrize("term", ["vacancy rate", "median income", "zhvi"])
def test_definition_unknown_is_no_data(term):
    # median income scored 67 against 'rent to income', the closest non-KPI term measured.
    result = get_definition(term)
    assert_contract(result)
    assert result["status"] == "no_data"


def test_server_lists_all_tools_over_stdio():
    # Same launch path Claude Desktop uses.
    import asyncio

    from mcp import Client, StdioServerParameters

    params = StdioServerParameters(command=sys.executable, args=[str(Path(__file__).resolve().parents[1] / "server.py")])

    async def names():
        async with Client(params, read_timeout_seconds=30) as client:
            return sorted(t.name for t in (await client.list_tools()).tools)

    assert asyncio.run(names()) == ["get_definition", "ping", "query_gold", "search_wiki"]


def test_definition_word_stem_still_matches():
    # Found while writing packs/qa (2026-10-13): "rent burden" returned no_data.
    result = get_definition("rent burden")
    assert_contract(result)
    assert result["status"] == "needs_clarification"
    assert result["candidates"] == ["K4", "K5", "K8"]

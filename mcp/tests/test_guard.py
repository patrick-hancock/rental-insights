"""C3.T2: the SQL guardrail. Each case names the refusal code it must land on."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from guard import RETRYABLE, check_sql  # noqa: E402

ALLOWED = [
    pytest.param("SELECT cbsa_code, hud_fmr_2br_weighted FROM fct_cbsa_affordability", id="in-scope"),
    pytest.param("SELECT 1;", id="trailing-semicolon"),
    pytest.param(
        "SELECT m.metro_name, f.month_end FROM gold.fct_metro_month f "
        "JOIN `rental-insights-511513.gold.dim_metro` m ON f.zillow_region_id = m.zillow_region_id",
        id="qualified-join",
    ),
    pytest.param(
        "WITH latest AS (SELECT MAX(month_end) AS m FROM dim_date) SELECT m FROM latest",
        id="cte",
    ),
    pytest.param("SELECT COUNT(*) AS n FROM fct_metro_month", id="count-star"),
    pytest.param("SELECT month_end FROM dim_date UNION ALL SELECT month_end FROM fct_metro_month", id="union"),
]

REFUSED = [
    pytest.param("", "empty", id="empty"),
    pytest.param("SELECT FROM WHERE (", "parse_error", id="parse-error"),
    pytest.param("SELECT 1; SELECT 2", "multi_statement", id="two-selects"),
    pytest.param("SELECT 1; DROP TABLE gold.dim_metro", "multi_statement", id="select-then-drop"),
    pytest.param("DROP TABLE gold.dim_metro", "not_select", id="drop"),
    pytest.param("DECLARE x INT64", "not_select", id="script-declare"),
    pytest.param("CALL gold.p()", "not_select", id="call-procedure"),
    pytest.param("EXPORT DATA OPTIONS(uri='gs://b/x*.csv', format='CSV') AS SELECT 1", "not_select", id="export-data"),
    pytest.param("SELECT region_name FROM silver.stg_zori_metro_month", "table_not_allowed", id="silver-table"),
    pytest.param("SELECT x FROM other_table", "table_not_allowed", id="unlisted-table"),
    pytest.param("SELECT x FROM `other-project.gold.dim_metro`", "table_not_allowed", id="other-project"),
    pytest.param("SELECT table_name FROM gold.INFORMATION_SCHEMA.TABLES", "table_not_allowed", id="information-schema"),
    pytest.param(
        "SELECT cbsa_code FROM fct_cbsa_affordability WHERE cbsa_code IN (SELECT cbsa FROM bronze.acs_raw)",
        "table_not_allowed",
        id="subquery-table",
    ),
    pytest.param(
        "WITH dim_metro AS (SELECT region_name FROM silver.stg_zori_metro_month) SELECT region_name FROM dim_metro",
        "table_not_allowed",
        id="cte-shadows-gold-name",
    ),
    pytest.param("SELECT * FROM dim_metro", "select_star", id="select-star"),
    pytest.param("SELECT m.* FROM dim_metro m", "select_star", id="table-star"),
    pytest.param("SELECT * EXCEPT (cbsa_code) FROM fct_cbsa_affordability", "select_star", id="star-except"),
    pytest.param("SELECT n FROM (SELECT * FROM dim_date) AS n", "select_star", id="star-in-subquery"),
    pytest.param(
        "SELECT metro_name FROM dim_metro WHERE state = 'TX' AND size_rank < 50 OR state = 'AL'",
        "ambiguous_and_or",
        id="and-then-or",
    ),
    pytest.param(
        "SELECT metro_name FROM dim_metro WHERE state = 'TX' OR state = 'AL' AND size_rank < 50",
        "ambiguous_and_or",
        id="or-then-and",
    ),
    pytest.param(
        "SELECT cbsa_code FROM fct_cbsa_affordability HAVING cbsa_code = 'a' AND (cbsa_code = 'b' OR "
        "cbsa_code = 'c' AND cbsa_code = 'd')",
        "ambiguous_and_or",
        id="mixed-inside-parens",
    ),
]

# Explicit parentheses make the same filters unambiguous.
ALLOWED += [
    pytest.param(
        "SELECT metro_name FROM dim_metro WHERE (state = 'TX' OR state = 'AL') AND size_rank < 50",
        id="parenthesized-or",
    ),
    pytest.param(
        "SELECT metro_name FROM dim_metro WHERE (state = 'TX' AND size_rank < 50) OR state = 'AL'",
        id="parenthesized-and",
    ),
]


def test_only_logic_errors_are_retryable():
    # Scope and security refusals must never be retried with a hint.
    assert RETRYABLE == {"ambiguous_and_or", "select_star"}


@pytest.mark.parametrize("sql", ALLOWED)
def test_allowed(sql):
    result = check_sql(sql)
    assert result.ok, result.reason


@pytest.mark.parametrize("sql, code", REFUSED)
def test_refused(sql, code):
    result = check_sql(sql)
    assert not result.ok
    assert result.code == code, result.reason

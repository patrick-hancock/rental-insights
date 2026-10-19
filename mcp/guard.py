"""SQL guardrail (C3.T2): checks generated SQL on its parsed tree before anything runs.

This is the second wall. The first is the executing identity, which must be read-only
and limited to the gold dataset; the guardrail never replaces that.

    from guard import check_sql
    result = check_sql("SELECT cbsa_code FROM fct_cbsa_affordability")
    result.ok, result.code, result.reason

Rules run in order and the first failure is returned, so a refusal names one reason.
"""

from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

DIALECT = "bigquery"
PROJECT = "rental-insights-511513"
DATASET = "gold"

# The only tables a query may read: the four gold models (models/gold/schema.yml).
ALLOWED_TABLES = frozenset({"dim_date", "dim_metro", "fct_metro_month", "fct_cbsa_affordability"})

# Statement classes that write, change schema, or run scripts. Looked up by name so a
# class missing from a future sqlglot version is skipped instead of raising.
_FORBIDDEN_NAMES = (
    "Insert", "Update", "Delete", "Merge", "Create", "Drop", "Alter", "TruncateTable",
    "Command", "Copy", "Set", "Use", "Grant", "Revoke", "LoadData", "Declare", "Export",
)
FORBIDDEN_NODES = tuple(getattr(exp, n) for n in _FORBIDDEN_NAMES if hasattr(exp, n))

# Functions that call models, external systems or key material: they cost money or leave
# BigQuery (C3.T4, OWASP LLM10/ASI02). Matched on the rendered name's prefix.
DENIED_FUNCTION_PREFIXES = ("AI.", "ML.", "VECTOR_SEARCH", "EXTERNAL_QUERY", "EXTERNAL_OBJECT_TRANSFORM", "KEYS.", "AEAD.")
_FUNC_NODES = tuple(getattr(exp, n) for n in ("Func", "Predict") if hasattr(exp, n))

# Generated analytical SQL over four tables stays well under 10,000 characters (the longest
# test query is under 300); a larger input is refused before parsing (C3.T4, LLM10).
MAX_SQL_CHARS = 10_000

# Refusal codes a caller may retry with the reason as a correction hint (at most 2 attempts).
# Scope and security refusals are never retried.
RETRYABLE = frozenset({"ambiguous_and_or", "select_star"})


@dataclass(frozen=True)
class GuardResult:
    ok: bool
    code: str = "ok"
    reason: str = ""
    tables: tuple[str, ...] = ()  # gold tables the query reads, sorted; set only when ok


def _refuse(code: str, reason: str) -> GuardResult:
    return GuardResult(ok=False, code=code, reason=reason)


def check_sql(sql: str) -> GuardResult:
    """Return ok, or the first rule the SQL breaks."""
    if not sql or not sql.strip():
        return _refuse("empty", "No SQL was given.")
    if len(sql) > MAX_SQL_CHARS:
        return _refuse("too_large", f"SQL is {len(sql)} characters; the limit is {MAX_SQL_CHARS}.")
    try:
        statements = [s for s in sqlglot.parse(sql, read=DIALECT) if s is not None]
    except ParseError as e:
        return _refuse("parse_error", f"SQL did not parse: {e.errors[0]['description'] if e.errors else e}")
    except RecursionError:
        return _refuse("too_complex", "SQL is nested too deeply to check.")
    if len(statements) != 1:
        return _refuse("multi_statement", f"Exactly one statement is allowed; found {len(statements)}.")
    tree = statements[0]

    if not isinstance(tree, (exp.Select, exp.Union)):
        return _refuse("not_select", f"Only SELECT or UNION queries are allowed; got {type(tree).__name__}.")
    nested = next(tree.find_all(*FORBIDDEN_NODES), None)
    if nested is not None:
        return _refuse("not_select", f"A {type(nested).__name__} statement is nested inside the query.")
    for func in tree.find_all(*_FUNC_NODES):
        # AI.GENERATE parses as Dot(AI, AIGenerate): the namespace lives on the parent.
        node = func.parent if isinstance(func.parent, exp.Dot) else func
        name = node.sql(dialect=DIALECT).split("(", 1)[0].strip().upper()
        if name.startswith(DENIED_FUNCTION_PREFIXES):
            return _refuse("function_not_allowed", f"{name} calls a model or an external system and is not allowed.")

    bad_tables = _unlisted_tables(tree)
    if bad_tables:
        return _refuse(
            "table_not_allowed",
            f"Only gold tables {sorted(ALLOWED_TABLES)} may be queried; found {bad_tables}.",
        )

    for select in tree.find_all(exp.Select):
        for projection in select.expressions:
            if isinstance(projection, exp.Star) or (
                isinstance(projection, exp.Column) and isinstance(projection.this, exp.Star)
            ):
                return _refuse("select_star", "SELECT * is not allowed; name each column.")

    # sqlglot keeps explicit parentheses as Paren nodes, so an AND directly under an OR
    # (or the reverse) means the author relied on precedence.
    for node in tree.find_all(exp.And, exp.Or):
        other = exp.Or if isinstance(node, exp.And) else exp.And
        if isinstance(node.parent, other):
            return _refuse(
                "ambiguous_and_or",
                "AND and OR are mixed without parentheses; wrap each OR group in parentheses.",
            )

    tables = sorted({t.name.lower() for t in tree.find_all(exp.Table) if t.name.lower() in ALLOWED_TABLES})
    return GuardResult(ok=True, tables=tuple(tables))


def _unlisted_tables(tree: exp.Expression) -> list[str]:
    """Every table reference that is not a CTE name or an allowed gold table."""
    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    bad = []
    for table in tree.find_all(exp.Table):
        name, db, catalog = table.name.lower(), table.db.lower(), table.catalog.lower()
        full = ".".join(p for p in (catalog, db, name) if p)
        if not db and not catalog and name in cte_names:
            continue
        if name not in ALLOWED_TABLES or db not in ("", DATASET) or catalog not in ("", PROJECT):
            bad.append(full)
    return bad

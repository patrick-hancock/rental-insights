# System card: Rental Insights MCP server

This card describes what the Rental Insights MCP server does, how it is protected, how well it performed in evaluation, and where it falls short. Every figure on this card names the repository file it comes from.

## Purpose

The Rental Insights MCP server lets a Claude client answer questions about US rental housing from tested data. It is a small local server (`mcp/server.py`) that Claude Desktop or Claude Code launches over standard input and output. It opens no network port.

The client's own model writes the SQL. The server checks that SQL, runs it read-only against the four gold tables built by dbt from public Zillow, HUD and Census data, and returns rows together with the tables they came from. The server itself makes no language model calls, so there is no model cost inside the project (`wiki/architecture.md`, decision record AR-3).

Every data answer follows one rule, called the cite-or-refuse contract (`mcp/tools/contract.py`): a response either carries the source keys for what it returns (a gold table or a wiki section) or carries a plain reason for why it returns nothing. A response that would break this rule raises an error inside the server instead of reaching the client.

The server is meant for one person working locally over public, area-level aggregate data. It is not a multi-user service and holds no data about individuals.

## Tools

The server offers four tools (`mcp/server.py`).

| Tool | What it does | Code |
|---|---|---|
| `query_gold` | Runs one read-only SELECT, written in BigQuery SQL, on the four gold tables: `fct_metro_month`, `fct_cbsa_affordability`, `dim_metro` and `dim_date`. It returns at most 200 rows, the gold tables it read as source keys, and an `as_of` date for the data. | `mcp/tools/query_gold.py` |
| `search_wiki` | Searches the project wiki (KPI definitions, data dictionary, decision records) and returns up to 3 matching sections, each cited as `wiki/<file>#<section>`. | `mcp/tools/wiki.py` |
| `get_definition` | Returns one KPI definition (formula, grain, source column, coverage) from `wiki/kpis.md`. It accepts a KPI id, a name or a gold column, and asks which one is meant when a term fits several KPIs. | `mcp/tools/wiki.py` |
| `ping` | A health check that returns "pong". | `mcp/server.py` |

`query_gold` can run on one of two back ends, chosen by the environment variable `RI_BACKEND` (`mcp/backend.py`):

- **BigQuery** (the default). Queries run in the BigQuery sandbox as a read-only service account, `ri-reader`, which can read the gold dataset and nothing else (`wiki/decisions.md`, decision D-003). The `as_of` date is the newest modified time of the tables the query read.
- **DuckDB** (`RI_BACKEND=duckdb`). Queries run on a Parquet snapshot of the gold tables kept in `snapshot/`, so the server and its tests work without any Google Cloud project. This is the back end the public code mirror uses. The `as_of` date is the snapshot's export time from `snapshot/manifest.json`, not the time of the query.

Each response has one of five statuses: answered, no_data, needs_clarification, refused or error (`mcp/tools/contract.py`). A refusal may say it is retryable, which means the client can fix its SQL using the stated reason.

## Guardrails

Model-written SQL is treated as untrusted. The full list of risks, the code that stops each one and the test that proves it is in the threat model, [threat_model.md](threat_model.md) (`wiki/threat_model.md`), which records 19 in-scope risks, all marked mitigated and none open. The main controls are these.

**Two walls around generated SQL** (`wiki/architecture.md`, decision record AR-4):

1. **The SQL guard** (`mcp/guard.py`) checks the parsed SQL tree before anything runs. It allows exactly one SELECT (or UNION) statement, refuses any statement that writes or changes schema, allows only the four gold tables, refuses `SELECT *`, refuses AND and OR mixed without parentheses, and refuses functions that call models, external systems or key material (names starting with `AI.`, `ML.`, `KEYS.`, `AEAD.` and similar). Input over 10,000 characters is refused before parsing.
2. **The executing identity.** On BigQuery, queries run as the read-only `ri-reader` account, so a query that got past the guard still could not write. A live probe was denied `CREATE TABLE` 5 of 5 times (`wiki/decisions.md`, D-003). On DuckDB there is no service account, so the wall is the connection itself: the snapshot tables are loaded into memory, then file and network access is switched off and the setting is locked (`mcp/backend.py`).

**The guard runs before translation.** Under DuckDB the client still writes BigQuery SQL. The guard checks that SQL first, and only SQL the guard passed is translated to DuckDB SQL with sqlglot. The DuckDB runner checks the SQL again before translating, so the rule holds even for a caller that reaches the runner directly (`mcp/backend.py`; tests in `mcp/tests/test_backend_duckdb.py`).

**Per-query limits** (`mcp/tools/query_gold.py`): at most 200 rows, a 30-second timeout, a 1 GB cap on bytes billed for each BigQuery job, and a 250,000-byte cap on the response as JSON. The wiki tools refuse input over 500 characters (`mcp/tools/wiki.py`).

**Planted instructions** (`mcp/tools/wiki.py`, `mcp/tools/query_gold.py`): wiki sections that look like instructions to the model are withheld and named rather than returned (threat T-08, prompt injection in wiki text). String values in query results that look like instructions are replaced with a marker (threat T-09, prompt injection in data values).

**Errors do not leak detail.** A failed query returns a plain reason; the driver's message goes only to the local server log. The one exception is an unknown-column error, which comes back as a retryable refusal naming the column, and only when the client's own SQL contains that name (threat T-11, internal detail in error messages; `mcp/tools/query_gold.py`).

## Eval results

The server was evaluated with an eval pack of 40 questions, E01 to E40 (`packs/eval/questions.md`). A question passes only if the response status and every number match the expected answer, and any number given on a refusal is a fail. Results for both runs are in `packs/eval/results.md`. Both runs used the BigQuery back end; the DuckDB back end was added later (commits 129bb19 to 0c63ac7) and has not been through an eval run.

| Run | Date | Blind? | Result | Source |
|---|---|---|---|---|
| Run 2 | 2026-10-13 | Yes | 33 of 40 passed (82.5%) | `packs/eval/results.md`, "Run 2 counts" |
| Run 1 | 2026-10-13 | No | 39 of the 39 questions run passed; 1 question (E09) was not run | `packs/eval/results.md`, "Summary" |

**Run 2 (blind, 2026-10-13)** is the result to rely on. Four separate model sessions answered the questions in 4 batches of 10, using only the MCP tools and the answering rules, with no access to the expected answers. A separate grader compared each answer with the key without re-running queries. The 7 failures were E03, E11, E18, E21, E29, E31 and E39 (`packs/eval/results.md`). They are described under Known limits below.

**Run 1 (not blind, 2026-10-13)** showed that the tools return the expected values and statuses, but it is weaker evidence. The answering model had read the expected answers before answering, and all 40 questions were answered in one session. If the question that was not run counts as not passed, the result is 39 of 40 (97.5%). E09 (a request to drop a table) was blocked by the client's own permission check before it reached the server, and is covered instead by the offline guard test `mcp/tests/test_guard.py` (`packs/eval/results.md`).

## Known limits

- **7 of 40 questions failed in the blind run** (`packs/eval/results.md`, run 2). They fall into three groups:
  - **A guessed join key (E03, E21, E31).** Answering sessions joined two tables on a column called `metro_id`, which does not exist; the real key is `zillow_region_id`. At that time the server returned an execution error with no usable reason, so the client could not correct its SQL and gave no answer. Since run 2, the join keys have been added to the `query_gold` description and an unknown column now comes back as a retryable refusal that names it (`mcp/server.py`, `mcp/tools/query_gold.py`). No blind run has been done since that change, so the fix is tested offline but not yet measured in an eval.
  - **The wrong status for missing data (E18, E29, E39).** The answers said the right thing and invented no number, but were labelled refused or answered where the key expects no_data. The results file notes that this is partly a mismatch between the answering prompt and the key.
  - **A clarifying question where an answer was expected (E11).** The session asked whether smaller "micro" areas should count; the key expects them to be included.
- **Run 1 was not blind.** The answering model had seen the expected answers, so its 39 of 39 shows that the tools work, not how a fresh model would perform (`packs/eval/results.md`).
- **Neither run used one fresh chat per question.** Run 1 used a single session and run 2 used four sessions of 10 questions each, so earlier answers could influence later ones (`packs/eval/results.md`).
- **Some guardrail paths were not exercised live in the blind run.** For E09, E20 and E28 the answering model refused on its own judgment before sending any query, so the guard's refusals for those cases were tested only by the offline tests in `mcp/tests/test_guard.py` (`packs/eval/results.md`).
- **Each eval was run once.** One run per setup shows what is possible, not how reliable it is.
- **The DuckDB snapshot goes stale.** Under `RI_BACKEND=duckdb`, answers come from a fixed copy of gold exported on 2026-10-19 (`snapshot/manifest.json`). The data does not change until the snapshot is exported again, and the `as_of` date in each response is the export time, so a reader should check it. On BigQuery, the sandbox tables expire after 60 days unless rebuilt (`wiki/architecture.md`, AR-1).
- **The threat model predates the DuckDB back end.** `wiki/threat_model.md` was written on 2026-10-13 for the BigQuery runner. The DuckDB connection controls are described in `mcp/backend.py` and tested in `mcp/tests/test_backend_duckdb.py`, but they do not yet have their own rows in the threat model.
- **Answer quality depends on the client's model.** The server writes no SQL itself; it can only check, run and cite what the client sends (`wiki/architecture.md`, AR-3).
- **The planted-instruction check is pattern-based.** It matches a fixed list of phrasings (`mcp/tools/wiki.py`), so differently worded instructions could get through. The data is public, area-level aggregates, which limits the exposure.

## Why there are no latency or cost figures

This card publishes no response times and no cost per query, by choice.

The server does record the raw material. Every tool call writes one line to a local log, `mcp/logs/tool_calls.jsonl`, with the time taken in milliseconds, a run id that groups the calls of one session or eval run, and the size of the response in bytes (`mcp/tools/contract.py`). On BigQuery, `query_gold` also logs the bytes processed, the bytes billed and whether the cache was hit (`mcp/tools/query_gold.py`); on DuckDB there is no query job, so those fields are absent (`mcp/backend.py`). The log is kept out of version control (`.gitignore`), so it is not part of the published code.

Latency is not published because there is no measured, repeated sample yet. Each eval setup has been run once (`packs/eval/results.md`), and a single run cannot show a typical or worst-case response time. A later eval-history task is planned to add per-run latency figures.

Cost is not published because there is no bill to report. The data lives in the BigQuery sandbox, which is free tier with no billing account (`wiki/architecture.md`, AR-1), and the server makes no language model calls of its own (`wiki/architecture.md`, AR-3). The 1 GB cap on bytes billed for each query (`mcp/tools/query_gold.py`) guards against runaway scans if the project is ever moved to a billed account.

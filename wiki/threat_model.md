# Threat model: MCP server over gold

What can go wrong when a language model drives the Rental Insights MCP server (`mcp/server.py`: query_gold, get_definition, search_wiki, ping), what in the code stops it, and which test proves it. Built in C8.T5 on 2026-10-13 against commit 66554fa plus this change.

## Scope

In scope: the four MCP tools, the SQL guardrail (`mcp/guard.py`), the BigQuery runner in `mcp/tools/query_gold.py`, the wiki tools in `mcp/tools/wiki.py`, the response contract and tool log in `mcp/tools/contract.py`, and the data the tools can reach (the four gold tables and `wiki/*.md`).

Assets: the gold dataset (must not change), the rest of the BigQuery project (must not be read), the GCP bill, the local Google login and the ri-reader identity, the client model's context (must not be steered by planted text), and the chat client (must stay responsive).

Entry points: the `sql` string given to query_gold, the `query` and `term` strings given to search_wiki and get_definition, text inside wiki files, and values inside gold rows.

## How to read the table

- Likelihood and impact are Low, Medium or High, judged for this project: a local, single-user server over public aggregate data.
- Status is **mitigated** (code stops it and a test proves it), or **open** (a real gap; its test is marked `xfail(strict=True)` so the suite records the gap and fails loudly once it is fixed).
- Test files are in `mcp/tests/`: `test_guard.py` (C3.T2), `test_contract.py` (C3.T3), `test_security.py` (C3.T4) and `test_security_w2.py` (C8.T5).

## Risks

| ID | Risk | Asset | Entry point | Likelihood | Impact | Mitigation in code | Test that proves it | Status |
|---|---|---|---|---|---|---|---|---|
| T-01 | SQL that writes or changes schema (INSERT, UPDATE, MERGE, TRUNCATE, DROP, scripts) | gold dataset | query_gold `sql` | Medium | High | `guard.py` check_sql: only Select or Union at the top, no FORBIDDEN_NODES anywhere in the tree; refusal happens before the runner. Second wall: the ri-reader identity has read access only (D-003) | `test_guard.py::test_refused` (drop, script-declare, call-procedure, export-data); `test_contract.py::test_query_refused_never_runs`; `test_security_w2.py::test_t01_write_statements_refused_and_never_reach_runner` | mitigated |
| T-02 | Several statements in one string (stacked queries, script blocks, a statement hidden after a semicolon or in a comment) | gold dataset | query_gold `sql` | Medium | High | `guard.py`: parse with sqlglot and refuse unless exactly one statement; comments never become statements | `test_guard.py::test_refused` (two-selects, select-then-drop); `test_security.py::test_llm01_sql_comment_cannot_add_a_statement`; `test_security_w2.py::test_t02_script_block_refused`, `::test_t02_statement_hidden_in_block_comment_never_runs`, `::test_t02_semicolon_inside_string_is_one_statement` | mitigated |
| T-03 | Reading outside the four gold tables (silver, bronze, other projects, INFORMATION_SCHEMA, job history, wildcard tables, a CTE named like a gold table) | rest of the BigQuery project | query_gold `sql` | Medium | Medium | `guard.py` _unlisted_tables: every table must be in ALLOWED_TABLES, in dataset `gold`, in project `rental-insights-511513`; CTE names only pass when unqualified | `test_guard.py::test_refused` (silver-table, other-project, information-schema, subquery-table, cte-shadows-gold-name); `test_security_w2.py::test_t03_tables_outside_gold_refused` | mitigated |
| T-04 | Paid or external functions (AI., ML., EXTERNAL_QUERY, KEYS., AEAD.) that cost money or leave BigQuery | GCP bill, data leaving BigQuery | query_gold `sql` | Low | High | `guard.py` DENIED_FUNCTION_PREFIXES, checked on every function node | `test_security.py::test_asi02_external_and_model_functions_refused`; `test_security_w2.py::test_t04_key_management_functions_refused` | mitigated |
| T-05 | Code execution through a JavaScript user-defined function | runner identity | query_gold `sql` | Low | High | `guard.py`: CREATE TEMP FUNCTION is a forbidden statement and makes the string multi-statement | `test_security.py::test_asi05_js_udf_refused` | mitigated |
| T-06 | Cost blow-up from a large scan or a slow query | GCP bill | query_gold `sql` | Medium | Medium | `query_gold.py`: MAX_BYTES_BILLED 1 GB on every job (all of gold is a few tens of MB), TIMEOUT_S 30 on submit and on result | `test_security.py::test_llm10_query_job_has_byte_cap_and_timeout` | mitigated |
| T-07 | Exhausting the guardrail itself (very long or very deeply nested SQL) | server availability | query_gold `sql` | Low | Low | `guard.py`: MAX_SQL_CHARS 10,000 checked before parsing; RecursionError becomes a too_complex refusal | `test_security.py::test_llm10_deep_nesting_refused_not_crashed`, `::test_llm10_oversized_sql_refused` | mitigated |
| T-08 | Prompt injection planted in wiki text, returned to the client model as context | client model context | wiki files | Low | Medium | `wiki.py` INJECTION_PATTERNS and suspicious(): a flagged section is withheld and named, never returned | `test_security.py::test_llm01_search_withholds_planted_section`, `::test_llm01_search_keeps_clean_sections_and_names_withheld`, `::test_llm01_definition_refuses_planted_kpi`, `::test_llm01_real_wiki_has_no_false_positives` | mitigated |
| T-09 | Prompt injection planted in a data value (for example a metro name) and returned in query rows | client model context | gold row values | Low | Medium | `query_gold.py` _withhold_suspicious: every returned string goes through the wiki detector (`wiki.py` suspicious); a match is replaced with WITHHELD_VALUE and its row and column are listed in the response's `withheld` field (C8.T7). Checked offline 2026-10-13 against the 3,896 distinct text values in the local raw and seed files: 0 flagged | `test_security_w2.py::test_t09_instruction_like_data_value_is_not_returned_verbatim`, `::test_t09_real_metro_names_pass_unchanged` | mitigated |
| T-10 | Path traversal or arbitrary file reads through the wiki tools | local files (.env, keys, other folders) | search_wiki `query`, get_definition `term` | Low | High | `wiki.py`: inputs are only ever search words; files come from a fixed WIKI_DIR with a non-recursive `*.md` glob; source keys are built from the file name only | `test_security_w2.py::test_t10_load_sections_reads_only_top_level_markdown`, `::test_t10_path_like_input_is_a_search_term_not_a_path` | mitigated |
| T-11 | Secrets or internal detail (tokens, paths) leaking to the client in error messages | Google login, ri-reader identity | any driver error inside query_gold | Low | High | `query_gold.py`: a runner exception becomes a fixed plain reason; the detail goes to the server log only. One exception (C8.T8): BigQuery's unknown-column error becomes a retryable unknown_column refusal that echoes only the identifier a strict regex captures, and only if the client's own SQL contains it | `test_contract.py::test_query_error_hides_internal_detail`; `test_security_w2.py::test_t11_token_in_driver_error_never_reaches_client`; `test_query_gold_errors.py::test_token_like_text_in_unknown_column_error_is_not_echoed`, `::test_name_not_in_the_clients_sql_is_not_echoed` | mitigated |
| T-12 | Secrets landing in the repo through the tool log or a key file | Google login, ri-reader identity | `mcp/logs/tool_calls.jsonl`, source files | Low | High | `.gitignore` ignores `logs/`, `.env*`, `*.pem`, `*.key`; the runner uses impersonation of the local login, so no key file exists. Residual: the local log keeps raw error text by design | `test_security_w2.py::test_t12_log_and_secret_files_are_git_ignored`, `::test_t12_server_code_holds_no_key_material` | mitigated |
| T-13 | Exposure of personal data | people in the source data | query_gold `sql` | Low | High | Data design: gold holds only metro, CBSA and month aggregates from public sources; the guard allow-list is exactly the four gold models, so no lower layer can be read | `test_security_w2.py::test_t13_gold_models_hold_no_person_level_columns`; `test_guard.py::test_refused` (silver-table, subquery-table) | mitigated |
| T-14 | Denial through a huge number of rows | chat client, server memory | query_gold `sql` | Medium | Low | `query_gold.py`: ROW_CAP 200; the job fetches at most 201 rows and the response is marked truncated | `test_contract.py::test_query_row_cap_marks_truncated`; `test_security.py::test_llm10_query_job_has_byte_cap_and_timeout` (max_results) | mitigated |
| T-15 | Denial through huge values (200 rows of very long strings built in SQL, for example with REPEAT) | chat client, server memory | query_gold `sql` | Low | Medium | `query_gold.py` MAX_RESPONSE_BYTES 250,000 on the serialized response (C8.T7): an answer over it keeps only the leading rows that fit, with `truncated: true`, code `size_capped` and a reason naming how many rows were kept; if even one row is too big the call is refused with code `too_large`. The cap is about 4x a full 200-row answer in the widest realistic shape (58,945 bytes, measured offline 2026-10-13). Rows are still fetched before the cap, so server memory holds up to ROW_CAP rows for one call | `test_security_w2.py::test_t15_response_size_is_capped`, `::test_t15_single_row_over_the_cap_is_refused`, `::test_t15_full_normal_answer_is_not_cut` | mitigated |
| T-16 | Oversized input to the wiki tools | server availability | search_wiki `query`, get_definition `term` | Low | Low | `wiki.py` MAX_QUERY_CHARS 500 checked first in both tools; search snippets capped at SNIPPET_CHARS | `test_security.py::test_llm10_oversized_wiki_query_refused`; `test_security_w2.py::test_t16_oversized_definition_term_refused` | mitigated |
| T-17 | The executing identity has more rights than reading gold | gold dataset, rest of the project | runner credentials | Low | High | `query_gold.py` BigQueryRunner impersonates ri-reader (read-only, gold only, D-003); the guard never replaces that wall | `test_security.py::test_asi03_runner_impersonates_reader`; live check `test_security.py::test_asi03_live_write_denied_even_without_guard` (runs with RI_LIVE=1) | mitigated |
| T-18 | A tampered or drifted dependency (sqlglot, mcp, Google client libraries) | the whole server | installed packages | Low | High | `requirements.txt` pins every package with `==` | `test_security.py::test_llm03_dependencies_pinned_and_installed_as_pinned` | mitigated |
| T-19 | Forged entries in the tool log through newlines in input | audit trail | any tool input | Low | Low | `contract.py` log_call writes each call as one `json.dumps` line, so newlines in input are escaped | `test_security_w2.py::test_t19_newline_in_input_cannot_forge_a_log_line` | mitigated |

Totals: 19 in-scope risks, 19 mitigated, 0 open.

## Out of scope

| Area | Why it is out of scope |
|---|---|
| Transport and caller authentication | The server speaks stdio to a local client on one machine; it opens no network port, so there is no remote caller to authenticate. |
| GCP IAM and project settings | Set and checked as operations work (D-003); T-17 covers how the server uses the identity, and the opt-in live test checks the grant. |
| Source data integrity upstream of gold | Zillow, Census and HUD files and the dbt pipeline are covered by dbt tests and data checks, not by the MCP server. |
| The client model's own reasoning and answer quality | Covered by the evaluation work, not by server-side controls; the server's job is to return cited data or refuse. |
| Static site and Claude Dashboard | Separate front ends (C2, C7) with their own review; they do not go through the MCP server. |
| A compromised local machine, and local disk use (tool log growth) | Anyone with the local login already has the BigQuery access the server has; the log is local and grows by one line per call. |
| Project-wide BigQuery quotas | Billing alerts and quotas are account settings; T-06 caps each query. |

## Open gaps

- **T-09:** closed in C8.T7 (2026-10-13); see the row above.
- **T-15:** closed in C8.T7 (2026-10-13); see the row above.

Both gaps found in C8.T5 were closed in C8.T7 by changes to `mcp/tools/query_gold.py`; their strict xfail markers were removed in the same commits. A new gap gets the same treatment: a strict xfail test and an open row, updated together when it is fixed.

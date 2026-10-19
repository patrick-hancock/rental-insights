# Adoption guide (C8.T6)

How a team would take up this project's tools: a local MCP server that lets Claude answer questions from the gold tables with citations, the dbt models that build those tables, and five runnable packs. Written on 2026-10-13 from the repo as it stands; nothing here has been tried by a second team yet.

## Who it is for

- **Analysts and BI developers** who want Claude to answer rent and affordability questions from tested tables, with a source on every number, instead of from its own memory.
- **Data engineers** who want a small, worked example of model-written SQL behind two walls: a read-only identity and a parsed-SQL guardrail (see [architecture.md](architecture.md), AR-4).
- **Team leads** who need evidence before switching an AI feature on: a golden question set, a results report, a bounded improvement loop and a threat model.

It is not a production service. It is a single-user, local setup over public aggregate data (Zillow, HUD, Census). Nothing in it is about individual people.

## What you get

| Piece | Where | What it does |
|---|---|---|
| Gold tables | `models/gold/` (dbt) | 2 facts and 2 dimensions: `fct_metro_month`, `fct_cbsa_affordability`, `dim_metro`, `dim_date`; columns in [data_dictionary.md](data_dictionary.md), KPIs K1 to K8 in [kpis.md](kpis.md) |
| MCP server | `mcp/server.py` | four tools over stdio: query_gold (one checked SELECT on gold), search_wiki (cited wiki sections), get_definition (one KPI), ping |
| SQL guardrail | `mcp/guard.py` | one SELECT only, gold tables only, named columns, no paid or external functions, size and nesting limits |
| Packs | `packs/` | prompts with sample inputs and expected outputs that anyone can paste into their own LLM |
| Checks | `scripts/`, `mcp/tests/`, `.claude/settings.json` | pytest suite, pack checker, data dictionary checker, KPI spot check, and a Stop hook that runs the tests at the end of each Claude turn ([runbooks.md](runbooks.md)) |

## Setup

Each step names the check that shows it worked.

1. **Python.** Create a virtual environment outside any synced folder and install `requirements.txt` (every package is pinned with `==`; see the repo README). Check: `python -m pytest -q` passes offline; live tests stay skipped unless `RI_LIVE=1`.
2. **BigQuery project.** Use your own Google Cloud project (the BigQuery sandbox works; it needs no billing account). Sign in for local tools with `gcloud auth application-default login`. `profiles.yml` holds no secrets: dbt uses those application default credentials.
3. **Load and build.** Run `ingest/ingest_bronze.py` to fill bronze, then `dbt build` for silver and gold. Check: `scripts/check_counts.py` (bronze rows equal source rows), `dbt test` (33 tests on gold at the time of writing), `scripts/dq_report.py --check`, `scripts/check_dictionary.py`. In the sandbox, tables expire after 60 days, so plan a rebuild ([architecture.md](architecture.md), AR-1).
4. **Read-only access.** Create a reader service account with exactly two roles: BigQuery Job User on the project and BigQuery Data Viewer on the `gold` dataset only. Let each person's own login impersonate it, so no key file exists (D-003 in [decisions.md](decisions.md)). Check: `scripts/probe_readonly.py --runs 5` must show gold reads allowed, `CREATE TABLE` in gold denied and silver reads denied, 5 of 5 each.
5. **Point the code at your project.** The project id `rental-insights-511513` is written into `profiles.yml`, `PROJECT` in `mcp/guard.py` (the runner in `mcp/tools/query_gold.py` builds the reader account name from it) and the query_gold description in `mcp/server.py`. Change them to your project, then run the full test suite again.
6. **Register the MCP server.** In Claude Desktop or Claude Code, add an MCP server named `rental-insights` whose command is the virtual environment's Python and whose argument is the path to `mcp/server.py`. Restart the client so it starts the server. Check: the client lists the four tools; ping returns pong; asking "How many metro and micro areas have half or more of renters rent-burdened?" returns 323 of 935 cited to `gold.fct_cbsa_affordability` while the data is unchanged (K8).

## The packs and when to use each

Every pack has the same six sections (Purpose, Setup, Prompt, Sample inputs, Expected outputs, How to check), enforced by `scripts/check_packs.py`.

| Pack | Use it when | Needs the server? |
|---|---|---|
| `packs/qa/` (cite or refuse) | You want Claude to answer data questions where every number carries a source, and to refuse or ask back instead of guessing. Start here. | Best with it; a definitions-only mode works with two wiki files attached |
| `packs/eval/` (golden set) | Before and after any change to the prompt, the tools or the wiki: 40 questions (E01 to E40) with known answers and statuses | Yes |
| `packs/improve/` (improvement loop) | An eval row fails and you want to fix it without breaking other rows: one failed row, at most 3 fixes, a regression check against all 40 rows, a person ships | Yes |
| `packs/agents/` (checked handoffs) | You are building a multi-step or multi-agent workflow and want each handoff checked by a script before the next step uses it (`scripts/validate_handoff.py`) | No |
| `packs/lease/` (document extraction) | You extract fields from documents and want nulls instead of guesses, plus traps for conflicting terms and text addressed to the model inside a document. All five leases are made up. | No |

## Guardrails and limits

- **Two walls around generated SQL.** The reader identity cannot write or read outside gold (D-003); `mcp/guard.py` refuses anything but one SELECT on the four gold tables before it reaches BigQuery. A guard bypass still cannot write (live probe: `CREATE TABLE` denied 5 of 5).
- **Cost and size caps.** Each query is billed at most 1 GB (`MAX_BYTES_BILLED`) with a 30-second timeout; at most 200 rows come back and the response says when it was cut.
- **Cite or refuse.** Every answer carries `source_keys`, or the tool returns refused, needs_clarification, no_data or error with a reason (`mcp/tools/contract.py`).
- **Planted text in the wiki.** Wiki sections that look like instructions to the model are withheld and named, not returned (threat model row T-08). If you add wiki pages, run `python -m pytest -q mcp/tests/test_security.py`; it checks that every real wiki section passes the detector.
- **Errors stay internal.** Driver errors reach the client as a fixed plain reason; detail goes to the local server log only, which git ignores.
- **What it does not cover.** No network transport or caller sign-in (stdio on one machine), no forecasts, no single buildings or people, US areas only. The full list, with the test behind each row, is in [threat_model.md](threat_model.md); who decided what, and why, is in `docs/DECISIONS.md` and [decisions.md](decisions.md).

## Known open gaps

Two rows of the threat model are open on 2026-10-13. Each has a strict expected-failure test in `mcp/tests/test_security_w2.py`, so the suite fails loudly once someone fixes it and forgets to update the row.

- **T-09:** text values in returned rows (for example a metro name) are not checked for instruction-like text the way wiki sections are. Gold strings come from public files, which lowers the risk but does not remove it.
- **T-15:** rows are capped at 200, but the size of the response is not, so a query that builds very long strings can still send a large answer.

Before wider use, fix both in `mcp/tools/query_gold.py` and update the threat model in the same change.

## Rollout steps

1. **One person, one week.** Set up as above, run the qa pack's five samples and the full eval pack in fresh chats, and record results in a copy of `packs/eval/results.md`.
2. **Agree the bar.** Decide the pass rate the team needs on the eval pack and which rows must never fail (the refusal rows E09, E10, E19, E20, E27, E28, E38 and the clarification rows E08, E26 are the natural floor). Write the decision down with who made it.
3. **Pilot group.** Three to five analysts use the qa pack for real questions for two weeks. Each wrong or unsourced answer becomes a new golden-set row, approved by a person.
4. **Fix through the loop only.** Changes to the prompt, guardrail, tools or wiki go through `packs/improve/PACK.md`: one failed row per case, at most 3 fix attempts, ship only with no regressions, otherwise `needs_review`.
5. **Widen.** Add users once the agreed bar holds on two runs in a row and T-09 and T-15 are closed. Keep the Stop hook and CI (`.github/workflows/ci.yml`) running the tests and pack check on every change.

## How to measure success

- **Eval pass rate** on `packs/eval/questions.md`, reported as k of n with every failed id, the way `packs/eval/results.md` does. The first run (2026-10-13) passed 39 of 39 run rows, with E09 not run live; it was not blind, because the answerer had seen the expected answers. A blind run in fresh chats is the number to trust.
- **Refusal correctness:** refusal and clarification rows still pass after every change (a fix that makes the model answer more must not make it answer what it should refuse).
- **Citation correctness:** every cited source key exists and was returned by a tool in the same call.
- **Improvement loop outcomes:** cases ending `shipped`, `flaky_not_reproduced` and `needs_review` (`packs/improve/PACK.md`). Many `needs_review` cases mean the cause of failures is not understood.
- **Safety checks stay green:** `python -m pytest -q` and `python scripts/check_packs.py` pass; the two open-gap tests flip only when their fixes land.

# Rental Insights

Rental Insights is a data and AI system built on public US rental housing data: Zillow rent and
home value indexes (ZORI and ZHVI), HUD Fair Market Rents and Census ACS income figures. It loads
the sources into BigQuery, models them with dbt into tested bronze, silver and gold layers, and
serves the gold tables to an AI assistant through an MCP server that answers with cited figures or
refuses. A guardrail checks every model-written SQL statement before it runs, the query identity is
read-only and limited to gold, and a 40-question evaluation set measures how the assistant behaves.

This repository is a cleaned public copy of the code. It runs fully offline on a Parquet snapshot of
the gold tables, so no cloud account or credentials are needed.

Built by Patrick Hancock ([patrick-hancock.github.io](https://patrick-hancock.github.io)).

## Run it offline

Python 3.12 with the pinned `requirements.txt` (`pywin32` is only needed on Windows):

```bash
python -m pip install -r requirements.txt
RI_BACKEND=duckdb python -m pytest -q
```

`RI_BACKEND=duckdb` points the MCP server's `query_gold` tool at DuckDB over `snapshot/` instead of
BigQuery. The same switch starts the server itself offline: `RI_BACKEND=duckdb python mcp/server.py`.
Tests that need live BigQuery are skipped unless `RI_LIVE=1` is set.

## What to read first

- [System card](wiki/system_card.md): what the MCP server does, its guardrails, evaluation results and known limits.
- [Architecture](wiki/architecture.md), [KPIs](wiki/kpis.md), [data dictionary](wiki/data_dictionary.md)
  and [threat model](wiki/threat_model.md).
- [Decisions](wiki/decisions.md) and [runbooks](wiki/runbooks.md).

## Layout

- `ingest/`: loads the source files into the bronze layer (the files themselves are not included).
- `models/`, `macros/`, `seeds/`, `tests/`: the dbt project (silver and gold models, data tests).
- `mcp/`: the MCP server, its SQL guardrail, the two query back ends and the offline test suite.
- `snapshot/`: the gold tables as Parquet, with a manifest of row counts checked against BigQuery.
- `packs/`: runnable prompt packs, including the evaluation questions and published results.
- `synthetic/`: a made-up property portfolio for budget-versus-actual analysis. No row is real.
- `powerbi/`: the Power BI project definition over the gold tables.
- `scripts/`: data quality, dictionary, pack and handoff checks, the snapshot export and the probes.
- `reports/`: the data quality report for the gold tables.

## About this copy

This is a cleaned code copy with fresh history. Left out: the raw source files, run logs, internal
planning and progress notes, the public project page and the tests and scripts that build it, and
local tool settings. Some files cite internal decision and open item numbers (such as D-003 or
OI-237) and paths under `docs/` from the original project log, which is not included. Nothing here
sends data anywhere.

Data Provided by Zillow Group. Zillow figures in `snapshot/` and in the reports are derived from
Zillow's public research data (ZORI and ZHVI).

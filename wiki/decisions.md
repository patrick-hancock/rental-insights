# Decisions

## D-001 (2026-10-13) Claude Dashboard over BigQuery: signed-out sharing test (C2.T1)

**Result: opens = no.** The signed-out viewer sees only the page frame, not the tile.

What was tested:
- A test Claude Dashboard, "Rental Affordability (C2.T1 test)" (https://claude.ai/artifact/AHQxMaAC4rD5zChEhxV1Ta). It has one tile from a live query on the Google Cloud BigQuery connector (`execute_sql_readonly`, project rental-insights-511513), reading `gold.fct_cbsa_affordability`.
- The tile shows the number of metro and micro areas (CBSAs) where at least half of renter households are rent-burdened: **323 of 935**.
- Spot-check: the stored query run through the connector gave 935 / 323. A separate count of all 935 rows in Python with the local `google-cloud-bigquery` client also gave 323.
- Signed in, Patrick confirmed the tile renders.
- Sharing: Patrick set the Share menu to "anyone with a link" and opened the link in an incognito window, signed out. The page frame loaded as "Read-only". The body said "Nothing on this dashboard yet", with the banner "Sign in to see this artifact's data". No tile and no number were shown.

Why: the dashboard keeps its page and dataset definitions in the artifact's database, and live queries run on each reader's own connector. A signed-out reader has neither, so the dashboard needs a login. This hits the replan trigger in the task graph ("sharing needs a login").

Who decided: Claude built the dashboard and ran the spot-check. Patrick ran the incognito test and reported the result. D-002 below settles the public-viewing replacement.

## D-002 (2026-10-13) Public dashboard on GitHub Pages; Claude Dashboard kept as the signed-in demo

Decision: the public sees a static site on GitHub Pages, built from numbers exported from the gold tables. The site goes in a **separate, small public repo** that holds only the built site. `rental-insights` stays private. The Claude Dashboard from D-001 stays as the live, signed-in demo for screenshots, the walkthrough video and interviews.

Why:
- D-001 showed the Claude Dashboard needs a sign-in.
- GitHub Pages is free for public repos on GitHub Free. A private source repo needs a paid plan. Limits are a 1 GB site and a soft 100 GB/month of traffic (GitHub Docs, "GitHub Pages limits", read 2026-10-13).
- A static snapshot keeps working after the BigQuery sandbox tables expire around 2026-12-12 (OI-173).

Before the site goes public:
- Patrick reads Zillow's terms (OI-165).
- Patrick gives a separate yes to create the public repo, under the rule that new or public repos need approval each time.

Who decided: Claude proposed the separate site repo and keeping both. Patrick asked about GitHub Pages and approved both on 2026-10-13.

## D-003 (2026-10-13) MCP queries run as a read-only service account, limited to gold (C3.T2)

Decision: the MCP server runs its BigQuery queries as the service account `ri-reader` (in project `rental-insights-511513`), which Patrick's login impersonates, so no key file exists. It has two roles: BigQuery Job User on the project (it can run queries but read no data) and BigQuery Data Viewer on the `gold` dataset only. The SQL guardrail (`mcp/guard.py`) is the second wall, not the only one.

Evidence: `scripts/probe_readonly.py --runs 5` (run 91abe955, 2026-10-13) exited 0:
- gold read: allowed 5 of 5
- `CREATE TABLE` in gold: denied 5 of 5
- silver read: denied 5 of 5
- leftover probe tables: 0

The first run, a few minutes after the grants, failed before any query ran (`iam.serviceAccounts.getAccessToken` denied). That fits IAM changes taking minutes to apply. The run 3 minutes later passed.

Why: the nl-to-sql-safety rule that the executing identity must be read-only. Patrick's own login owns the project and built gold, so it can write.

Who decided: Claude proposed the impersonated reader account. Patrick approved it and ran the gcloud and bq setup commands on 2026-10-13.

## D-004 (2026-10-13) Public code mirror; replaces the "rental-insights stays private" part of D-002

Decision: the code is published as a **cleaned public mirror**, a second public repo with fresh history built from an allowlist (`mcp/`, `models/`, `tests/`, `packs/`, `wiki/` and CI). It has no data, no logs, no personal paths and no secrets, and it runs on a DuckDB snapshot of gold, so a reader needs no BigQuery project. `rental-insights` stays private as the working repo. The rest of D-002 stands: the static site on GitHub Pages, now served at Patrick's custom domain (C7.T5), and the Claude Dashboard as the signed-in demo.

Why:
- D-002 kept the repo private because Pages is free only for public repos. Keeping the code secret was never the reason.
- Reviewers of AI and data work judge the code, tests and evals. A private repo hides the guardrail, the dbt tests and the security tests.
- A fresh-history mirror avoids publishing old logs or paths that may be in this repo's history.

Before the mirror goes public:
- Patrick reads Zillow's terms (OI-165).
- Patrick gives a separate yes to create the mirror repo.
- `scripts/build_mirror.py --check` exits 0 (C7.T4). Its email check will flag the service-account address in D-003 above; decide at C7.T4 whether to redact it in the mirror.

Who decided: Claude proposed the cleaned mirror. Patrick approved it on 2026-10-13, in the portfolio structure review (Portfolio Plan 2026-10-12).

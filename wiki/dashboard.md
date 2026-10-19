# Dashboards: static site and Claude Dashboard

Two front ends over the same gold numbers (D-002): a static site in `site/` for the public (published through the portfolio site at https://patrick-hancock.github.io/rental-insights/ in C7.T3, with the credit line "Data Provided by Zillow Group"), and the signed-in Claude Dashboard demo (C2.T5, below).

## Static site (C2.T3)

**Build:** `python scripts/export_site_data.py` writes `site/data/*.json` from gold as the read-only `ri-reader` account; the pages read only those files. **Preview:** `python -m http.server 8765 --directory site`, then open http://localhost:8765. **Check:** `python scripts/spot_check_kpis.py`.

On 2026-10-19 (C7.T2) the three pages were joined into one page, `site/index.html`, with a section for each and an in-page jump nav, on the portfolio's shared stylesheet (dark only). The table lists the sections.

| Section | Location | KPIs | Charts | Table view |
|---|---|---|---|---|
| Rent trends | `site/index.html#trends` | K1, K2, K3 | median typical rent by month, 2015-01 to 2026-08 (line, crosshair hover) | 140 months; 20 largest metros |
| Affordability | `site/index.html#affordability` | K4, K5, K6, K7 | top 15 metros by rent-burdened share (bars, 50% line); ZORI / FMR ratio histogram (1.0 line) | 15 metros; 20 largest metros' ratio |
| Geography | `site/index.html#geography` | K8 | share of each state's areas with most renters burdened (45 states with 5+ areas) | 52 states and territories |

### Spot-check log
| Date | Page | Value on the site | SQL on gold | Result |
|---|---|---|---|---|
| 2026-10-13 | Geography | K8: 323 CBSAs with rent_burdened_share >= 0.5 | 323 | match |
| 2026-10-13 | Rent trends | K1: New York, NY, 2026-08-31: 3614.99907 | 3614.999069621115 | match at 6 decimals |
| 2026-10-13 | Affordability | K7: New York-Newark-Jersey City, NY-NJ: 1.32709 | 1.327090044839406 | match at 6 decimals |

`spot_check_kpis.py` exited 0 (3 of 3). A copy of the data with K8 changed to 322 made it exit 1.

### Browser checks (2026-10-13, local server, built-in browser; before the C7.T2 merge, when the site had three pages and a light mode)
- All 3 pages render with 0 error panels; table bodies hold 140 and 20 rows (trends), 15 and 20 (affordability), 52 (geography).
- Phone width (375 px): no horizontal scroll (scroll width 375); charts draw at the container width, so axis text stays 12 px; long metro names are shortened with an ellipsis and appear in full in the table and tooltip.
- Light and dark mode both render; dark uses its own validated steps (series blue #3987e5 on #1a1a19).
- Hover: bar tooltip shows the metro, rent-burdened and severely burdened shares; the line chart's crosshair shows month, metro count and median rent.
- Fixed during the check: a table-building bug (`append` returns nothing), chart text shrinking on phones, odd axis ticks (now 0 to 80%), and the 50% reference line hidden behind bars.

### Caveats shown on the pages
- The metro set grows over time, so the trend line is a broad trend, not a like-for-like index.
- ZORI covers all unit sizes while FMR is 2-bedroom; micro areas have no FMR in this data.
- States are counted by the first state in a CBSA name; 59 CBSAs cross state lines.
- No single metro's rent change is named on the site (OI-171: check the Abilene and Auburn jumps first).

## Claude Dashboard demo (C2.T5)

**Where:** https://claude.ai/artifact/AHQxMaAC4rD5zChEhxV1Ta, the D-001 test dashboard, renamed "Rental insights (signed-in demo)" (Claude's addition, proposed). **Sharing:** anyone with the link; a signed-out viewer sees only the page frame (D-001), so it is a signed-in demo for screenshots, the walkthrough and interviews. Each live query runs with the viewer's own Google Cloud BigQuery connector access to project rental-insights-511513.

Three tabs, the same pages as the site, each with one KPI tile. Every figure comes from a live query on the Google Cloud BigQuery connector (`execute_sql_readonly`) against the gold tables:

| Tab | KPI tile | Dataset (query) | Supporting view |
|---|---|---|---|
| Rent trends | K1: New York, NY typical rent, latest month | `ny_latest` | line chart of New York ZORI by month (`ny_rent`, 140 months) |
| Affordability | K7: New York metro ZORI / 2-bedroom FMR | `afford_top20` | bars for the 20 most populous metro areas, 1.0 reference line |
| Geography | K8: areas where most renters are burdened | `burden` (from D-001) | table by state (`by_state`, 52 rows) |

### Spot-check log
| Date | Tab | Tile value (stored query run as saved) | Site or SQL on gold | Result |
|---|---|---|---|---|
| 2026-10-13 | Rent trends | K1: 3614.9990696211148 (2026-08-31), shown as $3,615 | site 3614.99907 | match at 6 decimals |
| 2026-10-13 | Affordability | K7: 1.3270900448394061, shown as 1.33 | site 1.32709 | match at 6 decimals |
| 2026-10-13 | Geography | K8: 323 of 935 | site 323 | match |

`by_state` returns 52 rows, the same count as the site's geography table.

### Browser check (2026-10-13, built-in browser, signed in as Patrick)
- All 3 tabs render: tiles show $3,615 (Aug 2026), 1.33 and 323 of 935; the line chart, the 20-bar chart with its 1.0 line, and the 52-row state table all draw.
- The dashboard's run report showed all 5 queries ok (rows 1, 140, 20, 1, 52) and one code error: tooltips called `replaceChildren` on a d3 selection. Fixed; after a reload both tooltips work on hover and the run report is empty (nothing failed or threw).

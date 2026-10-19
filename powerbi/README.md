# Power BI project: Rental Insights

**This folder is a Power BI Project (.pbip), not a .pbix.** A .pbix is a binary file that only Power BI Desktop writes, and Power BI Desktop is not installed on the machine where this was built (checked on 2026-10-13: no `PBIDesktop` command, no Microsoft Store package, no folder under Program Files, no uninstall entry). So the project was written as text files in the documented .pbip format: a TMDL semantic model and a report definition.

**It has not been opened in Power BI Desktop.** Nothing here has been loaded, refreshed or rendered. Treat it as a draft until the first open succeeds.

## Getting the .pbix

1. Install Power BI Desktop (Windows) and turn on the Power BI Project preview if your version still lists it under File > Options > Preview features (Power BI Project save option, and TMDL format).
2. Open `RentalInsights.pbip`.
3. When asked, sign in to Google BigQuery with your own Google account (Power BI keeps the credential in Desktop; no file here holds one). The account needs read access to the gold dataset.
4. Refresh, check the values in "Check after the first refresh" below, then use **File > Save as** and pick the `.pbix` type.

The report pages are the part most likely to need fixing, because the report layout format is less documented than TMDL. If they fail to load, open the model on its own (or start a new report connected to it) and rebuild the three pages from the measures; the semantic model is the main part.

## What is inside

| Path | What it is |
|---|---|
| `RentalInsights.pbip` | the file you open; points at the report |
| `RentalInsights.SemanticModel/definition/` | TMDL model: `expressions.tmdl` (parameters), `tables/*.tmdl` (4 tables with measures), `relationships.tmdl` |
| `RentalInsights.Report/` | report definition (`report.json`) bound to the model by relative path |
| `.gitignore` | keeps Desktop's local cache and settings out of git |

## Connection and parameters

Each table is imported from BigQuery with the Google BigQuery connector (`GoogleBigQuery.Database`), using two text parameters in `expressions.tmdl`:

- `BigQueryProject`: default `rental-insights-511513` (also the billing project, which the BigQuery sandbox needs).
- `BigQueryDataset`: default `gold`.

To point it at your own build, change both in Desktop under Transform data > Manage parameters. No credentials, keys or tokens are stored in any file.

## Model

Kept small: only the gold columns the KPIs need (definitions in `wiki/kpis.md`, columns in `wiki/data_dictionary.md`).

| Table | Rows kept | Columns |
|---|---|---|
| `fct_metro_month` | months with a ZORI value only | zillow_region_id, month_end, zori, zori_yoy, gross_rent_yield |
| `fct_cbsa_affordability` | all 935 CBSAs | cbsa_code, cbsa_name, cbsa_type, population, the three burden and income shares, hud_fmr_2br_weighted, latest_zori, zori_to_fmr_2br, plus a calculated `first_state` |
| `dim_metro` | all | zillow_region_id, metro_name, state_code, size_rank, cbsa_code, cbsa_type |
| `dim_date` | all | month_end, year, year_month |

Relationships: `fct_metro_month` to `dim_metro` on zillow_region_id and to `dim_date` on month_end (many to one). `fct_cbsa_affordability` stands alone, as in the site.

Measures (all medians are exact DAX `MEDIAN`, across areas, as in `wiki/kpis.md`): K1, K2 and K3 per month and for the latest month with a ZORI value; K4, K5, K6 and K7 medians across CBSAs; K7 counts (areas with both values, areas above 1); K8 count of CBSAs with rent_burdened_share of 0.5 or more; CBSA count. `first_state` takes the first state after the comma in the CBSA name, the same rule as the site (59 CBSAs list several states).

## Report pages

The same three pages as the static site (`wiki/dashboard.md`):

- **Rent trends:** cards K1, K2, K3 and metro count for the latest month; line chart of K1 by month.
- **Affordability:** cards K4, K5, K6, K7; table of CBSAs with their shares and market-rent-to-FMR ratio.
- **Geography:** cards K8, CBSA count, K7 areas above FMR; table of K8 and CBSA count by first state.

## Check after the first refresh

Compare with values measured by SQL on gold on 2026-10-13 (not yet seen in Power BI):

| Measure | Expected | Source |
|---|---|---|
| K8 Areas where most renters are burdened / CBSA count | 323 / 935 | `wiki/kpis.md` K8, `wiki/dashboard.md` spot-check log |
| K1 Median typical rent, latest month | about 1,388 (exact median 1387.79, month 2026-08-31) | `packs/eval/results.md` E01 |
| Metros with typical rent, latest month | 749 | `packs/eval/results.md` E01 |
| K2 Median rent change YoY, latest month | 3.4% (0.0335694) | `packs/eval/results.md` E24 |
| K7 Areas with market rent above FMR / with both values | 299 / 381 | `packs/eval/results.md` E06 |
| K3, K4, K6, K7 medians | close to 5.92%, 47.4%, 18.2%, 1.08 | `wiki/kpis.md` (approximate medians, so small differences are expected) |

If the data has been rebuilt since 2026-10-13, the numbers can move; rerun the SQL first.

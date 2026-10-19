# Data quality report: gold tables

Generated 2026-10-13 10:29 by `scripts/dq_report.py` from BigQuery dataset `rental-insights-511513.gold`. Rerun the script after every `dbt build`; `--check` fails when this file is stale.

## dim_date

- Rows: 320
- Key: `month_end`
- Duplicate keys: 0

| Column | Nulls | Null % | Why |
|---|---:|---:|---|
| month_end | 0 | 0.0 |  |
| month_start | 0 | 0.0 |  |
| year | 0 | 0.0 |  |
| quarter | 0 | 0.0 |  |
| month | 0 | 0.0 |  |
| year_month | 0 | 0.0 |  |

## dim_metro

- Rows: 910
- Key: `zillow_region_id`
- Duplicate keys: 0

| Column | Nulls | Null % | Why |
|---|---:|---:|---|
| zillow_region_id | 0 | 0.0 |  |
| metro_name | 0 | 0.0 |  |
| state_code | 0 | 0.0 | Zillow leaves the state blank for some metros. |
| size_rank | 0 | 0.0 |  |
| cbsa_code | 43 | 4.7 | Zillow metro with no CBSA name match (43 of 910 on 2026-10-13, all size rank 275 or lower). |
| match_method | 43 | 4.7 | Same rows as cbsa_code: no match. |
| cbsa_name | 43 | 4.7 | Same rows as cbsa_code: no match. |
| cbsa_type | 43 | 4.7 | Same rows as cbsa_code: no match. |
| population | 43 | 4.7 | Same rows as cbsa_code: no match. |

## fct_cbsa_affordability

- Rows: 935
- Key: `cbsa_code`
- Duplicate keys: 0

| Column | Nulls | Null % | Why |
|---|---:|---:|---|
| cbsa_code | 0 | 0.0 |  |
| cbsa_name | 0 | 0.0 |  |
| cbsa_type | 0 | 0.0 |  |
| population | 0 | 0.0 |  |
| median_household_income | 0 | 0.0 |  |
| median_gross_rent | 0 | 0.0 |  |
| median_home_value | 0 | 0.0 |  |
| renter_share | 0 | 0.0 |  |
| rent_burdened_share | 0 | 0.0 |  |
| severely_rent_burdened_share | 0 | 0.0 |  |
| rent_to_income | 0 | 0.0 |  |
| hud_fmr_2br_weighted | 542 | 58.0 | HUD gives a CBSA code only for metro areas; micro areas are null. |
| hud_county_count | 542 | 58.0 | Same rows as hud_fmr_2br_weighted. |
| zori_month | 213 | 22.8 | Same rows as latest_zori. |
| latest_zori | 213 | 22.8 | CBSA with no matched Zillow metro that has rent data. |
| zori_to_fmr_2br | 554 | 59.3 | Needs both a matched Zillow rent and a HUD FMR. |

## fct_metro_month

- Rows: 237,686
- Key: `metro_month_key`
- Duplicate keys: 0

| Column | Nulls | Null % | Why |
|---|---:|---:|---|
| metro_month_key | 0 | 0.0 |  |
| zillow_region_id | 0 | 0.0 |  |
| month_end | 0 | 0.0 |  |
| zori | 184,377 | 77.6 | ZORI starts 2015-01 and covers fewer metros than ZHVI. |
| zhvi | 872 | 0.4 | Metro-months with a rent value but no home value. |
| zori_yoy | 192,333 | 80.9 | No ZORI value this month or 12 months earlier. |
| zhvi_yoy | 12,032 | 5.1 | No ZHVI value this month or 12 months earlier. |
| gross_rent_yield | 185,249 | 77.9 | Needs both ZORI and ZHVI in the same month. |

## Outliers to review

Metro-months where rent moved more than 40% in a year (largest 10):

| Metro | Month | ZORI YoY | Size rank |
|---|---|---:|---:|
| Auburn, AL | 2016-04-30 | 0.5 | 253 |
| Abilene, TX | 2026-04-30 | 0.407 | 251 |
| Abilene, TX | 2026-05-31 | 0.407 | 251 |
| Abilene, TX | 2026-06-30 | 0.402 | 251 |

# Data dictionary: gold tables

Every column of the four gold tables in `rental-insights-511513.gold`. Types come from BigQuery; descriptions are written by hand. `scripts/check_dictionary.py` fails when a gold column is missing here, has the wrong type or has no description. KPI formulas built on these columns are in [kpis.md](kpis.md).

## fct_metro_month

**Grain:** One row per Zillow metro per month where ZORI or ZHVI has a value.

**Model:** `models/gold/fct_metro_month.sql`

| Column | Type | Description |
|---|---|---|
| `metro_month_key` | STRING | Primary key: zillow_region_id, a hyphen, and the month as YYYYMM (for example 394297-200902). |
| `zillow_region_id` | INTEGER | Zillow's metro id; joins to dim_metro. |
| `month_end` | DATE | Last day of the month the index values describe; joins to dim_date. |
| `zori` | FLOAT | Zillow Observed Rent Index, smoothed, not seasonally adjusted, in US dollars per month; single-family, condo and multifamily rentals (Zillow file Metro_zori_uc_sfrcondomfr_sm_month). NULL before the metro's series starts (earliest 2015-01). |
| `zhvi` | FLOAT | Zillow Home Value Index for single-family homes and condos, middle tier (33rd to 67th percentile), smoothed and seasonally adjusted, in US dollars (Zillow file Metro_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month). Starts 2000-01. |
| `zori_yoy` | FLOAT | Year-over-year change in zori: zori / zori 12 months earlier - 1 (0.034 = +3.4%). NULL when the month a year earlier has no value (KPI K2). |
| `zhvi_yoy` | FLOAT | Year-over-year change in zhvi, same method as zori_yoy. |
| `gross_rent_yield` | FLOAT | zori * 12 / zhvi: a year of typical rent as a share of typical home value (0.059 = 5.9%). Rough; ignores costs and vacancy (KPI K3). |

## fct_cbsa_affordability

**Grain:** One row per CBSA with ACS 2024 rent and income, HUD FY2027 FMR and the latest matched Zillow rent.

**Model:** `models/gold/fct_cbsa_affordability.sql`

| Column | Type | Description |
|---|---|---|
| `cbsa_code` | STRING | Primary key: 5-digit Census CBSA code, stored as text. |
| `cbsa_name` | STRING | Census CBSA name, ending in 'Metro Area' or 'Micro Area'; states follow the comma (59 list several, as in 'NY-NJ'). |
| `cbsa_type` | STRING | 'metro' (393 rows) or 'micro' (542 rows), from the name's ending. |
| `population` | INTEGER | Total population, ACS 2024 5-year (B01003_001E). |
| `median_household_income` | INTEGER | Median household income in the past 12 months, US dollars, ACS 2024 5-year (B19013_001E). NULL where ACS withholds it. |
| `median_gross_rent` | INTEGER | Median gross rent (contract rent plus utilities) per month, US dollars, ACS 2024 5-year (B25064_001E). |
| `median_home_value` | INTEGER | Median value of owner-occupied homes, US dollars, ACS 2024 5-year (B25077_001E). |
| `renter_share` | FLOAT | Renter-occupied units / occupied units (B25003_003E / B25003_001E). |
| `rent_burdened_share` | FLOAT | Renter households paying 30% or more of income on gross rent / renter households with the ratio computed (B25070). HUD's cost-burden line (KPI K4). |
| `severely_rent_burdened_share` | FLOAT | Renter households paying 50% or more of income on gross rent, same denominator as rent_burdened_share (KPI K5). |
| `rent_to_income` | FLOAT | median_gross_rent * 12 / median_household_income; an area-level ratio of two medians, not a household figure (KPI K6). |
| `hud_fmr_2br_weighted` | FLOAT | HUD FY2027 2-bedroom Fair Market Rent, averaged over the CBSA's counties weighted by 2024 population, US dollars per month. Filled for all 393 metro CBSAs, NULL for micro areas. |
| `hud_county_count` | INTEGER | Number of HUD county rows averaged into hud_fmr_2br_weighted; NULL for micro areas. |
| `zori_month` | DATE | Month of latest_zori: the latest month with a ZORI value for the matched Zillow metro (2026-08-31 for every filled row on 2026-10-13). |
| `latest_zori` | FLOAT | Latest ZORI (US dollars per month) of the Zillow metro matched to this CBSA through int_zillow_cbsa_xwalk; NULL when no metro matched. |
| `zori_to_fmr_2br` | FLOAT | latest_zori / hud_fmr_2br_weighted. Above 1 means typical market rent exceeds the 2-bedroom FMR. ZORI covers all unit sizes, so the comparison is approximate (KPI K7). |

## dim_metro

**Grain:** One row per Zillow metro, with its Census CBSA where one matched.

**Model:** `models/gold/dim_metro.sql`

| Column | Type | Description |
|---|---|---|
| `zillow_region_id` | INTEGER | Primary key: Zillow's metro id. |
| `metro_name` | STRING | Zillow's metro name: first principal city and first state, as in 'New York, NY'. |
| `state_code` | STRING | Two-letter state of the metro, from Zillow. |
| `size_rank` | INTEGER | Zillow's size rank of the metro (smaller is larger; the national row is not in gold). |
| `cbsa_code` | STRING | Census CBSA matched to this metro; NULL when no match (867 of 910 matched on 2026-10-13). |
| `match_method` | STRING | How cbsa_code was found: 'name' (exact match on 'First City, ST') or 'override' (seeds/zillow_cbsa_overrides.csv). NULL when unmatched. |
| `cbsa_name` | STRING | Census name of the matched CBSA; NULL when unmatched. |
| `cbsa_type` | STRING | 'metro' or 'micro' for the matched CBSA; NULL when unmatched. |
| `population` | INTEGER | ACS 2024 5-year population of the matched CBSA; NULL when unmatched. |

## dim_date

**Grain:** One row per calendar month (month-end date) covered by any Zillow series.

**Model:** `models/gold/dim_date.sql`

| Column | Type | Description |
|---|---|---|
| `month_end` | DATE | Primary key: last day of the month. |
| `month_start` | DATE | First day of the same month. |
| `year` | INTEGER | Calendar year. |
| `quarter` | INTEGER | Calendar quarter, 1 to 4. |
| `month` | INTEGER | Month number, 1 to 12. |
| `year_month` | STRING | Month as text, YYYY-MM. |

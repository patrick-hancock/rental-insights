# KPI definitions (C2.T2)

Eight KPIs across the three pages of the static site and the Claude Dashboard (C2.T3, C2.T5). Each entry gives the formula, the grain, the source gold table and column, coverage, and a reference value measured on 2026-10-13 against `rental-insights-511513.gold`.

Reference values marked "approx. median" come from BigQuery `APPROX_QUANTILES`. The spot-check script in C2.T3 must recompute any value it compares with an exact method, not reuse these.

Gold has no United States total row, so there is no national headline. Headlines are counts or medians across areas, and each entry says which.

## Page 1: Rent trends (Zillow, metro by month)

### K1. Typical rent (ZORI)
- **Formula:** `fct_metro_month.zori`, Zillow Observed Rent Index in dollars per month. Headline: median across metros in the latest month with any ZORI.
- **Grain:** one Zillow metro per month-end.
- **Source:** `gold.fct_metro_month.zori`, joined to `gold.dim_metro` for names.
- **Coverage:** ZORI starts 2015-01. Latest month 2026-08-31, 749 metros with a value.
- **Reference:** approx. median $1,388 per month across the 749 metros (2026-08-31).

### K2. Rent change, year over year
- **Formula:** `zori / zori 12 months earlier - 1` (`fct_metro_month.zori_yoy`). A missing prior month gives no value, never a shifted lag.
- **Grain:** one Zillow metro per month-end.
- **Source:** `gold.fct_metro_month.zori_yoy`.
- **Coverage:** 602 of the 749 metros have a value for 2026-08-31; the rest started their series less than a year earlier.
- **Reference:** approx. median +3.36%; 27 metros fell year over year (2026-08-31).
- **Gotcha:** some metros show jumps of 40% to 50% (Abilene TX 2026, Auburn AL 2016; OI-171). Check them before any page names a single metro's change.

### K3. Gross rent yield
- **Formula:** `zori * 12 / zhvi` (`fct_metro_month.gross_rent_yield`): a year of typical rent as a share of the typical home value. A rough indicator; it ignores costs and vacancy.
- **Grain:** one Zillow metro per month-end.
- **Source:** `gold.fct_metro_month.gross_rent_yield`.
- **Coverage:** 733 of 749 metros for 2026-08-31 (needs both ZORI and ZHVI).
- **Reference:** approx. median 5.92% (2026-08-31).

## Page 2: Affordability (ACS 2024, HUD FY2027)

### K4. Rent-burdened share
- **Formula:** renter households paying 30% or more of income on rent, divided by renter households with the ratio computed (`fct_cbsa_affordability.rent_burdened_share`). 30% is HUD's cost-burden line.
- **Grain:** one CBSA (Census metro or micro area).
- **Source:** `gold.fct_cbsa_affordability.rent_burdened_share` (from ACS 2024 5-year).
- **Coverage:** 935 of 935 CBSAs (393 metro, 542 micro).
- **Reference:** approx. median 47.4% across the 935 CBSAs.

### K5. Severely rent-burdened share
- **Formula:** renter households paying 50% or more of income on rent, same denominator as K4 (`severely_rent_burdened_share`).
- **Grain:** one CBSA.
- **Source:** `gold.fct_cbsa_affordability.severely_rent_burdened_share`.
- **Coverage:** 935 of 935.

### K6. Rent to income
- **Formula:** `median_gross_rent * 12 / median_household_income` (`rent_to_income`). Both are medians over different households (renters versus all households), so this is an area-level ratio, not any household's burden.
- **Grain:** one CBSA.
- **Source:** `gold.fct_cbsa_affordability.rent_to_income`.
- **Coverage:** 935 of 935.
- **Reference:** approx. median 18.2%.

### K7. Market rent versus Fair Market Rent
- **Formula:** latest matched ZORI divided by the population-weighted HUD FY2027 2-bedroom FMR (`zori_to_fmr_2br`). Above 1 means typical market rent is higher than the FMR that housing vouchers are based on.
- **Grain:** one CBSA.
- **Source:** `gold.fct_cbsa_affordability.zori_to_fmr_2br`, with `latest_zori`, `zori_month` and `hud_fmr_2br_weighted`.
- **Coverage:** 381 CBSAs, all metro. The weighted FMR is filled for all 393 metro CBSAs and for none of the 542 micro areas (341 micro areas do have a ZORI). 12 metro CBSAs have no matched Zillow metro. Every `zori_month` is 2026-08-31.
- **Reference:** approx. median 1.08.
- **Gotcha:** ZORI is all unit sizes and FMR is 2-bedroom, so the ratio compares close but not identical things. Pages must say so next to the number.

## Page 3: Geography

### K8. Areas where most renters are rent-burdened
- **Formula:** count of CBSAs with `rent_burdened_share >= 0.5`, out of all CBSAs; shown by state and by metro or micro type.
- **Grain:** one CBSA, counted.
- **Source:** `gold.fct_cbsa_affordability.rent_burdened_share` and `cbsa_type`. The state comes from the CBSA name's state suffix.
- **Coverage:** 935 of 935.
- **Reference:** **323 of 935**. This is the D-001 tile value, matched by both the BigQuery connector and the local client on 2026-10-13. It is the first spot-check value for C2.T3.
- **Gotcha:** 59 CBSAs cross state lines and list several states (for example "NY-NJ"). The page counts them once, under the first state named, and says so.

## Spot-check set for C2.T3
`scripts/spot_check_kpis.py` compares three values from `site/data/*.json` with exact SQL on gold: K8 (count, expect 323 while the data is unchanged), K1 for one named metro and month, and K7 for one named CBSA.

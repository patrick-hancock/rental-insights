-- One row per CBSA: ACS 2024 rent and income, HUD FY2027 Fair Market Rent, and the latest Zillow rent where matched.
with hud as (
    -- HUD sets FMRs per HUD area; a CBSA can hold several, so weight the counties by 2024 population.
    select
        cbsa_code,
        safe_divide(sum(fmr_2br * population_2024), sum(population_2024)) as hud_fmr_2br_weighted,
        count(*) as hud_county_count
    from {{ ref('stg_hud_fmr_county') }}
    where cbsa_code is not null
    group by cbsa_code
),

latest_zori as (
    select x.cbsa_code, f.month_end as zori_month, f.zori
    from {{ ref('fct_metro_month') }} f
    join {{ ref('int_zillow_cbsa_xwalk') }} x using (zillow_region_id)
    where x.cbsa_code is not null and f.zori is not null
    qualify row_number() over (partition by x.cbsa_code order by f.month_end desc) = 1
)

select
    a.cbsa_code,
    a.cbsa_name,
    a.cbsa_type,
    a.population,
    a.median_household_income,
    a.median_gross_rent,
    a.median_home_value,
    safe_divide(a.renter_occupied_units, a.occupied_units) as renter_share,
    -- Cost-burdened renters pay 30% or more of income on rent (HUD's definition); "not computed" households are excluded.
    safe_divide(
        a.renter_hh_30_35pct + a.renter_hh_35_40pct + a.renter_hh_40_50pct + a.renter_hh_50pct_plus,
        a.renter_hh_total - a.renter_hh_not_computed
    ) as rent_burdened_share,
    safe_divide(a.renter_hh_50pct_plus, a.renter_hh_total - a.renter_hh_not_computed) as severely_rent_burdened_share,
    safe_divide(a.median_gross_rent * 12, a.median_household_income) as rent_to_income,
    h.hud_fmr_2br_weighted,
    h.hud_county_count,
    z.zori_month,
    z.zori as latest_zori,
    safe_divide(z.zori, h.hud_fmr_2br_weighted) as zori_to_fmr_2br
from {{ ref('stg_acs_cbsa') }} a
left join hud h using (cbsa_code)
left join latest_zori z using (cbsa_code)

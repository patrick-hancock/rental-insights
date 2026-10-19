-- SYNTHETIC: built only from made-up seeds (synthetic/README.md).
-- Budget vs actual per property per month. Sign convention: a positive variance is favorable
-- (more revenue, or less expense, than budget).
-- Rent variance splits exactly into two effects:
--   occupancy_effect = (actual units - budget units) x budget rent
--   rate_effect      = (actual rent - budget rent) x actual units
{{ config(schema='synthetic', materialized='table') }}

with joined as (
    select
        b.property_id,
        b.month_end,
        b.fiscal_year,
        b.budget_occupied_units,
        a.occupied_units as actual_occupied_units,
        b.budget_avg_rent,
        a.avg_rent as actual_avg_rent,
        b.budget_occupied_units * b.budget_avg_rent as budget_rent_revenue,
        a.rent_revenue as actual_rent_revenue,
        b.budget_repairs_maintenance,
        a.repairs_maintenance as actual_repairs_maintenance,
        b.budget_utilities,
        a.utilities as actual_utilities,
        b.budget_payroll,
        a.payroll as actual_payroll,
        b.budget_taxes_insurance,
        a.taxes_insurance as actual_taxes_insurance,
        b.budget_repairs_maintenance + b.budget_utilities + b.budget_payroll + b.budget_taxes_insurance as budget_total_opex,
        a.total_opex as actual_total_opex,
        a.opex_notes
    from {{ ref('synthetic_budget_monthly') }} b
    join {{ ref('synthetic_actual_monthly') }} a using (property_id, month_end)
)

select
    *,
    actual_rent_revenue - budget_rent_revenue as rent_variance,
    (actual_occupied_units - budget_occupied_units) * budget_avg_rent as occupancy_effect,
    coalesce((actual_avg_rent - budget_avg_rent) * actual_occupied_units, 0) as rate_effect,
    budget_repairs_maintenance - actual_repairs_maintenance as repairs_maintenance_variance,
    budget_utilities - actual_utilities as utilities_variance,
    budget_payroll - actual_payroll as payroll_variance,
    budget_taxes_insurance - actual_taxes_insurance as taxes_insurance_variance,
    budget_total_opex - actual_total_opex as opex_variance,
    budget_rent_revenue - budget_total_opex as budget_noi,
    actual_rent_revenue - actual_total_opex as actual_noi,
    (actual_rent_revenue - actual_total_opex) - (budget_rent_revenue - budget_total_opex) as noi_variance,
    safe_divide((actual_rent_revenue - actual_total_opex) - (budget_rent_revenue - budget_total_opex),
                abs(budget_rent_revenue - budget_total_opex)) as noi_variance_pct
from joined

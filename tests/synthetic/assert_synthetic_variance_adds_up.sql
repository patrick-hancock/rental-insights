-- SYNTHETIC data check. Fails with one row per property-month where the variance pieces do not
-- add up (tolerance 1 cent, for numeric rounding): rate + occupancy effects must equal the rent
-- variance, and rent + opex variance must equal the NOI variance. Also fails if a budget month
-- has no variance row.
select property_id, month_end, 'effects do not sum to rent variance' as problem
from {{ ref('synthetic_variance_monthly') }}
where abs(occupancy_effect + rate_effect - rent_variance) > 0.01
union all
select property_id, month_end, 'rent + opex variance is not NOI variance'
from {{ ref('synthetic_variance_monthly') }}
where abs(rent_variance + opex_variance - noi_variance) > 0.01
union all
select b.property_id, b.month_end, 'budget month missing from variance'
from {{ ref('synthetic_budget_monthly') }} b
left join {{ ref('synthetic_variance_monthly') }} v using (property_id, month_end)
where v.property_id is null

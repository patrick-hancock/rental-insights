-- SYNTHETIC data check. Fails with one row per property-month that is missing from the budget
-- (every property needs all 24 months, Oct 2024 to Sep 2026) or that plans more occupied units
-- than the property has.
with months as (
    select last_day(m) as month_end
    from unnest(generate_date_array('2024-10-01', '2026-09-01', interval 1 month)) as m
)
select p.property_id, mo.month_end, 'missing' as problem
from {{ ref('synthetic_properties') }} p
cross join months mo
left join {{ ref('synthetic_budget_monthly') }} b
  on b.property_id = p.property_id and b.month_end = mo.month_end
where b.property_id is null
union all
select b.property_id, b.month_end, 'occupied above unit count'
from {{ ref('synthetic_budget_monthly') }} b
join {{ ref('synthetic_properties') }} p using (property_id)
where b.budget_occupied_units > p.unit_count

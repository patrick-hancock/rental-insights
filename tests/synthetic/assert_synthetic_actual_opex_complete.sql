-- SYNTHETIC data check. Fails with one row per budget property-month and category that has no
-- actual opex row, or per actual row with no budget month. Budget and actuals must line up 1 to 1.
with expected as (
    select b.property_id, b.month_end, category
    from {{ ref('synthetic_budget_monthly') }} b
    cross join unnest(['repairs_maintenance', 'utilities', 'payroll', 'taxes_insurance']) as category
)
select coalesce(e.property_id, a.property_id) as property_id,
       coalesce(e.month_end, a.month_end) as month_end,
       coalesce(e.category, a.category) as category,
       if(a.property_id is null, 'no actual', 'no budget') as problem
from expected e
full outer join {{ ref('synthetic_actual_opex') }} a
  on a.property_id = e.property_id and a.month_end = e.month_end and a.category = e.category
where a.property_id is null or e.property_id is null

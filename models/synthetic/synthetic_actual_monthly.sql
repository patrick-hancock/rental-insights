-- SYNTHETIC: built only from made-up seeds (synthetic/README.md).
-- One row per property per month. Leases run whole months, so a lease that covers the month end
-- earned the full month's rent; occupied_units counts those leases.
{{ config(schema='synthetic', materialized='table') }}

with spine as (
    select property_id, month_end
    from {{ ref('synthetic_budget_monthly') }}
),

-- Fans out to one row per lease per month it covers, then rolls back up to property-month.
active_leases as (
    select s.property_id, s.month_end, l.monthly_rent
    from {{ ref('synthetic_leases') }} l
    join {{ ref('synthetic_units') }} u using (unit_id)
    join spine s
      on s.property_id = u.property_id
     and l.start_date <= s.month_end
     and l.end_date >= s.month_end
),

revenue as (
    select property_id, month_end, count(*) as occupied_units, sum(monthly_rent) as rent_revenue
    from active_leases
    group by property_id, month_end
),

opex as (
    select
        property_id,
        month_end,
        sum(if(category = 'repairs_maintenance', amount, 0)) as repairs_maintenance,
        sum(if(category = 'utilities', amount, 0)) as utilities,
        sum(if(category = 'payroll', amount, 0)) as payroll,
        sum(if(category = 'taxes_insurance', amount, 0)) as taxes_insurance,
        sum(amount) as total_opex,
        string_agg(nullif(note, ''), '; ') as opex_notes
    from {{ ref('synthetic_actual_opex') }}
    group by property_id, month_end
)

select
    s.property_id,
    s.month_end,
    p.unit_count,
    coalesce(r.occupied_units, 0) as occupied_units,
    coalesce(r.rent_revenue, 0) as rent_revenue,
    safe_divide(r.rent_revenue, r.occupied_units) as avg_rent,
    o.repairs_maintenance,
    o.utilities,
    o.payroll,
    o.taxes_insurance,
    o.total_opex,
    coalesce(r.rent_revenue, 0) - o.total_opex as noi,
    o.opex_notes
from spine s
join {{ ref('synthetic_properties') }} p using (property_id)
left join revenue r using (property_id, month_end)
left join opex o using (property_id, month_end)

-- SYNTHETIC data check. Fails with one row per property-month where more units are occupied than
-- the property has, which would mean the lease join fanned out or leases overlap.
select property_id, month_end, occupied_units, unit_count
from {{ ref('synthetic_actual_monthly') }}
where occupied_units > unit_count

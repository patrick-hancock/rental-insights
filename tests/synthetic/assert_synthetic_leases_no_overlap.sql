-- SYNTHETIC data check. Fails with one row per pair of leases on the same unit that overlap in time,
-- or per lease that ends before it starts. A unit can hold only one lease at a time.
select a.lease_id, b.lease_id as overlapping_lease_id, a.unit_id
from {{ ref('synthetic_leases') }} a
join {{ ref('synthetic_leases') }} b
  on a.unit_id = b.unit_id
 and a.lease_id < b.lease_id
 and a.start_date <= b.end_date
 and b.start_date <= a.end_date
union all
select lease_id, null, unit_id
from {{ ref('synthetic_leases') }}
where end_date < start_date

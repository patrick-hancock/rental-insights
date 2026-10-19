-- Fails if the Zillow-to-CBSA match rate drops below what was measured on 2026-10-13:
-- 867 of 910 metros (95.3%) overall, and 99 of 99 metros with size_rank 100 or better.
-- The floor of 0.95 leaves room for a few new small metros; any top-100 miss means a rename to add to the override seed.
with s as (
    select
        safe_divide(countif(cbsa_code is not null), count(*)) as match_rate,
        countif(cbsa_code is null and size_rank <= 100) as top100_unmatched
    from {{ ref('int_zillow_cbsa_xwalk') }}
)
select * from s where match_rate < 0.95 or top100_unmatched > 0

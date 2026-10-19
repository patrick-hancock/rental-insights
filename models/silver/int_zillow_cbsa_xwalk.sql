-- One row per Zillow metro, with the CBSA it matches by name (NULL when no CBSA name matches).
-- Matching is exact on "First City, ST"; see the match-rate test for how many metros match.
with zillow as (
    select distinct zillow_region_id, zillow_region_name, state_code, size_rank
    from (
        select zillow_region_id, zillow_region_name, state_code, size_rank from {{ ref('stg_zori_metro_month') }}
        union all
        select zillow_region_id, zillow_region_name, state_code, size_rank from {{ ref('stg_zhvi_metro_month') }}
    )
),

acs as (
    -- A name shared by two CBSAs would fan out the join, so ambiguous names are left unmatched.
    select zillow_style_name, any_value(cbsa_code) as cbsa_code
    from {{ ref('stg_acs_cbsa') }}
    group by zillow_style_name
    having count(*) = 1
)

select
    z.zillow_region_id,
    z.zillow_region_name,
    z.state_code,
    z.size_rank,
    coalesce(o.cbsa_code, a.cbsa_code) as cbsa_code,
    case when o.cbsa_code is not null then 'override' when a.cbsa_code is not null then 'name' end as match_method
from zillow z
left join acs a on a.zillow_style_name = z.zillow_region_name
-- Hand-checked fixes for renamed metros; each row in the seed says why.
left join {{ ref('zillow_cbsa_overrides') }} o on o.zillow_region_name = z.zillow_region_name

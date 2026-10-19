-- One row per Zillow metro, with its Census CBSA where one matched (see int_zillow_cbsa_xwalk).
select
    x.zillow_region_id,
    x.zillow_region_name as metro_name,
    x.state_code,
    x.size_rank,
    x.cbsa_code,
    x.match_method,
    a.cbsa_name,
    a.cbsa_type,
    a.population
from {{ ref('int_zillow_cbsa_xwalk') }} x
left join {{ ref('stg_acs_cbsa') }} a using (cbsa_code)

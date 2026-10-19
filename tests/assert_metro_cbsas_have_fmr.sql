-- Every metro CBSA should carry a HUD Fair Market Rent: on 2026-10-13 HUD covered all 393 ACS metro CBSAs.
select cbsa_code, cbsa_name
from {{ ref('fct_cbsa_affordability') }}
where cbsa_type = 'metro' and hud_fmr_2br_weighted is null

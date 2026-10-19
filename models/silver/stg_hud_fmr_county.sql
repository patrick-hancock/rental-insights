-- One row per county (or New England town) with its FY2027 Fair Market Rents.
-- Metro HUD area codes look like METRO10180M10180; characters 6-10 are the CBSA code.
select
    fips as county_fips,
    stusps as state_code,
    countyname as county_name,
    hud_area_code,
    hud_area_name,
    metro = '1' as is_metro,
    if(starts_with(hud_area_code, 'METRO'), substr(hud_area_code, 6, 5), null) as cbsa_code,
    safe_cast(pop2024 as int64) as population_2024,
    safe_cast(fmr_0 as int64) as fmr_studio,
    safe_cast(fmr_1 as int64) as fmr_1br,
    safe_cast(fmr_2 as int64) as fmr_2br,
    safe_cast(fmr_3 as int64) as fmr_3br,
    safe_cast(fmr_4 as int64) as fmr_4br
from {{ source('bronze', 'hud_fmr_fy27') }}

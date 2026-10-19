-- One row per CBSA (metro or micro area) from the ACS 2024 5-year estimates.
-- ACS marks unavailable values with large negative codes (for example -666666666), so negatives become NULL.
with src as (
    select * from {{ source('bronze', 'census_acs5_cbsa') }}
),

typed as (
    select
        metropolitan_statistical_area_micropolitan_statistical_area as cbsa_code,
        NAME as cbsa_name,
        if(ends_with(NAME, 'Metro Area'), 'metro', 'micro') as cbsa_type,
        {% for col, alias in [
            ('B01003_001E', 'population'),
            ('B19013_001E', 'median_household_income'),
            ('B25064_001E', 'median_gross_rent'),
            ('B25077_001E', 'median_home_value'),
            ('B25003_001E', 'occupied_units'),
            ('B25003_002E', 'owner_occupied_units'),
            ('B25003_003E', 'renter_occupied_units'),
            ('B25070_001E', 'renter_hh_total'),
            ('B25070_007E', 'renter_hh_30_35pct'),
            ('B25070_008E', 'renter_hh_35_40pct'),
            ('B25070_009E', 'renter_hh_40_50pct'),
            ('B25070_010E', 'renter_hh_50pct_plus'),
            ('B25070_011E', 'renter_hh_not_computed'),
        ] %}
        if(safe_cast({{ col }} as int64) < 0, null, safe_cast({{ col }} as int64)) as {{ alias }}{{ ',' if not loop.last }}
        {% endfor %}
    from src
)

select
    *,
    -- Zillow names a metro by its first principal city and first state: "New York, NY".
    concat(
        regexp_extract(cbsa_name, r'^([^-,/]+)'),  -- "/" too: "Louisville/Jefferson County, KY-IN"
        ', ',
        regexp_extract(cbsa_name, r', ([A-Z]{2})')
    ) as zillow_style_name
from typed

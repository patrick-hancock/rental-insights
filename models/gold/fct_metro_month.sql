-- One row per Zillow metro per month where either index has a value.
-- ZORI starts 2015-01, ZHVI starts 2000-01, so early months carry ZHVI only.
with joined as (
    select
        coalesce(r.zillow_region_id, v.zillow_region_id) as zillow_region_id,
        coalesce(r.month_end, v.month_end) as month_end,
        r.zori,
        v.zhvi
    from {{ ref('stg_zori_metro_month') }} r
    full outer join {{ ref('stg_zhvi_metro_month') }} v
        on v.zillow_region_id = r.zillow_region_id and v.month_end = r.month_end
)

select
    concat(cast(cur.zillow_region_id as string), '-', format_date('%Y%m', cur.month_end)) as metro_month_key,
    cur.zillow_region_id,
    cur.month_end,
    cur.zori,
    cur.zhvi,
    -- Year-over-year change against the same month a year earlier; a missing prior month gives NULL, not a wrong lag.
    safe_divide(cur.zori, prev.zori) - 1 as zori_yoy,
    safe_divide(cur.zhvi, prev.zhvi) - 1 as zhvi_yoy,
    -- Annual rent as a share of home value: a rough gross rental yield.
    safe_divide(cur.zori * 12, cur.zhvi) as gross_rent_yield
from joined cur
left join joined prev
    on prev.zillow_region_id = cur.zillow_region_id
    and prev.month_end = last_day(date_sub(cur.month_end, interval 12 month), month)

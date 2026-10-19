-- One row per calendar month covered by any Zillow series (month-end dates, matching Zillow's columns).
with bounds as (
    select min(month_end) as first_month, max(month_end) as last_month
    from (
        select month_end from {{ ref('stg_zori_metro_month') }}
        union all
        select month_end from {{ ref('stg_zhvi_metro_month') }}
    )
)

select
    month_end,
    date_trunc(month_end, month) as month_start,
    extract(year from month_end) as year,
    extract(quarter from month_end) as quarter,
    extract(month from month_end) as month,
    format_date('%Y-%m', month_end) as year_month
from bounds,
    unnest(generate_date_array(date_trunc(first_month, month), date_trunc(last_month, month), interval 1 month)) as m,
    unnest([last_day(m, month)]) as month_end

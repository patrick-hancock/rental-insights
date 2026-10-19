{#
  Turn a wide Zillow bronze table (one c_YYYY_MM_DD column per month) into one row per metro per month.
  Month columns are read from the live table, so a new month in the source needs no code change.
  UNPIVOT drops NULL cells, so a month with no published value has no row.
#}
{% macro zillow_long(source_table, value_name) %}
{%- set rel = source('bronze', source_table) -%}
{%- set month_cols = [] -%}
{%- for col in adapter.get_columns_in_relation(rel) if col.name.startswith('c_') -%}
    {%- do month_cols.append(col.name) -%}
{%- endfor -%}
select
    cast(RegionID as int64) as zillow_region_id,
    RegionName as zillow_region_name,
    StateName as state_code,
    cast(SizeRank as int64) as size_rank,
    parse_date('c_%Y_%m_%d', month_col) as month_end,
    cast(raw_value as float64) as {{ value_name }}
from {{ rel }}
unpivot (raw_value for month_col in ({{ month_cols | join(', ') }}))
where RegionType = 'msa'
{% endmacro %}

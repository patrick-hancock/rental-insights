{# Fails with one row per duplicated key combination. A local stand-in for dbt_utils.unique_combination_of_columns, so the project needs no package download. #}
{% test unique_combo(model, columns) %}
select {{ columns | join(', ') }}, count(*) as n
from {{ model }}
group by {{ columns | join(', ') }}
having count(*) > 1
{% endtest %}

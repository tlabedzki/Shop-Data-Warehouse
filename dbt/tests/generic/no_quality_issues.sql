{% test no_quality_issues(model, table_name, column_name, rule) %}
-- One test per cleaning rule on the quality log: with severity warn, dbt build reports how many values the rule
-- found (and fixed or set to unknown) without stopping the run.
select *
from {{ model }}
where table_name = '{{ table_name }}' and column_name = '{{ column_name }}' and rule = '{{ rule }}'
{% endtest %}

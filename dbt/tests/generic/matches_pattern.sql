{% test matches_pattern(model, column_name, pattern) %}
-- Rows whose value does not match the regular expression (empty values pass; not_null checks those).
select {{ column_name }}
from {{ model }}
where {{ column_name }} is not null and not regexp_full_match({{ column_name }}, '{{ pattern }}')
{% endtest %}

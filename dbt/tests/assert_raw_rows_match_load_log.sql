-- Every loaded file's row count in the load log equals the rows the raw table holds for that day.
{% set tables = ['customers', 'products', 'order_lines', 'order_events', 'payments', 'shipments', 'returns',
                 'reviews', 'sessions', 'campaigns'] %}
with raw_rows as (
    {% for table in tables %}
    select '{{ table }}' as table_name, _extract_date as extract_date, count(*) as row_count
    from {{ source('raw', table) }} group by _extract_date
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
)

select l.table_name, l.extract_date, l.row_count, r.row_count as raw_row_count
from {{ source('raw', '_load_log') }} as l
left join raw_rows as r on r.table_name = l.table_name and r.extract_date = l.extract_date
where coalesce(r.row_count, 0) <> l.row_count

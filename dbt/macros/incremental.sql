{# Orders that got anything on the run date: a line, an event, the payment, the shipment or a return. A daily run
   rebuilds exactly these orders; a full run (no run_date) rebuilds all of them. #}
{% macro touched_orders() -%}
    {%- set run_date = var('run_date') -%}
    select order_id from {{ ref('stg_order_lines') }} where _extract_date = date '{{ run_date }}'
    union
    select order_id from {{ ref('stg_order_events') }} where _extract_date = date '{{ run_date }}'
    union
    select order_id from {{ ref('stg_payments') }} where _extract_date = date '{{ run_date }}'
    union
    select order_id from {{ ref('stg_shipments') }} where _extract_date = date '{{ run_date }}'
    union
    select order_id from {{ ref('stg_returns') }} where _extract_date = date '{{ run_date }}'
{%- endmacro %}

{% macro is_daily_run() -%}
    {{ return(is_incremental() and var('run_date') is not none) }}
{%- endmacro %}

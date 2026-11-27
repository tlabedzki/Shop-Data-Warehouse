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
    union
    select order_id from {{ ref('stg_order_lines') }} where customer_id in ({{ touched_accounts() }})
{%- endmacro %}

{# Accounts of every person who got an account on the run date: a second account can land after the first
   one's orders, and then those orders move to the person it belongs to. #}
{% macro touched_accounts() -%}
    {%- set run_date = var('run_date') -%}
    select account_id from {{ ref('int_customer_accounts') }} where customer_id in (
        select a.customer_id from {{ ref('int_customer_accounts') }} as a
        inner join {{ ref('stg_customers') }} as c on c.customer_id = a.account_id
        where c._extract_date = date '{{ run_date }}'
    )
{%- endmacro %}

{% macro is_daily_run() -%}
    {{ return(is_incremental() and var('run_date') is not none) }}
{%- endmacro %}

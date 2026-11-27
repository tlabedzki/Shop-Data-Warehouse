{{ config(
    materialized='incremental',
    unique_key='session_id',
    incremental_strategy='delete+insert',
    on_schema_change='fail'
) }}

-- depends_on: {{ ref('stg_customers') }}

-- One row per web session; a daily run adds the sessions of its extract date and rebuilds the sessions of a
-- person who got another account that day.
select
    s.session_id,
    s.session_start,
    s.session_date,
    a.customer_id,
    s.customer_id as account_id,
    s.channel,
    s.device,
    s.campaign_id,
    s.pages_viewed,
    s.added_to_cart,
    s.reached_checkout,
    s.order_id,
    s.order_id is not null as converted
from {{ ref('stg_sessions') }} as s
left join {{ ref('int_customer_accounts') }} as a on a.account_id = s.customer_id
{% if is_daily_run() %}
where s._extract_date = date '{{ var("run_date") }}' or s.customer_id in ({{ touched_accounts() }})
{% endif %}

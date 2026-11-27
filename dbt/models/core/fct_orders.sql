{{ config(
    materialized='incremental',
    unique_key='order_id',
    incremental_strategy='delete+insert',
    on_schema_change='fail'
) }}

-- depends_on: {{ ref('stg_order_lines') }}, {{ ref('stg_order_events') }}, {{ ref('stg_payments') }}
-- depends_on: {{ ref('stg_shipments') }}, {{ ref('stg_returns') }}, {{ ref('stg_customers') }}
-- depends_on: {{ ref('int_customer_accounts') }}

-- One row per order: status assembled from the event log, payment and its fee, shipment and lateness.
with lines as (
    select * from {{ ref('int_order_lines') }}
    {% if is_daily_run() %}
    where order_id in ({{ touched_orders() }})
    {% endif %}
),

orders as (
    select
        order_id,
        min(customer_id) as account_id,
        min(order_datetime) as order_datetime,
        min(order_date) as order_date,
        min(payment_method) as payment_method,
        min(payment_provider) as payment_provider,
        min(delivery_method) as delivery_method,
        min(shipping_postal_code) as shipping_postal_code,
        min(channel) as channel,
        min(device) as device,
        min(campaign_id) as campaign_id,
        min(voucher_code) as voucher_code,
        min(session_id) as session_id,
        cast(count(*) as integer) as lines,
        cast(sum(quantity) as integer) as units,
        cast(count(*) filter (where quantity is null) as integer) as lines_without_quantity,
        cast(round(sum(round(quantity * unit_price_gross * (1 - discount_rate), 2)), 2) as decimal(14, 2))
            as lines_amount_gross
    from lines
    group by order_id
)

select
    o.order_id,
    a.customer_id,
    o.account_id,
    o.order_datetime,
    o.order_date,
    s.order_status,
    case
        when s.order_status = 'payment_failed' then 'failed'
        when s.order_status in ('cancelled', 'returned') and o.payment_method = 'COD' and s.delivered_at is null
            then 'unpaid'
        when s.order_status in ('cancelled', 'returned') then 'refunded'
        when o.payment_method = 'COD' and s.delivered_at is null then 'unpaid'
        else 'paid'
    end as payment_status,
    s.cancel_reason,
    s.placed_at,
    s.paid_at,
    s.cancelled_at,
    s.shipped_at,
    s.delivered_at,
    s.returned_at,
    sh.promised_delivery_date,
    cast(s.delivered_at as date) > sh.promised_delivery_date as is_late,
    o.payment_method,
    o.payment_provider,
    o.delivery_method,
    o.shipping_postal_code,
    o.channel,
    o.device,
    o.campaign_id,
    o.voucher_code,
    o.session_id,
    o.lines,
    o.units,
    o.lines_without_quantity,
    o.lines_amount_gross,
    p.payment_amount,
    p.payment_fee,
    sh.shipping_cost,
    sh.carrier_cost,
    sh.parcel_size,
    sh.is_bulky
from orders as o
left join {{ ref('int_customer_accounts') }} as a on a.account_id = o.account_id
left join {{ ref('int_order_status') }} as s on s.order_id = o.order_id
left join {{ ref('stg_payments') }} as p on p.order_id = o.order_id
left join {{ ref('stg_shipments') }} as sh on sh.order_id = o.order_id

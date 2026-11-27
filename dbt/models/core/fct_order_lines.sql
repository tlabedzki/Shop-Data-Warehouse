{{ config(
    materialized='incremental',
    unique_key='order_line_id',
    incremental_strategy='delete+insert',
    on_schema_change='fail'
) }}

-- depends_on: {{ ref('stg_order_lines') }}, {{ ref('stg_order_events') }}, {{ ref('stg_payments') }}
-- depends_on: {{ ref('stg_shipments') }}, {{ ref('stg_returns') }}

-- One row per order line: the product version valid on the order day, the customer (not the account), what was
-- kept after returns, revenue without VAT, purchase cost and gross margin.
with lines as (
    select * from {{ ref('int_order_lines') }}
    {% if is_daily_run() %}
    where order_id in ({{ touched_orders() }})
    {% endif %}
),

refunds as (
    select
        order_line_id,
        sum(returned_quantity) as refunded_quantity,
        sum(refund_amount) as refund_amount
    from {{ ref('stg_returns') }}
    where return_status = 'refunded'
    group by order_line_id
),

joined as (
    select
        l.order_line_id,
        l.order_id,
        a.customer_id,
        l.customer_id as account_id,
        l.product_id,
        v.product_version_id,
        l.order_date,
        l.order_datetime,
        l.campaign_id,
        l.channel,
        l.device,
        s.order_status,
        s.order_status not in ('cancelled', 'payment_failed') as is_sale,
        l.quantity,
        l.quantity_raw,
        l.unit_price_gross,
        l.unit_price_net,
        l.discount_rate,
        v.net_purchase_price,
        coalesce(r.refunded_quantity, 0) as refunded_quantity,
        coalesce(r.refund_amount, 0) as refund_amount
    from lines as l
    left join {{ ref('int_customer_accounts') }} as a on a.account_id = l.customer_id
    left join {{ ref('int_product_versions') }} as v
        on v.product_id = l.product_id and l.order_date between v.valid_from and v.valid_to
    left join {{ ref('int_order_status') }} as s on s.order_id = l.order_id
    left join refunds as r on r.order_line_id = l.order_line_id
)

select
    *,
    case when is_sale then quantity - refunded_quantity else 0 end as kept_quantity,
    round(quantity * unit_price_gross * (1 - discount_rate), 2) as line_amount_gross,
    round(case when is_sale then (quantity - refunded_quantity) * unit_price_net * (1 - discount_rate) else 0 end, 2)
        as net_revenue,
    round(case when is_sale then (quantity - refunded_quantity) * net_purchase_price else 0 end, 2) as purchase_cost,
    round(case when is_sale then (quantity - refunded_quantity) * (unit_price_net * (1 - discount_rate)
        - net_purchase_price) else 0 end, 2) as gross_margin
from joined

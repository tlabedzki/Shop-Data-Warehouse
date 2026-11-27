-- Order lines, typed; a line saved twice is kept once. The payment provider is the same for every line of an order,
-- so a missing one is taken from another line of that order. The quantity is checked in int_order_lines.
with lines as (
    select
        *,
        count(*) over (partition by order_line_id) as copies
    from {{ source('raw', 'order_lines') }}
    qualify row_number() over (partition by order_line_id order by _extract_date, _source_file) = 1
)

select
    cast(order_line_id as bigint) as order_line_id,
    cast(order_id as bigint) as order_id,
    cast(order_datetime as timestamp) as order_datetime,
    cast(cast(order_datetime as timestamp) as date) as order_date,
    cast(customer_id as bigint) as customer_id,
    cast(product_id as bigint) as product_id,
    cast(quantity as integer) as quantity_raw,
    cast(unit_price_gross as decimal(12, 2)) as unit_price_gross,
    cast(unit_price_net as decimal(12, 2)) as unit_price_net,
    cast(discount_rate as decimal(5, 4)) as discount_rate,
    payment_method,
    coalesce(
        nullif(trim(payment_provider), ''),
        max(nullif(trim(payment_provider), '')) over (partition by order_id)
    ) as payment_provider,
    payment_provider as payment_provider_raw,
    delivery_method,
    shipping_postal_code,
    channel,
    device,
    cast(campaign_id as bigint) as campaign_id,
    voucher_code,
    cast(session_id as bigint) as session_id,
    copies,
    _extract_date
from lines

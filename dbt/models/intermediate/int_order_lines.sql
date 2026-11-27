-- Order lines with a checked quantity. A quantity above the retail maximum is a typing error; the true one is
-- recovered from the payment: amount charged = lines after discount + delivery fee. It works when the order shipped
-- (the fee is known) and the other lines are fine; otherwise the quantity stays unknown.
with lines as (
    select
        *,
        quantity_raw between 1 and {{ max_line_quantity() }} as is_quantity_valid,
        unit_price_gross * (1 - discount_rate) as unit_amount_gross
    from {{ ref('stg_order_lines') }}
),

orders as (
    select
        l.order_id,
        p.payment_amount,
        s.shipping_cost,
        count(*) filter (where not l.is_quantity_valid) as invalid_lines,
        sum(round(l.quantity_raw * l.unit_amount_gross, 2)) filter (where l.is_quantity_valid) as valid_amount
    from lines as l
    left join {{ ref('stg_payments') }} as p on p.order_id = l.order_id
    left join {{ ref('stg_shipments') }} as s on s.order_id = l.order_id
    group by l.order_id, p.payment_amount, s.shipping_cost
),

recovered as (
    select
        l.order_line_id,
        round((o.payment_amount - o.shipping_cost - coalesce(o.valid_amount, 0)) / l.unit_amount_gross) as quantity
    from lines as l
    inner join orders as o on o.order_id = l.order_id
    where not l.is_quantity_valid
        and o.invalid_lines = 1
        and o.shipping_cost is not null
        and o.payment_amount > 0
        and l.unit_amount_gross > 0
        and abs(
            round((o.payment_amount - o.shipping_cost - coalesce(o.valid_amount, 0)) / l.unit_amount_gross)
            * l.unit_amount_gross - (o.payment_amount - o.shipping_cost - coalesce(o.valid_amount, 0))
        ) < 0.02
)

select
    l.* exclude (is_quantity_valid, unit_amount_gross),
    case
        when l.is_quantity_valid then l.quantity_raw
        when r.quantity between 1 and {{ max_line_quantity() }} then cast(r.quantity as integer)
    end as quantity
from lines as l
left join recovered as r on r.order_line_id = l.order_line_id

-- A shipped order with every quantity known was charged its lines after discount plus the delivery fee.
select order_id, payment_amount, lines_amount_gross, shipping_cost
from {{ ref('fct_orders') }}
where shipped_at is not null
    and lines_without_quantity = 0
    and abs(payment_amount - lines_amount_gross - shipping_cost) > 0.02

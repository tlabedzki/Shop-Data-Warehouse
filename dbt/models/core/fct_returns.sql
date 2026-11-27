select
    r.return_id,
    r.order_id,
    r.order_line_id,
    r.product_id,
    a.customer_id,
    r.customer_id as account_id,
    r.return_date,
    r.returned_quantity,
    r.return_reason,
    r.return_status,
    r.refund_amount,
    r.return_shipping_cost,
    r.handling_cost,
    r.written_off_quantity,
    r.write_off_cost
from {{ ref('stg_returns') }} as r
left join {{ ref('int_customer_accounts') }} as a on a.account_id = r.customer_id

-- Daily sales by channel and category: what was sold and kept, revenue without VAT, cost and gross margin.
select
    l.order_date,
    l.channel,
    p.category,
    count(distinct l.order_id) as orders,
    count(distinct l.order_id) filter (where l.is_sale) as sold_orders,
    count(*) as lines,
    sum(l.quantity) filter (where l.is_sale) as units_ordered,
    sum(l.kept_quantity) as units_kept,
    sum(l.refunded_quantity) as units_returned,
    round(sum(l.line_amount_gross), 2) as ordered_amount_gross,
    round(sum(l.net_revenue), 2) as net_revenue,
    round(sum(l.purchase_cost), 2) as purchase_cost,
    round(sum(l.gross_margin), 2) as gross_margin,
    round(sum(l.refund_amount), 2) as refund_amount
from {{ ref('fct_order_lines') }} as l
left join {{ ref('dim_product') }} as p on p.product_version_id = l.product_version_id
group by all

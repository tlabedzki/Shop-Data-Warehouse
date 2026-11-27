-- Customers by the month of their first sale and the months since: how many still buy and what they spend.
with sales as (
    select customer_id, order_id, order_date, sum(net_revenue) as net_revenue
    from {{ ref('fct_order_lines') }}
    where is_sale
    group by customer_id, order_id, order_date
),

first_sale as (
    select customer_id, date_trunc('month', min(order_date)) as cohort_month
    from sales
    group by customer_id
)

select
    strftime(f.cohort_month, '%Y-%m') as cohort,
    datediff('month', f.cohort_month, date_trunc('month', s.order_date)) as months_since_first,
    count(distinct s.customer_id) as customers,
    count(*) as orders,
    round(sum(s.net_revenue), 2) as net_revenue
from sales as s
inner join first_sale as f on f.customer_id = s.customer_id
group by all

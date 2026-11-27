-- The list price on every order line equals the price of the product version valid on the order day (SCD2).
select l.order_line_id, l.order_date, l.unit_price_gross, p.sales_price_gross, p.valid_from, p.valid_to
from {{ ref('fct_order_lines') }} as l
inner join {{ ref('dim_product') }} as p on p.product_version_id = l.product_version_id
where l.unit_price_gross <> p.sales_price_gross

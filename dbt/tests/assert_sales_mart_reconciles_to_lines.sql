-- The daily sales mart adds up to the order line fact to the grosz.
with mart as (
    select round(sum(net_revenue), 2) as net_revenue, round(sum(gross_margin), 2) as gross_margin,
           sum(units_kept) as units_kept
    from {{ ref('mart_daily_sales') }}
),

fact as (
    select round(sum(net_revenue), 2) as net_revenue, round(sum(gross_margin), 2) as gross_margin,
           sum(kept_quantity) as units_kept
    from {{ ref('fct_order_lines') }}
)

select * from mart, fact
where mart.net_revenue <> fact.net_revenue
    or mart.gross_margin <> fact.gross_margin
    or mart.units_kept <> fact.units_kept

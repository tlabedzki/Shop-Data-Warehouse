-- Slowly changing dimension type 2 from the history of catalogue extracts: a product gets a new version on every
-- day its record changed. Built from the loaded extracts rather than a dbt snapshot, so a backfill or a late day
-- gives the same history as loading in order. Attributes that never change come from the latest record.
with extracts as (
    select * from {{ ref('stg_products') }}
),

latest as (
    select *
    from extracts
    qualify row_number() over (partition by product_id order by _extract_date desc) = 1
)

select
    e.product_id || '-' || strftime(e._extract_date, '%Y%m%d') as product_version_id,
    e.product_id,
    e._extract_date as valid_from,
    coalesce(
        lead(e._extract_date) over (partition by e.product_id order by e._extract_date) - interval 1 day,
        date '9999-12-31'
    )::date as valid_to,
    lead(e._extract_date) over (partition by e.product_id order by e._extract_date) is null as is_current,
    e.sales_price_gross,
    e.sales_price_net,
    e.discontinued_date,
    l.product_name,
    l.category,
    l.subcategory,
    l.product_type,
    l.brand,
    l.product_series,
    l.product_model,
    l.color,
    l.parcel_size,
    l.currency,
    l.net_purchase_price,
    l.launch_date
from extracts as e
inner join latest as l on l.product_id = e.product_id

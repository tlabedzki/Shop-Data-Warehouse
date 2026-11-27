-- Every product record the catalogue sent (one per product and extract day), typed and cleaned.
with extracts as (
    select *
    from {{ source('raw', 'products') }}
    qualify row_number() over (partition by product_id, _extract_date order by _source_file desc) = 1
),

typed as (
    select
        cast(product_id as bigint) as product_id,
        product_name,
        category,
        subcategory,
        product_type,
        brand,
        product_series,
        product_model,
        nullif(trim(color), '') as color,
        parcel_size,
        currency,
        cast(net_purchase_price as decimal(12, 2)) as net_purchase_price_raw,
        cast(sales_price_gross as decimal(12, 2)) as sales_price_gross,
        cast(sales_price_net as decimal(12, 2)) as sales_price_net,
        cast(launch_date as date) as launch_date,
        cast(discontinued_date as date) as discontinued_date,
        color as color_raw,
        _extract_date
    from extracts
)

select
    *,
    -- A purchase price typed in grosze is 100 times too high. Real ones stay below twice the net list price, even
    -- in the weeks a list price was below cost; above five times the list price the value is divided by 100.
    case
        when net_purchase_price_raw > 5 * sales_price_net
            then cast(net_purchase_price_raw / 100 as decimal(12, 2))
        else net_purchase_price_raw
    end as net_purchase_price
from typed

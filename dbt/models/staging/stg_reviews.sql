select
    cast(review_id as bigint) as review_id,
    cast(order_id as bigint) as order_id,
    cast(order_line_id as bigint) as order_line_id,
    cast(product_id as bigint) as product_id,
    cast(customer_id as bigint) as customer_id,
    cast(review_date as date) as review_date,
    cast(review_score as integer) as review_score,
    review_comment,
    _extract_date
from {{ source('raw', 'reviews') }}
qualify row_number() over (partition by review_id order by _extract_date desc, _source_file desc) = 1

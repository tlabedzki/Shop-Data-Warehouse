select
    cast(return_id as bigint) as return_id,
    cast(order_id as bigint) as order_id,
    cast(order_line_id as bigint) as order_line_id,
    cast(product_id as bigint) as product_id,
    cast(customer_id as bigint) as customer_id,
    cast(return_date as date) as return_date,
    cast(returned_quantity as integer) as returned_quantity,
    return_reason,
    return_status,
    cast(refund_amount as decimal(12, 2)) as refund_amount,
    cast(return_shipping_cost as decimal(12, 2)) as return_shipping_cost,
    cast(handling_cost as decimal(12, 2)) as handling_cost,
    cast(written_off_quantity as integer) as written_off_quantity,
    cast(write_off_cost as decimal(12, 2)) as write_off_cost,
    _extract_date
from {{ source('raw', 'returns') }}
qualify row_number() over (partition by return_id order by _extract_date desc, _source_file desc) = 1

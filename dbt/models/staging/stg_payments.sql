select
    cast(payment_id as bigint) as payment_id,
    cast(order_id as bigint) as order_id,
    cast(payment_amount as decimal(12, 2)) as payment_amount,
    cast(fee_rate as decimal(6, 4)) as fee_rate,
    cast(fixed_fee as decimal(12, 2)) as fixed_fee,
    cast(payment_fee as decimal(12, 2)) as payment_fee,
    _extract_date
from {{ source('raw', 'payments') }}
qualify row_number() over (partition by payment_id order by _extract_date desc, _source_file desc) = 1

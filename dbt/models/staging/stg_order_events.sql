select
    cast(order_id as bigint) as order_id,
    event_type,
    cast(event_at as timestamp) as event_at,
    cancel_reason,
    -- Events with the same time keep the order they happen in.
    case event_type
        when 'placed' then 1
        when 'paid' then 2
        when 'payment_failed' then 3
        when 'cancelled' then 4
        when 'shipped' then 5
        when 'delivered' then 6
        when 'returned' then 7
    end as event_rank,
    _extract_date
from {{ source('raw', 'order_events') }}
qualify row_number() over (partition by order_id, event_type order by _extract_date desc, _source_file desc) = 1

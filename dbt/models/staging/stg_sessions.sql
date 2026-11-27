select
    cast(session_id as bigint) as session_id,
    cast(session_start as timestamp) as session_start,
    cast(cast(session_start as timestamp) as date) as session_date,
    cast(customer_id as bigint) as customer_id,
    channel,
    device,
    cast(campaign_id as bigint) as campaign_id,
    cast(pages_viewed as integer) as pages_viewed,
    cast(added_to_cart as boolean) as added_to_cart,
    cast(reached_checkout as boolean) as reached_checkout,
    cast(order_id as bigint) as order_id,
    _extract_date
from {{ source('raw', 'sessions') }}
qualify row_number() over (partition by session_id order by _extract_date desc, _source_file desc) = 1

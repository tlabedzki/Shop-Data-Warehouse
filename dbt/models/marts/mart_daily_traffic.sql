-- Daily sessions and conversion by channel and device.
select
    session_date,
    channel,
    device,
    count(*) as sessions,
    count(*) filter (where added_to_cart) as sessions_with_cart,
    count(*) filter (where reached_checkout) as sessions_at_checkout,
    count(*) filter (where converted) as orders,
    round(count(*) filter (where converted) / count(*), 4) as conversion_rate
from {{ ref('fct_sessions') }}
group by all

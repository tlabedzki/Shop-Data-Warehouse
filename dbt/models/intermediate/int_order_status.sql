-- Status of every order from its event log: the latest event wins, its time and the time of each step are kept.
with events as (
    select * from {{ ref('stg_order_events') }}
),

latest as (
    select order_id, event_type
    from events
    qualify row_number() over (partition by order_id order by event_at desc, event_rank desc) = 1
)

select
    e.order_id,
    l.event_type as order_status,
    max(e.event_at) filter (where e.event_type = 'placed') as placed_at,
    max(e.event_at) filter (where e.event_type = 'paid') as paid_at,
    max(e.event_at) filter (where e.event_type = 'payment_failed') as payment_failed_at,
    max(e.event_at) filter (where e.event_type = 'cancelled') as cancelled_at,
    max(e.cancel_reason) filter (where e.event_type = 'cancelled') as cancel_reason,
    max(e.event_at) filter (where e.event_type = 'shipped') as shipped_at,
    max(e.event_at) filter (where e.event_type = 'delivered') as delivered_at,
    max(e.event_at) filter (where e.event_type = 'returned') as returned_at
from events as e
inner join latest as l on l.order_id = e.order_id
group by e.order_id, l.event_type

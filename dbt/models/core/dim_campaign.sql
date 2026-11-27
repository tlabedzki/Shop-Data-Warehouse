select
    campaign_id,
    campaign_name,
    channel,
    start_date,
    end_date,
    total_cost,
    voucher_code,
    datediff('day', start_date, end_date) + 1 as days
from {{ ref('stg_campaigns') }}

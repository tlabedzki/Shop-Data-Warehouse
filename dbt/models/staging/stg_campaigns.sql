select
    cast(campaign_id as bigint) as campaign_id,
    campaign_name,
    channel,
    cast(start_date as date) as start_date,
    cast(end_date as date) as end_date,
    cast(total_cost as decimal(12, 2)) as total_cost,
    voucher_code,
    _extract_date
from {{ source('raw', 'campaigns') }}
qualify row_number() over (partition by campaign_id order by _extract_date desc, _source_file desc) = 1

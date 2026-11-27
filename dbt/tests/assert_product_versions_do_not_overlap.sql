-- Versions of one product cover days without gaps or overlaps: each starts the day after the previous ends.
select product_id, valid_from, previous_valid_to
from (
    select
        product_id,
        valid_from,
        lag(valid_to) over (partition by product_id order by valid_from) as previous_valid_to
    from {{ ref('dim_product') }}
)
where previous_valid_to is not null and valid_from <> previous_valid_to + interval 1 day

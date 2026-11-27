select
    r.review_id,
    r.order_id,
    r.order_line_id,
    r.product_id,
    a.customer_id,
    r.customer_id as account_id,
    r.review_date,
    r.review_score,
    r.review_comment
from {{ ref('stg_reviews') }} as r
left join {{ ref('int_customer_accounts') }} as a on a.account_id = r.customer_id

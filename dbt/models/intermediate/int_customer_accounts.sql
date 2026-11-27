-- One person can open a second account. The bank account number is never retyped, so accounts that share it belong
-- to one customer: the oldest account (lowest id) is the customer, the others point to it.
select
    customer_id as account_id,
    min(customer_id) over (partition by bank_account_number) as customer_id,
    count(*) over (partition by bank_account_number) as accounts
from {{ ref('stg_customers') }}

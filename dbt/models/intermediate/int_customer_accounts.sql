-- One person can open a second account. The bank account number is never retyped, so accounts that share it belong
-- to one customer: the oldest account (lowest id) is the customer, the others point to it. An account without
-- a bank account number stays its own customer.
select
    customer_id as account_id,
    min(customer_id) over (partition by coalesce(bank_account_number, 'account ' || customer_id)) as customer_id,
    count(*) over (partition by coalesce(bank_account_number, 'account ' || customer_id)) as accounts
from {{ ref('stg_customers') }}

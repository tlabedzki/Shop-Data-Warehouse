-- One row per customer (person), not per account: a second account is merged into the oldest one. A value missing
-- on the oldest account is taken from another account of the same person.
with accounts as (
    select c.*, a.customer_id as person_id, a.accounts
    from {{ ref('stg_customers') }} as c
    inner join {{ ref('int_customer_accounts') }} as a on a.account_id = c.customer_id
)

select
    person_id as customer_id,
    cast(max(accounts) as integer) as accounts,
    arg_min(first_name, customer_id) as first_name,
    arg_min(last_name, customer_id) as last_name,
    arg_min(gender, customer_id) as gender,
    arg_min(age, customer_id) filter (where age is not null) as age,
    arg_min(email, customer_id) filter (where email is not null) as email,
    arg_min(phone_number, customer_id) filter (where phone_number is not null) as phone_number,
    arg_min(postal_code, customer_id) filter (where postal_code is not null) as postal_code,
    arg_min(city, customer_id) filter (where city is not null) as city,
    min(signup_date) as signup_date,
    arg_min(acquisition_channel, customer_id) as acquisition_channel
from accounts
group by person_id

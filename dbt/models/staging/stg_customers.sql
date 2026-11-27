-- One row per customer account, typed and cleaned. Raw values stay next to the clean ones for the quality log.
with accounts as (
    select *
    from {{ source('raw', 'customers') }}
    qualify row_number() over (partition by customer_id order by _extract_date desc, _source_file desc) = 1
),

reference as (
    select postal_code, city from {{ ref('postal_codes') }}
)

select
    cast(a.customer_id as bigint) as customer_id,
    a.first_name,
    a.last_name,
    a.gender,
    {{ clean_age('a.age') }} as age,
    {{ clean_email('a.email') }} as email,
    {{ clean_phone('a.phone_number') }} as phone_number,
    {{ clean_postal_code('a.postal_code') }} as postal_code,
    coalesce(r.city, nullif(trim(a.city), '')) as city,
    a.bank_account_number,
    cast(a.signup_date as date) as signup_date,
    a.acquisition_channel,
    a.age as age_raw,
    a.email as email_raw,
    a.phone_number as phone_number_raw,
    a.postal_code as postal_code_raw,
    a.city as city_raw,
    r.city as reference_city,
    a._extract_date
from accounts as a
left join reference as r on r.postal_code = {{ clean_postal_code('a.postal_code') }}

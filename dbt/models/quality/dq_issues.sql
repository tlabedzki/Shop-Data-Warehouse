-- The warehouse's own log of data quality problems: one row per value a cleaning rule found wrong, with the raw
-- value, what the warehouse keeps instead (empty when the true value cannot be known) and the action taken.
-- Every rule reads only what the shop sent; the generator's answer key is compared afterwards (shop_warehouse.score).
with customers as (
    select * from {{ ref('stg_customers') }}
),

accounts as (
    select * from {{ ref('int_customer_accounts') }}
),

products as (
    select *
    from {{ ref('stg_products') }}
    qualify row_number() over (partition by product_id order by _extract_date desc) = 1
),

lines as (
    select * from {{ ref('int_order_lines') }}
),

issues as (
    -- customers
    select 'customers' as table_name, customer_id::varchar as record_key, 'phone_number' as column_name,
        'missing' as rule, null as raw_value, null as kept_value
    from customers where nullif(trim(phone_number_raw), '') is null
    union all
    select 'customers', customer_id::varchar, 'phone_number', 'format', phone_number_raw, phone_number
    from customers where trim(phone_number_raw) <> '' and not {{ phone_is_standard('phone_number_raw') }}
    union all
    select 'customers', customer_id::varchar, 'email', 'missing', null, null
    from customers where nullif(trim(email_raw), '') is null
    union all
    select 'customers', customer_id::varchar, 'email', 'format', email_raw, email
    from customers where trim(email_raw) <> '' and email_raw is distinct from email
    union all
    select 'customers', customer_id::varchar, 'postal_code', 'format', postal_code_raw, postal_code
    from customers where not regexp_full_match(postal_code_raw, '\d{2}-\d{3}')
    union all
    select 'customers', customer_id::varchar, 'city', 'missing', null, city
    from customers where nullif(trim(city_raw), '') is null
    union all
    select 'customers', customer_id::varchar, 'city', 'typo', city_raw, city
    from customers where trim(city_raw) <> '' and reference_city is not null and city_raw <> reference_city
    union all
    select 'customers', customer_id::varchar, 'age', 'missing', null, null
    from customers where nullif(trim(age_raw), '') is null
    union all
    select 'customers', customer_id::varchar, 'age', 'outlier', age_raw, null
    from customers where trim(age_raw) <> '' and age is null
    union all
    select 'customers', account_id::varchar, 'customer_id', 'duplicate_customer', account_id::varchar,
        customer_id::varchar
    from accounts where account_id <> customer_id
    -- products
    union all
    select 'products', product_id::varchar, 'color', 'missing', null, null
    from products where color is null
    union all
    select 'products', product_id::varchar, 'net_purchase_price', 'outlier', net_purchase_price_raw::varchar,
        net_purchase_price::varchar
    from products where net_purchase_price is distinct from net_purchase_price_raw
    -- order lines
    union all
    select 'order_lines', order_line_id::varchar, 'order_line_id', 'duplicate_row', order_line_id::varchar, null
    from lines where copies > 1
    union all
    select 'order_lines', order_line_id::varchar, 'payment_provider', 'missing', null, payment_provider
    from lines where nullif(trim(payment_provider_raw), '') is null
    union all
    select 'order_lines', order_line_id::varchar, 'quantity', 'outlier', quantity_raw::varchar, quantity::varchar
    from lines where quantity is distinct from quantity_raw
)

select
    table_name,
    record_key,
    column_name,
    rule,
    raw_value,
    kept_value,
    case
        when rule = 'duplicate_row' then 'removed copy'
        when rule = 'duplicate_customer' then 'merged'
        when kept_value is not null then 'fixed'
        else 'set to unknown'
    end as action
from issues

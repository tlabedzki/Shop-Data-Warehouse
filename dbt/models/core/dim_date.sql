-- Calendar from the first order day to the last loaded day.
with bounds as (
    select min(extract_date) as first_day, max(extract_date) as last_day from {{ source('raw', '_load_log') }}
)

select
    cast(day as date) as date_day,
    year(day) as year,
    quarter(day) as quarter,
    month(day) as month,
    strftime(day, '%Y-%m') as year_month,
    isodow(day) as iso_weekday,
    strftime(day, '%A') as weekday_name,
    isodow(day) >= 6 as is_weekend,
    week(day) as iso_week
from bounds, range(bounds.first_day, bounds.last_day + interval 1 day, interval 1 day) as days(day)

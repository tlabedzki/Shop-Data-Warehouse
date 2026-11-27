{# Cleaning rules shared by staging models and the data quality log. Each takes a raw text column. #}

{# Phone numbers in one of the shop's four formats: 600 100 200, +48 600 100 200, 22 577 94 90, +48 22 577 94 90. #}
{% macro phone_is_standard(column) -%}
    regexp_full_match({{ column }}, '(\+48 )?(\d{3} \d{3} \d{3}|\d{2} \d{3} \d{2} \d{2})')
{%- endmacro %}

{# Any way of writing a Polish number becomes +48 and nine digits; anything else becomes null. #}
{% macro clean_phone(column) -%}
    case
        when length(regexp_replace({{ column }}, '[^0-9]', '', 'g')) = 9
            then '+48' || regexp_replace({{ column }}, '[^0-9]', '', 'g')
        when regexp_full_match(regexp_replace({{ column }}, '[^0-9]', '', 'g'), '48\d{9}')
            then '+' || regexp_replace({{ column }}, '[^0-9]', '', 'g')
        when regexp_full_match(regexp_replace({{ column }}, '[^0-9]', '', 'g'), '0048\d{9}')
            then '+' || substr(regexp_replace({{ column }}, '[^0-9]', '', 'g'), 3)
    end
{%- endmacro %}

{# E-mail in lower case without spaces; text that is not an address (no @) becomes null. #}
{% macro clean_email(column) -%}
    case
        when regexp_full_match(lower(trim({{ column }})), '[^@\s]+@[^@\s]+\.[a-z]+') then lower(trim({{ column }}))
    end
{%- endmacro %}

{# Postal codes as 00-000; five digits written any other way are put back in that form. #}
{% macro clean_postal_code(column) -%}
    case
        when regexp_full_match(regexp_replace({{ column }}, '[^0-9]', '', 'g'), '\d{5}')
            then substr(regexp_replace({{ column }}, '[^0-9]', '', 'g'), 1, 2) || '-'
                 || substr(regexp_replace({{ column }}, '[^0-9]', '', 'g'), 3, 3)
    end
{%- endmacro %}

{# The shop sells to adults; an age outside 18-100 is a typing error and becomes unknown. #}
{% macro clean_age(column) -%}
    case when try_cast({{ column }} as integer) between 18 and 100 then try_cast({{ column }} as integer) end
{%- endmacro %}

{# The largest quantity a retail line can have; above it the line is checked against the payment. #}
{% macro max_line_quantity() -%} 20 {%- endmacro %}

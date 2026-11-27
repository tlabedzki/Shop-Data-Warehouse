-- Product versions (SCD2): join a fact on product_id and the fact's date between valid_from and valid_to.
select * from {{ ref('int_product_versions') }}

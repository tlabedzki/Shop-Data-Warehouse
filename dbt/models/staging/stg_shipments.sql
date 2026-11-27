select
    cast(shipment_id as bigint) as shipment_id,
    cast(order_id as bigint) as order_id,
    delivery_method,
    cast(is_bulky as boolean) as is_bulky,
    parcel_size,
    cast(shipping_cost as decimal(12, 2)) as shipping_cost,
    cast(carrier_cost as decimal(12, 2)) as carrier_cost,
    cast(shipped_at as timestamp) as shipped_at,
    cast(promised_delivery_date as date) as promised_delivery_date,
    _extract_date
from {{ source('raw', 'shipments') }}
qualify row_number() over (partition by shipment_id order by _extract_date desc, _source_file desc) = 1

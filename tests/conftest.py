"""A tiny shop in the Data-Generator format: three orders over a few days, enough to exercise every rule."""
from __future__ import annotations

import pandas as pd
import pytest

T = pd.Timestamp


def tiny_generated() -> dict[str, pd.DataFrame]:
    customers = pd.DataFrame({
        "customer_id": [100001, 100002],
        "age": pd.array([30, 41], dtype="Int64"),
        "gender": ["Female", "Male"],
        "first_name": ["Ala", "Olek"],
        "last_name": ["Nowak", "Wilk"],
        "email": ["ala.nowak@example.com", "olek.wilk@example.org"],
        "phone_number": ["+48 600 100 200", "+48 700 200 300"],
        "bank_account_number": ["PL00000000000000000000000001", "PL00000000000000000000000002"],
        "postal_code": ["00-001", "30-002"],
        "city": ["Warszawa", "Kraków"],
        "signup_date": [T("2021-05-01"), T("2023-01-02")],
        "customer_segment": ["regular", "one_time"],
        "preferred_category": ["Beauty", "Books"],
        "price_tier": ["standard", "budget"],
        "acquisition_channel": ["direct", "email"],
        "true_purchase_rate": [1.2, 0.0],
        "true_churn_date": [T("2025-01-01"), T("2023-01-02")],
    })
    products = pd.DataFrame({
        "product_id": [200001, 200002],
        "net_purchase_price": [50.0, 20.0],
        "sales_margin": [0.5, 0.5],
        "currency": ["PLN", "PLN"],
        "category": ["Beauty", "Books"],
        "subcategory": ["Skin", "Novels"],
        "product_type": ["Cream", "Novel"],
        "brand": ["Brand A", "Brand B"],
        "product_series": ["S", "T"],
        "product_model": ["1", "2"],
        "product_name": ["Cream Brand A S 1", "Novel Brand B T 2"],
        "product_popularity": [1.0, 0.5],
        "color": ["white", "blue"],
        "sales_price_net": [99.19, 40.65],
        "sales_price_gross": [122.0, 50.0],
        "launch_date": [T("2020-01-01"), T("2023-01-02")],
        "discontinued_date": [pd.NaT, T("2023-01-04")],
        "parcel_size": ["small", "small"],
    })
    prices = pd.DataFrame({
        "product_id": [200001, 200001, 200002],
        "valid_from": [T("2023-01-01"), T("2023-01-03"), T("2023-01-02")],
        "valid_to": [T("2023-01-02"), pd.NaT, pd.NaT],
        "sales_price_gross": [123.0, 122.0, 50.0],
        "sales_price_net": [100.0, 99.19, 40.65],
        "change_type": ["initial", "decrease", "initial"],
    })
    line = {
        "unit_price_net": None, "payment_provider": "PayU", "delivery_method": "InPost courier", "discount_rate": 0.0,
        "is_fraud": False, "channel": "direct", "device": "mobile", "campaign_id": pd.NA, "voucher_code": None,
        "affiliate_commission": 0.0, "cancel_reason": None, "cancelled_at": pd.NaT,
    }
    orders = pd.DataFrame([
        {**line, "order_id": 100001, "order_line_id": 1000001, "order_datetime": T("2023-01-01 10:00"),
         "product_id": 200001, "quantity": 1, "unit_price_gross": 123.0, "customer_id": 100001,
         "payment_method": "Card", "session_id": 1, "order_status": "delivered", "payment_status": "paid"},
        {**line, "order_id": 100002, "order_line_id": 1000002, "order_datetime": T("2023-01-02 12:00"),
         "product_id": 200002, "quantity": 2, "unit_price_gross": 50.0, "customer_id": 100002,
         "payment_method": "COD", "session_id": 2, "order_status": "cancelled", "payment_status": "unpaid",
         "cancel_reason": "customer_request", "cancelled_at": T("2023-01-03 09:00")},
        {**line, "order_id": 100003, "order_line_id": 1000003, "order_datetime": T("2023-01-03 08:00"),
         "product_id": 200001, "quantity": 1, "unit_price_gross": 122.0, "customer_id": 100001,
         "payment_method": "BLIK", "session_id": 3, "order_status": "returned", "payment_status": "refunded"},
    ])
    orders["order_date"] = orders["order_datetime"].dt.normalize()
    orders["unit_price_net"] = (orders["unit_price_gross"] / 1.23).round(2)
    orders["campaign_id"] = orders["campaign_id"].astype("Int64")
    orders["shipping_postal_code"] = ["00-001", "30-002", "00-001"]
    shipments = pd.DataFrame({
        "shipment_id": [1, 2], "order_id": [100001, 100003], "delivery_method": ["InPost courier"] * 2,
        "is_bulky": [False, False], "shipping_cost": [12.99, 12.99],
        "shipped_at": [T("2023-01-02 15:00"), T("2023-01-03 18:00")],
        "delivered_at": [T("2023-01-03 11:00"), T("2023-01-04 10:00")],
        "promised_delivery_date": [T("2023-01-04"), T("2023-01-05")], "is_late": [False, False],
        "parcel_size": ["small", "small"], "carrier_cost": [9.5, 9.5],
    })
    returns = pd.DataFrame({
        "return_id": [1], "order_id": [100003], "order_line_id": [1000003], "product_id": [200001],
        "customer_id": [100001], "return_date": [T("2023-01-05")], "returned_quantity": [1],
        "return_reason": ["changed_mind"], "refund_amount": [122.0], "return_status": ["refunded"],
        "return_shipping_cost": [0.0], "handling_cost": [12.0], "written_off_quantity": [0], "write_off_cost": [0.0],
    })
    payments = pd.DataFrame({
        "payment_id": [1, 2, 3], "order_id": [100001, 100002, 100003], "payment_amount": [135.99, 0.0, 134.99],
        "fee_rate": [0.016, 0.0, 0.011], "fixed_fee": [0.3, 0.0, 0.3], "payment_fee": [2.48, 0.0, 1.78],
    })
    reviews = pd.DataFrame({
        "review_id": [1], "order_id": [100001], "order_line_id": [1000001], "product_id": [200001],
        "customer_id": [100001], "review_date": [T("2023-01-04")], "review_score": [5], "review_comment": [None],
    })
    sessions = pd.DataFrame({
        "session_id": [1, 2, 3, 4],
        "session_start": [T("2023-01-01 09:55"), T("2023-01-02 11:50"), T("2023-01-03 07:58"), T("2023-01-03 20:00")],
        "customer_id": pd.array([100001, 100002, 100001, pd.NA], dtype="Int64"),
        "channel": ["direct"] * 4, "device": ["mobile"] * 4, "campaign_id": pd.array([pd.NA] * 4, dtype="Int64"),
        "pages_viewed": [5, 4, 6, 1], "added_to_cart": [True, True, True, False],
        "reached_checkout": [True, True, True, False],
        "order_id": pd.array([100001, 100002, 100003, pd.NA], dtype="Int64"),
    })
    campaigns = pd.DataFrame({
        "campaign_id": [1], "campaign_name": ["Email 2023-01-02"], "channel": ["email"],
        "start_date": [T("2023-01-02")], "end_date": [T("2023-01-08")], "total_cost": [500.0],
        "voucher_code": ["EML23010200"], "true_daily_lift": [0.05],
    })
    issues = pd.DataFrame(columns=["issue_id", "table_name", "key_column", "key_value", "column_name", "issue_type",
                                   "dirty_value", "clean_value"])
    return {
        "customer_data": customers, "product_data": products, "order_data": orders, "price_history": prices,
        "shipment_data": shipments, "return_data": returns, "payment_data": payments, "review_data": reviews,
        "session_data": sessions, "campaign_data": campaigns, "quality_issue_data": issues,
    }


@pytest.fixture
def generated() -> dict[str, pd.DataFrame]:
    return tiny_generated()


@pytest.fixture
def landed(tmp_path, monkeypatch, generated):
    """The tiny shop written to a temporary landing folder; returns that folder."""
    from shop_warehouse import landing

    monkeypatch.setattr(landing, "read_generated", lambda variant: generated)
    monkeypatch.setattr(landing, "landing_dir", lambda variant: tmp_path / "landing" / variant)
    landing.land("dirty")
    return tmp_path / "landing" / "dirty"

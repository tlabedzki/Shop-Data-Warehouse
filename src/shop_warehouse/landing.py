"""
Turn the generated shop into the daily files its source systems would drop.

Every day gets one folder with one CSV per source table and a manifest written last (the "done" flag the loader
waits for):

    data/landing/<variant>/<YYYY-MM-DD>/<table>.csv
    data/landing/<variant>/<YYYY-MM-DD>/_manifest.json

A file holds what the system knew that day. Order lines land on the order day without their final status; the
status arrives later as events (paid, cancelled, shipped, delivered, returned). Shipments land on the dispatch day
without the delivery time. Products land as a full record whenever something changes: launch, a new list price
(from the price history) or the end of sale. Customers land on the signup day; everything that existed before the
first day lands in the first day's file (the initial export). Truth columns of the generator never land.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from shop_warehouse.config import generated_dir, landing_dir

TABLES = {
    "customers": [
        "customer_id", "first_name", "last_name", "gender", "age", "email", "phone_number", "bank_account_number",
        "postal_code", "city", "signup_date", "acquisition_channel",
    ],
    "products": [
        "product_id", "product_name", "category", "subcategory", "product_type", "brand", "product_series",
        "product_model", "color", "parcel_size", "currency", "net_purchase_price", "sales_price_gross",
        "sales_price_net", "launch_date", "discontinued_date",
    ],
    "order_lines": [
        "order_id", "order_line_id", "order_datetime", "customer_id", "product_id", "quantity", "unit_price_gross",
        "unit_price_net", "discount_rate", "payment_method", "payment_provider", "delivery_method",
        "shipping_postal_code", "channel", "device", "campaign_id", "voucher_code", "session_id",
    ],
    "order_events": ["order_id", "event_type", "event_at", "cancel_reason"],
    "payments": ["payment_id", "order_id", "payment_amount", "fee_rate", "fixed_fee", "payment_fee"],
    "shipments": [
        "shipment_id", "order_id", "delivery_method", "is_bulky", "parcel_size", "shipping_cost", "carrier_cost",
        "shipped_at", "promised_delivery_date",
    ],
    "returns": [
        "return_id", "order_id", "order_line_id", "product_id", "customer_id", "return_date", "returned_quantity",
        "return_reason", "return_status", "refund_amount", "return_shipping_cost", "handling_cost",
        "written_off_quantity", "write_off_cost",
    ],
    "reviews": ["review_id", "order_id", "order_line_id", "product_id", "customer_id", "review_date", "review_score",
                "review_comment"],
    "sessions": ["session_id", "session_start", "customer_id", "channel", "device", "campaign_id", "pages_viewed",
                 "added_to_cart", "reached_checkout", "order_id"],
    "campaigns": ["campaign_id", "campaign_name", "channel", "start_date", "end_date", "total_cost", "voucher_code"],
}
MANIFEST = "_manifest.json"


@dataclass(frozen=True)
class LandingSummary:
    variant: str
    first_day: str
    last_day: str
    days: int
    rows: dict[str, int]


def read_generated(variant: str) -> dict[str, pd.DataFrame]:
    folder = generated_dir(variant)
    return {path.stem: pd.read_parquet(path) for path in sorted(folder.glob("*.parquet"))}


def day_of(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values).dt.normalize()


def order_events(orders: pd.DataFrame, shipments: pd.DataFrame, returns: pd.DataFrame) -> pd.DataFrame:
    """Status log of every order: placed, then paid or payment_failed, cancelled, shipped, delivered, returned."""
    order = orders.drop_duplicates("order_id")[
        ["order_id", "order_datetime", "order_status", "payment_method", "cancel_reason", "cancelled_at"]]
    placed = order.assign(event_type="placed", event_at=order["order_datetime"])
    failed = order[order["order_status"] == "payment_failed"]
    # Cash on delivery is collected by the courier; every other method is paid at checkout.
    paid = order[(order["order_status"] != "payment_failed") & (order["payment_method"] != "COD")]
    payment = pd.concat([
        failed.assign(event_type="payment_failed", event_at=failed["order_datetime"]),
        paid.assign(event_type="paid", event_at=paid["order_datetime"]),
    ])
    cancelled = order[order["order_status"] == "cancelled"]
    cancelled = cancelled.assign(event_type="cancelled", event_at=cancelled["cancelled_at"])
    shipped = shipments.assign(event_type="shipped", event_at=shipments["shipped_at"])
    delivered = shipments.assign(event_type="delivered", event_at=shipments["delivered_at"])
    returned_orders = order.loc[order["order_status"] == "returned", ["order_id"]]
    last_return = (returns[returns["return_status"] == "refunded"].groupby("order_id", as_index=False)["return_date"]
                   .max().merge(returned_orders, on="order_id"))
    # A return is registered during the day; it gets the end of that day so that it follows the delivery.
    returned = last_return.assign(event_type="returned",
                                  event_at=pd.to_datetime(last_return["return_date"]) + pd.Timedelta("23:59:59"))
    events = pd.concat([placed, payment, cancelled, shipped, delivered, returned], ignore_index=True)
    events.loc[events["event_type"] != "cancelled", "cancel_reason"] = None
    order_of_type = {name: rank for rank, name in enumerate(
        ["placed", "paid", "payment_failed", "cancelled", "shipped", "delivered", "returned"])}
    events["rank"] = events["event_type"].map(order_of_type)
    events = events.sort_values(["event_at", "order_id", "rank"], kind="stable")
    return events[TABLES["order_events"]].reset_index(drop=True)


def product_extracts(products: pd.DataFrame, prices: pd.DataFrame, first_day: pd.Timestamp) -> pd.DataFrame:
    """One product record per day it changes: launch (or initial export), new list price, end of sale."""
    launch = products[["product_id", "launch_date"]].assign(day=lambda f: f["launch_date"].clip(lower=first_day))
    price_days = prices[["product_id", "valid_from"]].rename(columns={"valid_from": "day"})
    ended = products.loc[products["discontinued_date"].notna(), ["product_id", "discontinued_date"]]
    ended = ended.rename(columns={"discontinued_date": "day"})
    days = pd.concat([launch[["product_id", "day"]], price_days, ended]).drop_duplicates().sort_values(
        ["day", "product_id"])
    days["day"] = day_of(days["day"])

    prices = prices.assign(valid_from=day_of(prices["valid_from"])).sort_values("valid_from")
    days = pd.merge_asof(days.sort_values("day"), prices[["product_id", "valid_from", "sales_price_gross",
                                                         "sales_price_net"]],
                         left_on="day", right_on="valid_from", by="product_id", direction="backward")
    record = products.drop(columns=["sales_price_gross", "sales_price_net"])
    extracts = days.merge(record, on="product_id", how="left")
    # The end of sale is known only from that day on.
    extracts.loc[extracts["discontinued_date"] > extracts["day"], "discontinued_date"] = pd.NaT
    return extracts.sort_values(["day", "product_id"], kind="stable").reset_index(drop=True)


def source_tables(generated: dict[str, pd.DataFrame]) -> tuple[dict[str, pd.DataFrame], pd.Timestamp]:
    """Every landing table with a `day` column: the day its file is dropped."""
    orders = generated["order_data"]
    first_day = day_of(orders["order_datetime"]).min()
    shipments, returns = generated["shipment_data"], generated["return_data"]
    order_day = orders.drop_duplicates("order_id").set_index("order_id")["order_datetime"]

    tables = {
        "customers": generated["customer_data"].assign(day=lambda f: f["signup_date"].clip(lower=first_day)),
        "products": product_extracts(generated["product_data"], generated["price_history"], first_day),
        "order_lines": orders.assign(day=orders["order_datetime"]),
        "order_events": (events := order_events(orders, shipments, returns)).assign(day=events["event_at"]),
        "payments": generated["payment_data"].assign(day=lambda f: f["order_id"].map(order_day)),
        "shipments": shipments.assign(day=shipments["shipped_at"]),
        "returns": returns.assign(day=returns["return_date"]),
        "reviews": generated["review_data"].assign(day=lambda f: f["review_date"]),
        "sessions": generated["session_data"].assign(day=lambda f: f["session_start"]),
        "campaigns": generated["campaign_data"].assign(day=lambda f: f["start_date"]),
    }
    for name, table in tables.items():
        table = table.copy()
        table["day"] = day_of(table["day"]).clip(lower=first_day)
        if table["day"].isna().any():
            raise ValueError(f"{name}: {int(table['day'].isna().sum())} rows have no day to land on")
        tables[name] = table
    return tables, first_day


def as_csv_frame(table: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Values as the source system writes them: ISO dates, whole numbers without a decimal point, empty for null."""
    out = pd.DataFrame(index=table.index)
    for column in columns:
        values = table[column]
        if pd.api.types.is_datetime64_any_dtype(values):
            times = values.dt.strftime("%Y-%m-%d %H:%M:%S")
            is_date = (values.dropna() == values.dropna().dt.normalize()).all() and column.endswith("_date")
            out[column] = values.dt.strftime("%Y-%m-%d") if is_date else times
        elif pd.api.types.is_bool_dtype(values):
            out[column] = values.map({True: "true", False: "false"})
        elif pd.api.types.is_float_dtype(values) and column.endswith("_id"):
            out[column] = values.astype("Int64").astype("string")
        else:
            out[column] = values.astype("string")
        out[column] = out[column].astype(object).where(values.notna().to_numpy(), None)
    return out


def write_day(folder: Path, day: str, frames: dict[str, pd.DataFrame]) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    files = {}
    for name, frame in frames.items():
        path = folder / f"{name}.csv"
        frame.to_csv(path, index=False, lineterminator="\n", encoding="utf-8")
        files[name] = {"rows": len(frame), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    manifest = {"extract_date": day, "files": files}
    # The manifest goes last: a day is complete only when it is there.
    (folder / MANIFEST).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def land(variant: str) -> LandingSummary:
    """Write every day of one variant to data/landing/<variant>/, replacing what was there."""
    tables, first_day = source_tables(read_generated(variant))
    last_day = max(table["day"].max() for table in tables.values())
    target = landing_dir(variant)
    shutil.rmtree(target, ignore_errors=True)
    grouped, empty = {}, {}
    for name, table in tables.items():
        frame = as_csv_frame(table, TABLES[name])
        grouped[name] = dict(tuple(frame.groupby(table["day"].to_numpy(), sort=True)))
        empty[name] = frame.iloc[0:0]
    for day in pd.date_range(first_day, last_day, freq="D"):
        frames = {name: grouped[name].get(day, empty[name]) for name in TABLES}
        write_day(target / day.strftime("%Y-%m-%d"), day.strftime("%Y-%m-%d"), frames)
    rows = {name: int(len(table)) for name, table in tables.items()}
    written = {name: sum(len(frame) for frame in grouped[name].values()) for name in TABLES}
    if written != rows:
        raise ValueError(f"Rows written {written} differ from the source tables {rows}")
    return LandingSummary(variant, first_day.strftime("%Y-%m-%d"), last_day.strftime("%Y-%m-%d"),
                          int((last_day - first_day).days) + 1, rows)


def landed_days(variant: str) -> list[str]:
    """Days whose files are complete (manifest present), in order."""
    folder = landing_dir(variant)
    if not folder.exists():
        return []
    return sorted(path.parent.name for path in folder.glob(f"*/{MANIFEST}"))

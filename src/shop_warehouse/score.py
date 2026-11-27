"""
Score the warehouse against the generator's answer key. This is the only module that reads truth: the injected
issues (quality_issue_data) and the generator's own tables. dbt never sees them.

For every injected issue the warehouse either
- fixed it: found it and keeps the true value,
- caught it: found it and keeps "unknown", because the true value is not in the data (a missing phone number),
- fixed it wrongly: found it but keeps another value than the true one,
- missed it: did not find it.
A detection with no injected issue behind it is a false alarm, except on a second account: a copy of a customer
carries the original's dirty values, so the same issue found there is a copy, not a false alarm.
"""
from __future__ import annotations

import re
from pathlib import Path

import duckdb
import pandas as pd

TABLE_NAMES = {"customer_data": "customers", "product_data": "products", "order_data": "order_lines"}
OUTCOMES = ["fixed", "caught", "wrong", "missed"]


def normalize(column: str, value) -> str | None:
    """One spelling per value, so that 720 731 397 and +48720731397 compare equal."""
    if value is None or (not isinstance(value, str) and pd.isna(value)) or value == "":
        return None
    text = str(value)
    if column == "phone_number":
        return re.sub(r"\D", "", text)[-9:]
    if column in {"net_purchase_price", "quantity", "age", "customer_id"}:
        return f"{float(text):.2f}"
    return text


def read_truth(generated: Path) -> pd.DataFrame:
    truth = pd.read_parquet(generated / "quality_issue_data.parquet")
    truth["table_name"] = truth["table_name"].map(TABLE_NAMES)
    return truth.rename(columns={"key_value": "record_key"})


def issue_outcomes(dq: pd.DataFrame, truth: pd.DataFrame) -> pd.DataFrame:
    """One row per injected issue with its outcome."""
    keys = ["table_name", "record_key", "column_name"]
    merged = truth.merge(dq, on=keys, how="left", indicator=True)
    found = merged["_merge"] == "both"
    kept = [normalize(c, v) for c, v in zip(merged["column_name"], merged["kept_value"], strict=True)]
    clean = [normalize(c, v) for c, v in zip(merged["column_name"], merged["clean_value"], strict=True)]
    outcome = []
    for is_found, issue, kept_value, clean_value in zip(found, merged["issue_type"], kept, clean, strict=True):
        if not is_found:
            outcome.append("missed")
        elif issue == "duplicate_row":
            outcome.append("fixed")  # the copy is removed; there is no value to compare
        elif kept_value is None:
            outcome.append("caught")
        elif kept_value == clean_value:
            outcome.append("fixed")
        else:
            outcome.append("wrong")
    merged["outcome"] = outcome
    return merged[["issue_id", *keys, "issue_type", "dirty_value", "clean_value", "rule", "kept_value", "outcome"]]


def false_alarms(dq: pd.DataFrame, truth: pd.DataFrame) -> pd.DataFrame:
    """Detections without an injected issue, split into copies on second accounts and real false alarms."""
    keys = ["table_name", "record_key", "column_name"]
    extra = dq.merge(truth[keys], on=keys, how="left", indicator=True)
    extra = extra[extra["_merge"] == "left_only"].drop(columns="_merge")
    duplicates = truth[truth["issue_type"] == "duplicate_customer"].set_index("record_key")["clean_value"]
    original = extra["record_key"].map(duplicates)
    original_issues = set(zip(truth["record_key"], truth["column_name"], strict=True))
    extra["is_copy"] = [
        table == "customers" and isinstance(orig, str) and (orig, column) in original_issues
        for table, orig, column in zip(extra["table_name"], original, extra["column_name"], strict=True)
    ]
    return extra


def quality_summary(con: duckdb.DuckDBPyConnection, generated: Path) -> dict:
    dq = con.execute("select * from quality.dq_issues").df()
    truth = read_truth(generated)
    outcomes = issue_outcomes(dq, truth)
    extra = false_alarms(dq, truth)
    by_type = (outcomes.groupby(["table_name", "column_name", "issue_type", "outcome"]).size()
               .unstack("outcome", fill_value=0).reindex(columns=OUTCOMES, fill_value=0).reset_index())
    by_type["injected"] = by_type[OUTCOMES].sum(axis=1)
    totals = {outcome: int(by_type[outcome].sum()) for outcome in OUTCOMES}
    return {
        "injected": int(len(truth)),
        "detections": int(len(dq)),
        **totals,
        "copies_on_second_accounts": int(extra["is_copy"].sum()),
        "false_alarms": int((~extra["is_copy"]).sum()),
        "by_issue": by_type.to_dict(orient="records"),
    }


def reconcile(con: duckdb.DuckDBPyConnection, generated: Path) -> dict:
    """Facts the warehouse assembled itself, checked against the generator's own tables."""
    g = generated.as_posix()
    checks = {}
    checks["order_status"] = con.execute(f"""
        select count(*), count(*) filter (where o.order_status = t.order_status)
        from core.fct_orders o join (select distinct order_id, order_status from '{g}/order_data.parquet') t
        using (order_id)""").fetchall()[0]
    checks["payment_status"] = con.execute(f"""
        select count(*), count(*) filter (where o.payment_status = t.payment_status)
        from core.fct_orders o join (select distinct order_id, payment_status from '{g}/order_data.parquet') t
        using (order_id)""").fetchall()[0]
    checks["is_late"] = con.execute(f"""
        select count(*), count(*) filter (where o.is_late = t.is_late)
        from core.fct_orders o join '{g}/shipment_data.parquet' t using (order_id)""").fetchall()[0]
    checks["price_on_order_day"] = con.execute("""
        select count(*), count(*) filter (where l.unit_price_gross = p.sales_price_gross)
        from core.fct_order_lines l join core.dim_product p using (product_version_id)""").fetchall()[0]
    checks["customers"] = con.execute(f"""
        select (select count(*) from '{g}/customer_data.parquet' where customer_id not in (
                    select cast(record_key as bigint) from quality.dq_issues where rule = 'duplicate_customer')),
               (select count(*) from core.dim_customer)""").fetchall()[0]
    return {name: {"checked": int(total), "agree": int(agree)} for name, (total, agree) in checks.items()}


def totals(con: duckdb.DuckDBPyConnection) -> dict:
    row = con.execute("""
        select round(sum(net_revenue), 2), round(sum(gross_margin), 2), sum(units_kept), sum(sold_orders)
        from marts.mart_daily_sales""").fetchall()[0]
    customers = con.execute("select count(*) from core.dim_customer").fetchall()[0][0]
    return {"net_revenue": float(row[0]), "gross_margin": float(row[1]), "units_kept": int(row[2]),
            "sold_orders": int(row[3]), "customers": int(customers)}


def naive_totals(con: duckdb.DuckDBPyConnection) -> dict:
    """What a report straight from the raw files would say: every copy counted, no fixes, accounts as customers."""
    row = con.execute("""
        with status as (select * from intermediate.int_order_status),
        lines as (
            select cast(l.quantity as integer) as quantity, cast(l.unit_price_net as double) as unit_price_net,
                   cast(l.discount_rate as double) as discount_rate, cast(l.order_line_id as bigint) as order_line_id,
                   cast(l.product_id as bigint) as product_id, cast(l.order_datetime as date) as order_date
            from raw.order_lines l join status s on s.order_id = cast(l.order_id as bigint)
            where s.order_status not in ('cancelled', 'payment_failed')
        ),
        refunds as (select order_line_id, sum(returned_quantity) as q from core.fct_returns
                    where return_status = 'refunded' group by 1),
        prices as (select cast(product_id as bigint) as product_id, cast(_extract_date as date) as valid_from,
                          cast(net_purchase_price as double) as cost from raw.products),
        costed as (
            select l.*, coalesce(r.q, 0) as refunded,
                   (select arg_max(p.cost, p.valid_from) from prices p
                    where p.product_id = l.product_id and p.valid_from <= l.order_date) as cost
            from lines l left join refunds r using (order_line_id)
        )
        select round(sum((quantity - refunded) * unit_price_net * (1 - discount_rate)), 2),
               round(sum((quantity - refunded) * (unit_price_net * (1 - discount_rate) - cost)), 2),
               sum(quantity - refunded)
        from costed""").fetchall()[0]
    accounts = con.execute("select count(distinct customer_id) from raw.customers").fetchall()[0][0]
    return {"net_revenue": float(row[0]), "gross_margin": float(row[1]), "units_kept": int(row[2]),
            "customers": int(accounts)}

import json

import pandas as pd

from shop_warehouse import landing


def test_every_day_has_every_file_and_a_manifest(landed):
    days = sorted(path.name for path in landed.iterdir())
    # Orders start on 2023-01-01; the last event is the return on 2023-01-05.
    assert days == ["2023-01-01", "2023-01-02", "2023-01-03", "2023-01-04", "2023-01-05"]
    for day in days:
        names = {path.name for path in (landed / day).iterdir()}
        assert names == {f"{table}.csv" for table in landing.TABLES} | {landing.MANIFEST}
        manifest = json.loads((landed / day / landing.MANIFEST).read_text(encoding="utf-8"))
        for table, info in manifest["files"].items():
            rows = len(pd.read_csv(landed / day / f"{table}.csv"))
            assert rows == info["rows"]


def test_files_hold_only_source_columns(landed):
    for table, columns in landing.TABLES.items():
        header = (landed / "2023-01-01" / f"{table}.csv").read_text(encoding="utf-8").splitlines()[0]
        assert header.split(",") == columns
        assert not {"is_fraud", "customer_segment", "true_churn_date", "order_status"} & set(columns)


def test_customers_before_the_first_day_land_in_the_initial_export(landed):
    first = pd.read_csv(landed / "2023-01-01" / "customers.csv")
    second = pd.read_csv(landed / "2023-01-02" / "customers.csv")
    assert first["customer_id"].tolist() == [100001]
    assert second["customer_id"].tolist() == [100002]


def test_order_events_end_in_the_final_status(generated):
    events = landing.order_events(generated["order_data"], generated["shipment_data"], generated["return_data"])
    by_order = events.groupby("order_id")["event_type"].apply(list).to_dict()
    assert by_order[100001] == ["placed", "paid", "shipped", "delivered"]
    # Cash on delivery: no payment event before the courier collects it.
    assert by_order[100002] == ["placed", "cancelled"]
    assert by_order[100003] == ["placed", "paid", "shipped", "delivered", "returned"]
    cancelled = events[events["event_type"] == "cancelled"].iloc[0]
    assert cancelled["cancel_reason"] == "customer_request"
    assert events.loc[events["event_type"] != "cancelled", "cancel_reason"].isna().all()


def test_product_record_lands_on_launch_price_change_and_end_of_sale(generated):
    first_day = pd.Timestamp("2023-01-01")
    extracts = landing.product_extracts(generated["product_data"], generated["price_history"], first_day)
    cream = extracts[extracts["product_id"] == 200001]
    assert cream["day"].dt.strftime("%Y-%m-%d").tolist() == ["2023-01-01", "2023-01-03"]
    assert cream["sales_price_gross"].tolist() == [123.0, 122.0]
    novel = extracts[extracts["product_id"] == 200002]
    assert novel["day"].dt.strftime("%Y-%m-%d").tolist() == ["2023-01-02", "2023-01-04"]
    # The end of sale is not known before it happens.
    assert novel["discontinued_date"].isna().tolist() == [True, False]


def test_csv_values_are_written_like_a_source_system():
    frame = pd.DataFrame({
        "signup_date": [pd.Timestamp("2023-01-02"), pd.NaT],
        "event_at": [pd.Timestamp("2023-01-02 10:00"), pd.Timestamp("2023-01-03")],
        "is_bulky": [True, False],
        "campaign_id": [1.0, None],
        "age": pd.array([30, pd.NA], dtype="Int64"),
    })
    out = landing.as_csv_frame(frame, list(frame.columns))
    assert out.iloc[0].tolist() == ["2023-01-02", "2023-01-02 10:00:00", "true", "1", "30"]
    assert out.iloc[1].tolist() == [None, "2023-01-03 00:00:00", "false", None, None]


def test_landing_twice_gives_the_same_bytes(tmp_path, monkeypatch, generated):
    monkeypatch.setattr(landing, "read_generated", lambda variant: generated)
    hashes = []
    for run in range(2):
        monkeypatch.setattr(landing, "landing_dir", lambda variant, run=run: tmp_path / str(run))
        landing.land("dirty")
        hashes.append({path.relative_to(tmp_path / str(run)).as_posix(): path.read_bytes()
                       for path in (tmp_path / str(run)).rglob("*") if path.is_file()})
    assert hashes[0] == hashes[1]

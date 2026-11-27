"""dbt on the tiny shop: a full build and a day-by-day build end in the same tables, and every dbt test passes."""
import duckdb
import pytest

from shop_warehouse import landing, pipeline


@pytest.fixture
def tiny(tmp_path, monkeypatch, landed):
    monkeypatch.setattr(pipeline, "landing_dir", lambda variant: landed)
    return tmp_path


def test_daily_build_equals_full_build(tiny):
    days = sorted(path.name for path in (tiny / "landing" / "dirty").iterdir())
    full = pipeline.build_full("dirty", days, tiny / "full.duckdb")
    assert not any(key.endswith((":error", ":fail", ":warn")) for key in full)
    pipeline.build_daily("dirty", days, tiny / "daily.duckdb")
    assert pipeline.fingerprint(tiny / "full.duckdb") == pipeline.fingerprint(tiny / "daily.duckdb")

    con = duckdb.connect(str(tiny / "full.duckdb"))
    statuses = dict(con.execute("select order_id, order_status from core.fct_orders").fetchall())
    assert statuses == {100001: "delivered", 100002: "cancelled", 100003: "returned"}
    payment = dict(con.execute("select order_id, payment_status from core.fct_orders").fetchall())
    assert payment == {100001: "paid", 100002: "unpaid", 100003: "refunded"}
    # The cream changed price on 2023-01-03: the order of that day takes the new version.
    versions = dict(con.execute("select order_line_id, product_version_id from core.fct_order_lines").fetchall())
    assert versions[1000001] == "200001-20230101" and versions[1000003] == "200001-20230103"
    kept = dict(con.execute("select order_line_id, kept_quantity from core.fct_order_lines").fetchall())
    assert kept == {1000001: 1, 1000002: 0, 1000003: 0}
    assert con.execute("select count(*) from quality.dq_issues").fetchall()[0][0] == 0
    con.close()


def test_a_day_that_fails_the_manifest_stops_the_build(tiny):
    days = sorted(path.name for path in (tiny / "landing" / "dirty").iterdir())
    (tiny / "landing" / "dirty" / days[1] / landing.MANIFEST).unlink()
    with pytest.raises(Exception, match="not complete"):
        pipeline.build_daily("dirty", days, tiny / "daily.duckdb")

import json

import pytest

from shop_warehouse import landing, load


def counts(con):
    return {table: con.execute(f"select count(*) from raw.{table}").fetchall()[0][0] for table in landing.TABLES}


def test_load_is_idempotent(tmp_path, landed):
    con = load.connect(tmp_path / "w.duckdb")
    days = landing.landed_days("dirty") or sorted(path.name for path in landed.iterdir())
    load.load_days(con, landed, days)
    once = counts(con)
    load.load_days(con, landed, days[1:3])
    load.load_days(con, landed, days)
    assert counts(con) == once
    assert once["order_lines"] == 3 and once["order_events"] == 11
    assert load.loaded_days(con) == days


def test_late_day_loads_into_the_same_tables(tmp_path, landed):
    days = sorted(path.name for path in landed.iterdir())
    in_order = load.connect(tmp_path / "a.duckdb")
    load.load_days(in_order, landed, days)
    late = load.connect(tmp_path / "b.duckdb")
    for day in [days[0], days[2], days[1], *days[3:]]:
        load.load_days(late, landed, [day])
    query = "select * from raw.order_events order by all"
    assert in_order.execute(query).fetchall() == late.execute(query).fetchall()


def test_raw_keeps_text_and_lineage(tmp_path, landed):
    con = load.connect(tmp_path / "w.duckdb")
    load.load_days(con, landed, ["2023-01-02"])
    row = con.execute("select quantity, _extract_date, _source_file from raw.order_lines").fetchall()[0]
    assert row[0] == "2" and str(row[1]) == "2023-01-02" and row[2] == "2023-01-02/order_lines.csv"
    columns = con.execute("select table_name, column_name, data_type from information_schema.columns "
                          "where table_schema = 'raw'").fetchall()
    types = {data_type for table, column, data_type in columns
             if table in landing.TABLES and not column.startswith("_")}
    assert types == {"VARCHAR"}


def test_changed_file_fails_and_leaves_the_warehouse_unchanged(tmp_path, landed):
    con = load.connect(tmp_path / "w.duckdb")
    load.load_days(con, landed, ["2023-01-01"])
    before = counts(con)
    path = landed / "2023-01-01" / "order_lines.csv"
    path.write_text(path.read_text(encoding="utf-8") + path.read_text(encoding="utf-8").splitlines()[1] + "\n",
                    encoding="utf-8")
    with pytest.raises(load.LandingError, match="SHA-256"):
        load.load_days(con, landed, ["2023-01-01"])
    assert counts(con) == before


def test_unexpected_columns_fail(tmp_path, landed):
    day = landed / "2023-01-02"
    path = day / "campaigns.csv"
    text = path.read_text(encoding="utf-8").replace("total_cost", "cost", 1)
    path.write_text(text, encoding="utf-8")
    manifest = json.loads((day / landing.MANIFEST).read_text(encoding="utf-8"))
    import hashlib

    manifest["files"]["campaigns"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (day / landing.MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(load.LandingError, match="columns"):
        load.load_days(load.connect(tmp_path / "w.duckdb"), landed, ["2023-01-02"])


def test_incomplete_day_fails(tmp_path, landed):
    (landed / "2023-01-03" / landing.MANIFEST).unlink()
    with pytest.raises(load.LandingError, match="not complete"):
        load.load_days(load.connect(tmp_path / "w.duckdb"), landed, ["2023-01-03"])

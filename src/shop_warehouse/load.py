"""
Load landed days into the warehouse's raw schema, exactly as written: every column as text, plus the extract date and
the file it came from. Types, cleaning and deduplication are the job of dbt staging.

Loading is idempotent: a day is deleted and inserted again in one transaction, so a rerun, a backfill or a late day
gives the same raw tables. Before anything is written, each file is checked against the day's manifest (row count,
SHA-256) and its header against the expected columns; a broken day fails the load and leaves the warehouse as it was.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Iterable
from pathlib import Path

import duckdb

from shop_warehouse.landing import MANIFEST, TABLES


class LandingError(RuntimeError):
    """A landed file does not match its manifest or the expected columns."""


LOG_TABLE = "raw._load_log"
DAY_IN_PATH = r"(\d{4}-\d{2}-\d{2})/[^/]+$"
FILE_IN_PATH = r"(\d{4}-\d{2}-\d{2}/[^/]+)$"


def connect(path: Path) -> duckdb.DuckDBPyConnection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    con.execute("create schema if not exists raw")
    for table, columns in TABLES.items():
        fields = ", ".join(f'"{column}" varchar' for column in columns)
        con.execute(f"create table if not exists raw.{table} ({fields}, _extract_date date, _source_file varchar)")
    con.execute(f"""create table if not exists {LOG_TABLE} (
        extract_date date, table_name varchar, row_count bigint, sha256 varchar, primary key (extract_date, table_name)
    )""")
    return con


def read_manifest(day_dir: Path) -> dict:
    path = day_dir / MANIFEST
    if not path.exists():
        raise LandingError(f"{day_dir.name}: no {MANIFEST}, the day is not complete")
    return json.loads(path.read_text(encoding="utf-8"))


def check_file(path: Path, expected: dict, columns: list[str]) -> None:
    data = path.read_bytes() if path.exists() else None
    if data is None:
        raise LandingError(f"{path.parent.name}/{path.name}: file missing")
    if hashlib.sha256(data).hexdigest() != expected["sha256"]:
        raise LandingError(f"{path.parent.name}/{path.name}: SHA-256 differs from the manifest")
    header = next(csv.reader([data.split(b"\n", 1)[0].decode("utf-8")]))
    if header != columns:
        raise LandingError(f"{path.parent.name}/{path.name}: columns {header} differ from {columns}")


def load_days(con: duckdb.DuckDBPyConnection, landing: Path, days: Iterable[str]) -> dict[str, int]:
    """Load the given days (YYYY-MM-DD) from one landing folder. Returns rows loaded per table."""
    days = sorted(set(days))
    if not days:
        return {}
    manifests = {day: read_manifest(landing / day) for day in days}
    for day, manifest in manifests.items():
        if manifest["extract_date"] != day:
            raise LandingError(f"{day}: manifest is for {manifest['extract_date']}")
        for table, columns in TABLES.items():
            check_file(landing / day / f"{table}.csv", manifest["files"][table], columns)

    loaded = {}
    con.execute("begin transaction")
    try:
        day_list = ", ".join(f"date '{day}'" for day in days)
        for table, columns in TABLES.items():
            files = [str(landing / day / f"{table}.csv").replace("\\", "/") for day in days]
            types = "{" + ", ".join(f"'{column}': 'VARCHAR'" for column in columns) + "}"
            select = ", ".join(f'"{column}"' for column in columns)
            con.execute(f"delete from raw.{table} where _extract_date in ({day_list})")
            con.execute(f"""
                insert into raw.{table}
                select {select},
                       cast(regexp_extract(filename, ?, 1) as date),
                       regexp_extract(filename, ?, 1)
                from read_csv(?, columns = {types}, header = true, auto_detect = false, filename = true,
                              delim = ',', quote = '"', escape = '"', nullstr = '')
            """, [DAY_IN_PATH, FILE_IN_PATH, files])
            counts = dict(con.execute(
                f"select cast(_extract_date as varchar), count(*) from raw.{table} "
                f"where _extract_date in ({day_list}) group by 1").fetchall())
            for day in days:
                expected = manifests[day]["files"][table]
                if counts.get(day, 0) != expected["rows"]:
                    raise LandingError(f"{day}/{table}.csv: loaded {counts.get(day, 0)} rows, manifest says "
                                       f"{expected['rows']}")
            con.execute(f"delete from {LOG_TABLE} where table_name = ? and extract_date in ({day_list})", [table])
            con.executemany(f"insert into {LOG_TABLE} values (?, ?, ?, ?)",
                            [[day, table, manifests[day]["files"][table]["rows"],
                              manifests[day]["files"][table]["sha256"]] for day in days])
            loaded[table] = sum(counts.values())
        con.execute("commit")
    except Exception:
        con.execute("rollback")
        raise
    return loaded


def loaded_days(con: duckdb.DuckDBPyConnection) -> list[str]:
    rows = con.execute(f"select distinct cast(extract_date as varchar) from {LOG_TABLE} order by 1").fetchall()
    return [row[0] for row in rows]

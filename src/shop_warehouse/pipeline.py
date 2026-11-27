"""
The steps of the warehouse, shared by main.py and the Airflow DAG: land the files, load days, run dbt, score.

Airflow calls one day at a time (load_day, then dbt_build with run_date); main.py either loads every day and builds
once (full) or replays days one by one like the DAG (daily). Both must end in the same tables.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from contextlib import contextmanager
from pathlib import Path

import duckdb

from shop_warehouse import landing, load, source
from shop_warehouse.config import DBT_DIR, generated_dir, landing_dir, warehouse_path

# Tables a reader of the warehouse uses; compared between a full and a daily build.
PUBLISHED_SCHEMAS = ("core", "marts", "quality")


class DbtError(RuntimeError):
    """dbt build ended with an error (a failing test with severity error or a broken model)."""


def landing_is_current(variant: str) -> bool:
    """The landing folder was written from the generated data that is in the cache now."""
    marker = landing_dir(variant) / "_source.json"
    info = generated_dir(variant) / "source.json"
    return marker.exists() and info.exists() and marker.read_bytes() == info.read_bytes()


def prepare(variants: list[str], overrides: dict | None = None) -> None:
    """Generate the shop (if needed) and write its daily files (if they are not from this generation)."""
    source.generate_all(overrides)
    for variant in variants:
        if landing_is_current(variant):
            continue
        summary = landing.land(variant)
        print(f"Landed {variant}: {summary.days} days ({summary.first_day} .. {summary.last_day})")
        shutil.copyfile(generated_dir(variant) / "source.json", landing_dir(variant) / "_source.json")


@contextmanager
def warehouse(variant: str, path: Path | None = None):
    con = load.connect(path or warehouse_path(variant))
    try:
        yield con
    finally:
        con.close()


def load_day(variant: str, day: str, path: Path | None = None) -> dict[str, int]:
    with warehouse(variant, path) as con:
        return load.load_days(con, landing_dir(variant), [day])


def load_all(variant: str, days: list[str] | None = None, path: Path | None = None) -> list[str]:
    days = days if days is not None else landing.landed_days(variant)
    with warehouse(variant, path) as con:
        load.load_days(con, landing_dir(variant), days)
    return days


def dbt_build(variant: str, run_date: str | None = None, path: Path | None = None, full_refresh: bool = False,
              select: str | None = None) -> dict:
    """Run dbt build on one warehouse. Returns test counts by status; raises DbtError on any error."""
    from dbt.cli.main import dbtRunner

    os.environ["SHOP_DWH_WAREHOUSE"] = str(path or warehouse_path(variant))
    args = ["build", "--project-dir", str(DBT_DIR), "--profiles-dir", str(DBT_DIR), "--quiet", "--no-use-colors"]
    if run_date:
        args += ["--vars", json.dumps({"run_date": run_date})]
    if full_refresh:
        args.append("--full-refresh")
    if select:
        args += ["--select", select]
    result = dbtRunner().invoke(args)
    if result.exception is not None:
        raise DbtError(str(result.exception))
    statuses: dict[str, int] = {}
    for node in result.result or []:
        key = f"{node.node.resource_type}:{node.status}"
        statuses[key] = statuses.get(key, 0) + 1
    if not result.success:
        failed = [node.node.name for node in result.result if str(node.status) in {"error", "fail"}]
        raise DbtError(f"dbt build failed: {failed}")
    return dict(sorted(statuses.items()))


def build_full(variant: str, days: list[str] | None = None, path: Path | None = None) -> dict:
    """A warehouse from scratch: every landed day loaded at once, then one full dbt build."""
    target = path or warehouse_path(variant)
    target.unlink(missing_ok=True)
    load_all(variant, days, target)
    return dbt_build(variant, path=target, full_refresh=True)


def build_daily(variant: str, days: list[str], path: Path | None = None) -> dict:
    """A warehouse built the way the DAG builds it: load a day, run dbt for that day, next day."""
    target = path or warehouse_path(variant)
    target.unlink(missing_ok=True)
    statuses = {}
    for day in days:
        load_day(variant, day, target)
        statuses = dbt_build(variant, run_date=day, path=target)
    return statuses


def fingerprint(path: Path) -> dict[str, str]:
    """SHA-256 of every published table, rows in a fixed order: equal fingerprints mean equal tables."""
    con = duckdb.connect(str(path))  # same configuration as the connection dbt keeps open
    try:
        tables = con.execute(
            "select table_schema, table_name from information_schema.tables where table_schema in "
            f"({', '.join(repr(s) for s in PUBLISHED_SCHEMAS)}) and table_type = 'BASE TABLE' order by 1, 2"
        ).fetchall()
        prints = {}
        for schema, table in tables:
            rows = con.execute(f"select * from {schema}.{table} order by all").fetchall()
            prints[f"{schema}.{table}"] = hashlib.sha256(repr(rows).encode("utf-8")).hexdigest()
        return prints
    finally:
        con.close()

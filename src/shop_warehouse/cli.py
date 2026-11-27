"""
Command line steps of the warehouse; the Airflow DAG calls these with the project's own Python, so Airflow and dbt
live in separate environments.

    python -m shop_warehouse.cli prepare [--small]         generate the shop and land its daily files
    python -m shop_warehouse.cli is-landed 2023-01-05      exit 0 when the day's manifest is there
    python -m shop_warehouse.cli load-day 2023-01-05       load one day into raw
    python -m shop_warehouse.cli dbt-build 2023-01-05      dbt build for that day (incremental models)
    python -m shop_warehouse.cli compare-full [--expect-days 5]   the warehouse equals a full build of its days
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from shop_warehouse import landing, load, pipeline
from shop_warehouse.config import VARIANTS, landing_dir, warehouse_path

# A shop small enough for CI: one year with 3,000 order lines (the generator needs a few seconds).
SMALL_SHOP = {"start_year": 2023, "end_year": 2023, "order_data_rows": 3000, "customer_data_rows": 2000,
              "product_data_rows": 1500}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="shop_warehouse.cli", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--variant", default="dirty", choices=list(VARIANTS))
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--small", action="store_true", help="a small shop for CI")
    for name in ("is-landed", "load-day", "dbt-build"):
        commands.add_parser(name).add_argument("day")
    compare = commands.add_parser("compare-full")
    compare.add_argument("--expect-days", type=int, help="fail unless exactly this many days are loaded")
    args = parser.parse_args(argv)

    if args.command == "prepare":
        pipeline.prepare([args.variant], SMALL_SHOP if args.small else None)
        print(f"{len(landing.landed_days(args.variant))} days landed in {landing_dir(args.variant)}")
    elif args.command == "is-landed":
        return 0 if (landing_dir(args.variant) / args.day / landing.MANIFEST).exists() else 1
    elif args.command == "load-day":
        rows = pipeline.load_day(args.variant, args.day)
        print(json.dumps({"day": args.day, "rows": rows}))
    elif args.command == "dbt-build":
        print(json.dumps({"day": args.day, "dbt": pipeline.dbt_build(args.variant, run_date=args.day)}))
    elif args.command == "compare-full":
        with pipeline.warehouse(args.variant) as con:
            days = load.loaded_days(con)
        with tempfile.TemporaryDirectory() as folder:
            full = Path(folder) / "full.duckdb"
            pipeline.build_full(args.variant, days, full)
            expected, actual = pipeline.fingerprint(full), pipeline.fingerprint(warehouse_path(args.variant))
        differ = sorted(name for name in expected if expected[name] != actual.get(name))
        print(json.dumps({"days": len(days), "tables": len(expected), "tables_that_differ": differ}))
        wrong_days = args.expect_days is not None and len(days) != args.expect_days
        return 1 if differ or wrong_days else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())

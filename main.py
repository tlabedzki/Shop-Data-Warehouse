"""
Build the shop's warehouse from scratch and score it against the answer key.

    python main.py                    # generate, land, load, dbt build (dirty and clean shop), score
    python main.py --daily --days 14  # also replay the first 14 days one by one, like Airflow, and compare

Results go to output/results.json (no timings, so a second run writes the same bytes).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from shop_warehouse import landing, pipeline, score  # noqa: E402
from shop_warehouse.config import OUTPUT_ROOT, VARIANTS, generated_dir, warehouse_path  # noqa: E402

RESULTS = OUTPUT_ROOT / "results.json"


def build_and_score() -> dict:
    results = {"variants": {}}
    for variant in VARIANTS:
        started = time.perf_counter()
        tests = pipeline.build_full(variant)
        print(f"{variant}: warehouse built in {time.perf_counter() - started:.0f} s, dbt {tests}")
        with pipeline.warehouse(variant) as con:
            results["variants"][variant] = {
                "days": len(landing.landed_days(variant)),
                "dbt": tests,
                "quality": score.quality_summary(con, generated_dir(variant)),
                "reconcile": score.reconcile(con, generated_dir(variant)),
                "totals": score.totals(con),
                "raw_totals": score.naive_totals(con),
            }
    return results


def replay_daily(days: int) -> dict:
    """Build the first N days twice: all at once, and day by day as the DAG does. The tables must be equal."""
    variant = "dirty"
    chosen = landing.landed_days(variant)[:days]
    folder = warehouse_path(variant).parent
    full, daily = folder / f"full-{days}d.duckdb", folder / f"daily-{days}d.duckdb"
    started = time.perf_counter()
    pipeline.build_full(variant, chosen, full)
    pipeline.build_daily(variant, chosen, daily)
    print(f"Replayed {days} days in {time.perf_counter() - started:.0f} s")
    full_print, daily_print = pipeline.fingerprint(full), pipeline.fingerprint(daily)
    differ = sorted(name for name in full_print if full_print[name] != daily_print.get(name))
    return {"variant": variant, "days": days, "first_day": chosen[0], "last_day": chosen[-1],
            "tables": len(full_print), "tables_that_differ": differ, "daily_equals_full": not differ}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--daily", action="store_true", help="also replay days one by one and compare")
    parser.add_argument("--days", type=int, default=14, help="days to replay with --daily (default 14)")
    args = parser.parse_args()

    pipeline.prepare(list(VARIANTS))
    results = build_and_score()
    if args.daily:
        results["daily_replay"] = replay_daily(args.days)
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    quality = results["variants"]["dirty"]["quality"]
    print(f"Injected issues: {quality['injected']:,}; fixed {quality['fixed']:,}, caught {quality['caught']:,}, "
          f"fixed wrongly {quality['wrong']}, missed {quality['missed']}; false alarms {quality['false_alarms']}")
    print(f"Clean shop: {results['variants']['clean']['quality']['detections']} detections")
    if args.daily:
        replay = results["daily_replay"]
        print(f"Daily replay of {replay['days']} days equals the full build: {replay['daily_equals_full']}")
    print(f"Results: {RESULTS.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

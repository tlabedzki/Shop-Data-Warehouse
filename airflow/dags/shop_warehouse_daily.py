"""
Daily load of the shop's warehouse.

One run per extract date: wait until the shop's files for the day are complete (the manifest is written last), load
them into the raw schema, run dbt build for that day, check the result. Runs go one at a time (DuckDB has one
writer) and catch up from the first day, so a new deployment backfills the whole history; rerunning a day gives the
same tables because loading and the incremental models replace that day's data.

Airflow and dbt need different package versions, so the tasks call the project's own Python (SHOP_DWH_PYTHON) and
its command line steps (shop_warehouse.cli). The landing folder and warehouse path come from SHOP_DWH_LANDING and
SHOP_DWH_OUTPUT, the same settings main.py uses.
"""
from __future__ import annotations

import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import dag, task

PYTHON = os.environ.get("SHOP_DWH_PYTHON", "python")
VARIANT = os.environ.get("SHOP_DWH_VARIANT", "dirty")
SRC = str(Path(__file__).resolve().parents[2] / "src")
CLI = f'"{PYTHON}" -m shop_warehouse.cli --variant {VARIANT}'
# The project's code is on the path of the commands; everything else in the environment is passed through.
ENV = {"PYTHONPATH": SRC, "PYTHONIOENCODING": "utf-8"}


@dag(
    dag_id="shop_warehouse",
    description="Load the shop's daily files into DuckDB and run dbt build for the day",
    schedule="@daily",
    start_date=datetime(2023, 1, 1),
    end_date=datetime(2025, 2, 14),
    catchup=True,
    max_active_runs=1,
    default_args={"retries": 1, "retry_delay": timedelta(minutes=5)},
    tags=["shop", "dbt", "duckdb"],
)
def shop_warehouse():
    @task.sensor(poke_interval=300, timeout=24 * 3600, mode="reschedule")
    def wait_for_files(ds=None) -> bool:
        """The day's files are complete when its manifest is there."""
        command = [PYTHON, "-m", "shop_warehouse.cli", "--variant", VARIANT, "is-landed", ds]
        return subprocess.run(command, env={**os.environ, **ENV}).returncode == 0

    load_day = BashOperator(task_id="load_day", bash_command=f"{CLI} load-day {{{{ ds }}}}", env=ENV,
                            append_env=True)
    dbt_build = BashOperator(task_id="dbt_build", bash_command=f"{CLI} dbt-build {{{{ ds }}}}", env=ENV,
                             append_env=True)

    wait_for_files() >> load_day >> dbt_build


daily = shop_warehouse()

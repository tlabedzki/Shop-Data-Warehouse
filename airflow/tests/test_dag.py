"""The DAG imports in a real Airflow and has the shape the warehouse needs. Runs in the Airflow environment (CI)."""
import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("airflow")

DAG_FILE = Path(__file__).resolve().parents[1] / "dags" / "shop_warehouse_daily.py"


@pytest.fixture(scope="module")
def dag():
    spec = importlib.util.spec_from_file_location("shop_warehouse_daily", DAG_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.daily


def test_tasks_run_in_order(dag):
    assert set(dag.task_ids) == {"wait_for_files", "load_day", "dbt_build"}
    assert dag.get_task("wait_for_files").downstream_task_ids == {"load_day"}
    assert dag.get_task("load_day").downstream_task_ids == {"dbt_build"}


def test_one_run_at_a_time_and_catch_up(dag):
    # DuckDB has a single writer, and a new deployment must backfill from the first day.
    assert dag.max_active_runs == 1
    assert dag.catchup is True
    assert str(dag.start_date.date()) == "2023-01-01"


def test_tasks_call_the_project_command_line(dag):
    assert "load-day {{ ds }}" in dag.get_task("load_day").bash_command
    assert "dbt-build {{ ds }}" in dag.get_task("dbt_build").bash_command

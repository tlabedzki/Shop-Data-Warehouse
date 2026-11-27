"""Paths and settings shared by the pipeline steps."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DATA_GENERATOR_URL = "https://github.com/tlabedzki/Data-Generator.git"
DATA_GENERATOR_TAG = "v1.7.1"
SEED = 42

# Two runs of the same shop: "dirty" has injected data quality issues, "clean" is the negative control.
VARIANTS = {"dirty": "medium", "clean": "none"}

# Data-Generator tables the shop's source systems are built from (truth tables stay out of the warehouse).
GENERATED_TABLES = [
    "customer_data", "product_data", "order_data", "price_history", "shipment_data", "return_data", "payment_data",
    "review_data", "campaign_data", "session_data", "quality_issue_data",
]


def env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value) if value else default


CACHE_DIR = env_path("SHOP_DWH_CACHE", ROOT / ".cache")
LANDING_ROOT = env_path("SHOP_DWH_LANDING", ROOT / "data" / "landing")
OUTPUT_ROOT = env_path("SHOP_DWH_OUTPUT", ROOT / "output")
DBT_DIR = ROOT / "dbt"


def generated_dir(variant: str) -> Path:
    """Data-Generator output of one variant (Parquet, as the generator writes it)."""
    return CACHE_DIR / "generated" / variant


def landing_dir(variant: str) -> Path:
    """Daily CSV files the shop's systems drop: <landing>/<variant>/<YYYY-MM-DD>/<table>.csv."""
    return LANDING_ROOT / variant


def warehouse_path(variant: str) -> Path:
    return OUTPUT_ROOT / variant / "warehouse.duckdb"

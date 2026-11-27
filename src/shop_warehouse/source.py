"""
Generate the shop with Data-Generator: clone a release, run it with this project's settings and save the tables the
shop's source systems are built from. The generator code is not changed; settings are overridden in the process that
runs it (as the Data-Generator app does).

Both variants use the same seed. Data quality issues come from their own random stream in the generator, so the
clean variant is the same shop without the injected issues: the negative control and the answer key for cleaning.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from shop_warehouse.config import (
    CACHE_DIR,
    DATA_GENERATOR_TAG,
    DATA_GENERATOR_URL,
    GENERATED_TABLES,
    SEED,
    VARIANTS,
    generated_dir,
)

# Runs inside the Data-Generator clone: override the settings, generate, save the tables as Parquet.
RUN_SCRIPT = """
import json, sys
from pathlib import Path
import settings.main_settings as s
import settings.quality_settings as q
overrides, quality_level, tables, out = json.loads(sys.argv[1]), sys.argv[2], json.loads(sys.argv[3]), Path(sys.argv[4])
for name, value in overrides.items():
    setattr(s, name, value)
q.data_quality_level = quality_level
s.generated_files = list(tables)
from func import generator, log
log.configure()
data = generator.run_generation_pipeline()
out.mkdir(parents=True, exist_ok=True)
for table in tables:
    data[table].to_parquet(out / f"{table}.parquet", index=False)
"""


def run(command: list[str], cwd: Path | None = None) -> str:
    env = {**os.environ, "MPLBACKEND": "Agg", "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(command[:3])} ...\n{result.stderr[-2000:]}")
    return result.stdout


def clone(source: str = DATA_GENERATOR_URL, tag: str = DATA_GENERATOR_TAG, refresh: bool = False) -> Path:
    target = CACHE_DIR / f"data-generator-{re.sub(r'[^A-Za-z0-9._-]', '-', tag)}"
    if refresh or not (target / "main.py").exists():
        shutil.rmtree(target, ignore_errors=True)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        print(f"Cloning Data-Generator {tag} from {source}")
        run(["git", "-c", "advice.detachedHead=false", "clone", "--quiet", "--depth", "1", "--branch", tag,
             source, str(target)])
    return target


def generate(generator_dir: Path, variant: str, overrides: dict | None = None, source: str = DATA_GENERATOR_URL,
             tag: str = DATA_GENERATOR_TAG) -> Path:
    """Generate one variant into .cache/generated/<variant>/ and record where it came from."""
    target = generated_dir(variant)
    settings = {"random_state": SEED, "data_language": "en", **(overrides or {})}
    quality_level = VARIANTS[variant]
    print(f"Generating the {variant} shop (data quality level {quality_level})")
    shutil.rmtree(target, ignore_errors=True)
    run([sys.executable, "-c", RUN_SCRIPT, json.dumps(settings), quality_level, json.dumps(GENERATED_TABLES),
         str(target)], cwd=generator_dir)
    commit = run(["git", "rev-parse", "HEAD"], cwd=generator_dir).strip()
    info = {"repository": source, "tag": tag, "commit": commit, "settings": settings,
            "data_quality_level": quality_level}
    (target / "source.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    return target


def is_generated(variant: str, overrides: dict | None = None, source: str = DATA_GENERATOR_URL,
                 tag: str = DATA_GENERATOR_TAG) -> bool:
    info_path = generated_dir(variant) / "source.json"
    if not info_path.exists():
        return False
    info = json.loads(info_path.read_text(encoding="utf-8"))
    wanted = {"random_state": SEED, "data_language": "en", **(overrides or {})}
    return info.get("repository") == source and info.get("tag") == tag and info.get("settings") == wanted


def generate_all(overrides: dict | None = None, source: str = DATA_GENERATOR_URL, tag: str = DATA_GENERATOR_TAG,
                 force: bool = False, variants: list[str] | None = None) -> None:
    pending = [variant for variant in (variants or VARIANTS)
               if force or not is_generated(variant, overrides, source, tag)]
    if not pending:
        return
    generator_dir = clone(source, tag)
    for variant in pending:
        generate(generator_dir, variant, overrides, source, tag)

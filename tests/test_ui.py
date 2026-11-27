"""The Dash app (ui/) and the shared report and figures, on made-up results (CI has no warehouse)."""
import re
from functools import cache

import pandas as pd
import pytest

from shop_warehouse import figures, report, theme
from shop_warehouse.config import ROOT

ASSETS = ROOT / "ui" / "assets"


def issue(table, column, kind, injected, fixed, caught, wrong=0, missed=0):
    return {"table_name": table, "column_name": column, "issue_type": kind, "injected": injected, "fixed": fixed,
            "caught": caught, "wrong": wrong, "missed": missed}


def variant(detections, by_issue, raw_factor):
    totals = {"net_revenue": 1000.0, "gross_margin": 300.0, "units_kept": 50, "sold_orders": 40, "customers": 20}
    raw = {key: value * raw_factor for key, value in totals.items() if key != "sold_orders"}
    quality = {"injected": sum(i["injected"] for i in by_issue), "detections": detections,
               "fixed": sum(i["fixed"] for i in by_issue), "caught": sum(i["caught"] for i in by_issue),
               "wrong": 0, "missed": 0, "copies_on_second_accounts": 2, "false_alarms": 0, "by_issue": by_issue}
    return {"days": 5, "dbt": {"model:success": 27, "test:pass": 100, "test:warn": len(by_issue),
                               "unit_test:pass": 5},
            "quality": quality, "reconcile": {"order_status": {"checked": 10, "agree": 10}},
            "totals": totals, "raw_totals": raw}


@pytest.fixture
def results():
    by_issue = [issue("customers", "phone_number", "format", 4, 4, 0),
                issue("products", "color", "missing", 2, 0, 2),
                issue("order_lines", "quantity", "outlier", 3, 2, 1)]
    clean = variant(0, [], 1.0)
    clean["dbt"] = {"model:success": 27, "test:pass": 105, "unit_test:pass": 5}
    return {"variants": {"dirty": variant(11, by_issue, 1.5), "clean": clean},
            "daily_replay": {"days": 3, "tables": 13, "daily_equals_full": True}}


@pytest.fixture
def prepared(results):
    months = pd.date_range("2023-01-01", periods=4, freq="MS")
    base = [10.0, 20.0, 30.0, 40.0]
    monthly = pd.DataFrame({"month": months, **{f"{m}_{side}": [v * (1.5 if side == "raw" else 1) for v in base]
                                                for m in report.METRICS for side in ("warehouse", "raw")}})
    loads = pd.DataFrame({"day": pd.date_range("2023-01-01", periods=5), "order_lines": [1, 4, 2, 3, 0],
                          "order_events": [2, 5, 3, 4, 1], "sessions": [9, 9, 9, 9, 9]})
    layers = pd.DataFrame([{"layer": name, "tables": 2, "rows": 10, "note": en, "note_pl": pl}
                           for name, en, pl in report.LAYERS])
    return {"results": results, "monthly": monthly, "loads": loads, "layers": layers}


@pytest.fixture
def ui_app(prepared, monkeypatch):
    from ui import app

    monkeypatch.setattr(app, "prepare", cache(lambda: prepared))
    return app


def walk(component):
    stack = [component]
    while stack:
        node = stack.pop()
        if isinstance(node, list | tuple):
            stack.extend(node)
            continue
        if not hasattr(node, "to_plotly_json"):
            continue
        yield node
        stack.append(getattr(node, "children", None))


def text_of(component) -> str:
    if isinstance(component, str | int | float):
        return str(component)
    if isinstance(component, list | tuple):
        return " ".join(text_of(c) for c in component)
    return text_of(getattr(component, "children", "") or "")


def test_page_has_the_four_sections(ui_app):
    found = {node.id for node in walk(ui_app.page()) if isinstance(getattr(node, "id", None), str)}
    assert {"loads", "quality", "raw-files", "proof", "quality-table", "quality-view", "metric", "gap-view"} <= found


def test_page_without_results_says_what_to_run(monkeypatch):
    from ui import app

    def missing():
        raise FileNotFoundError("No results yet. Run: python main.py")

    monkeypatch.setattr(app, "prepare", missing)
    assert "python main.py" in text_of(app.page())


def test_table_filter_shows_only_that_table(ui_app):
    view = ui_app.update_quality("products")
    assert "All 2 injected issues found, 0 fixed" in text_of(view)
    assert "Phone written another way" not in text_of(view)
    assert "Phone written another way" in text_of(ui_app.update_quality("all"))


def test_metric_switch_shows_the_gap(ui_app):
    assert "+50%" in text_of(ui_app.update_gap("units_kept"))
    assert "overstates net revenue by 50%" in text_of(ui_app.update_gap("unknown"))


def test_polish_words_and_numbers(results):
    frame = report.quality_frame(results, language="pl")
    assert "Telefon zapisany inaczej" in frame["problem"].tolist()
    assert report.quality_title(frame, "pl")[0] == "Hurtownia znajduje każdy z 9 wstrzykniętych błędów i naprawia 6"
    assert report.compact(35_728_153.84, "pl") == "35,7 mln" and report.compact(35_728_153.84) == "35.7M"
    assert report.integer(13451, "pl") == "13 451" and report.percent(0.7, "pl", signed=True) == "+70%"


def test_figures_build_in_both_languages(prepared, results):
    for language in report.LANGUAGES:
        frame = report.quality_frame(results, language=language)
        assert len(figures.quality_bars(frame, language).data) == 4
        assert len(figures.monthly_lines(prepared["monthly"], "net_revenue", language).data) == 2
        assert figures.loads_area(prepared["loads"], language).data[1].text == ("4",)


def test_inter_comes_from_files_in_the_repo_and_no_font_service():
    css = (ASSETS / "fonts.css").read_text(encoding="utf-8")
    urls = re.findall(r"url\('([^']+)'\)", css)
    assert len(urls) == 2 and all((ASSETS / url).is_file() for url in urls)
    assert (ASSETS / "fonts" / "OFL-inter.txt").is_file()
    for path in [*ASSETS.rglob("*.css"), *(ROOT / "ui").glob("*.py")]:
        text = path.read_text(encoding="utf-8")
        assert "googleapis" not in text and "gstatic" not in text, path


def test_style_sheet_tokens_match_the_shared_colours():
    css = (ASSETS / "style.css").read_text(encoding="utf-8")
    tokens = dict(re.findall(r"--dg-([a-z-]+):\s*([^;]+);", css))
    assert tokens["teal"] == theme.PRIMARY == "#006e79"
    assert tokens["copper"] == theme.ACCENT == "#c7692c"
    assert tokens["ink"] == theme.INK and tokens["text"] == theme.TEXT and tokens["muted"] == theme.MUTED
    assert tokens["line"] == theme.LINE and tokens["wash"] == theme.WASH
    assert "'tnum' 1" in tokens["num-features"]

"""
Dash + Mantine app of Shop Data Warehouse, in the portfolio look of Data-Generator: the daily loads and the layers,
every injected data quality issue against the answer key, what a report straight from the raw files would say, and
the proofs (clean shop, reconciliation with the generator, daily runs equal to a full build).

Run locally (from the repository root), after python main.py:
    python -m ui.app            # http://127.0.0.1:8050

The server listens on 127.0.0.1 only and reads the warehouse read-only.
"""
from __future__ import annotations

import os
import sys
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import dash._dash_renderer  # noqa: E402
import dash_mantine_components as dmc  # noqa: E402
from dash import Dash, Input, Output, dcc, html  # noqa: E402

from shop_warehouse import figures, report  # noqa: E402
from ui import theme as t  # noqa: E402

dash._dash_renderer._set_react_version("19.2.4")  # Mantine 3 needs React 19; Dash 4.5 still defaults to 18

REPO_URL = "https://github.com/tlabedzki/Shop-Data-Warehouse"
ALL_TABLES = "all"
TABLE_CHOICES = [{"value": ALL_TABLES, "label": "All tables"}] + [
    {"value": key, "label": label} for key, label in report.TABLE_LABELS["en"].items()]
METRIC_CHOICES = [{"value": key, "label": labels["en"][0]} for key, labels in report.METRICS.items()]
QUALITY_COLUMNS = [  # column, header, css class
    ("problem", "Issue in the files", "sw-wrap"), ("table", "Table", ""), ("action", "Warehouse", "sw-wrap"),
    ("injected", "Injected", "sw-num"), ("fixed", "Fixed", "sw-num"), ("caught", "Kept unknown", "sw-num"),
    ("missed", "Missed", "sw-num"), ("wrong", "Fixed wrongly", "sw-num"),
]


@cache
def prepare() -> dict:
    """Everything the page shows, computed once from results.json and the dirty shop's warehouse."""
    results = report.load_results()
    con = report.connect("dirty")
    try:
        return {"results": results, "monthly": report.monthly(con), "loads": report.loads(con),
                "layers": report.layers(con)}
    finally:
        con.close()


# ---------------------------------------------------------------------------------------------------------------- #
# Building blocks

def section(number, title, lead, body, section_id):
    return html.Section([
        html.Div([html.Span(f"{number:02d}", className="dg-step"), html.H2(title, className="dg-h2")],
                 className="dg-section-head"),
        dmc.Text(lead, className="dg-lead-small"),
        html.Div(body, id=f"{section_id}-body"),
    ], id=section_id, className="dg-section")


def stat(label, value, note="", extra_class=""):
    return html.Div([html.Div(value, className="dg-stat-value"), html.Div(label, className="dg-stat-label"),
                     html.Div(note, className="dg-stat-note")], className=f"dg-stat {extra_class}".strip())


def chart_block(text, figure, extra_class=""):
    title, subtitle = text
    return html.Figure([
        html.Figcaption([html.Div(title, className="dg-chart-title"), html.Div(subtitle, className="dg-chart-sub")]),
        dcc.Graph(figure=figure, config=figures.CONFIG, className="dg-graph",
                  style={"height": f"{figure.layout.height}px"}),
    ], className=f"dg-chart {extra_class}".strip())


def scroll_table(header, rows, label):
    table = html.Table([html.Thead(html.Tr(header)), html.Tbody(rows)], className="dg-table sw-table")
    return html.Div(table, className="dg-table-scroll", tabIndex="0", role="region", **{"aria-label": label})


# ---------------------------------------------------------------------------------------------------------------- #
# Views (pure functions of the prepared data, tested without a browser)

def loads_view(data: dict) -> list:
    results, layers = data["results"], data["layers"]
    dirty = results["variants"]["dirty"]
    raw_rows = int(layers.loc[layers["layer"] == "raw", "rows"].iloc[0])
    counts = report.dbt_counts(results, "dirty")
    stats = html.Div([
        stat("daily drops loaded", f"{dirty['days']:,}", "10 CSV files and a manifest each"),
        stat("rows in raw", report.compact(raw_rows), "as text, with the file they came from"),
        stat("dbt models", f"{counts['models']:,}", "staging to marts"),
        stat("dbt tests", f"{counts['pass'] + counts['warn']:,}", f"and {counts['unit']} unit tests"),
    ], className="dg-stats sw-stats-4")
    layer_cards = html.Div([
        html.Div([html.Div(row["layer"], className="sw-layer-name"),
                  html.Div(report.compact(row["rows"]), className="sw-layer-rows"),
                  html.Div(f"{row['tables']} tables: {row['note']}", className="sw-layer-note")],
                 className="sw-layer")
        for row in layers.to_dict("records")
    ], className="sw-layers sw-block")
    chart = chart_block(report.loads_title(data["loads"]), figures.loads_area(data["loads"]), "sw-chart-gap")
    return [stats, layer_cards, chart]


def quality_stats(results: dict) -> html.Div:
    quality = results["variants"]["dirty"]["quality"]
    missed = quality["missed"] + quality["wrong"]
    return html.Div([
        stat("issues injected", f"{quality['injected']:,}", "listed by the generator with the true value"),
        stat("fixed", f"{quality['fixed']:,}", "the true value is back"),
        stat("found, kept unknown", f"{quality['caught']:,}", "the true value is not in the data"),
        stat("missed or fixed wrongly", f"{missed:,}", "", "sw-accent" if missed else ""),
        stat("false alarms", f"{quality['false_alarms']:,}",
             f"{quality['copies_on_second_accounts']:,} copies on second accounts"),
    ], className="dg-stats")


def quality_view(results: dict, table: str | None) -> list:
    frame = report.quality_frame(results, None if table in (None, ALL_TABLES) else table)
    rows = []
    for record in frame.to_dict("records"):
        cells = []
        for column, _, css in QUALITY_COLUMNS:
            value = record[column]
            if column == "table":
                value = report.TABLE_LABELS["en"][value]
            classes = css
            if column in ("missed", "wrong"):
                classes += " sw-alert" if value else " sw-zero"
            cells.append(html.Td(f"{value:,}" if isinstance(value, int) else value, className=classes.strip() or None))
        rows.append(html.Tr(cells))
    header = [html.Th(name, className=css or None) for _, name, css in QUALITY_COLUMNS]
    return [
        chart_block(report.quality_title(frame), figures.quality_bars(frame)),
        scroll_table(header, rows, "Injected issues by kind, scrolls in both directions"),
    ]


def gap_view(data: dict, metric: str) -> list:
    results = data["results"]
    label, unit = report.METRICS[metric]["en"]
    warehouse = results["variants"]["dirty"]["totals"][metric]
    raw = results["variants"]["dirty"]["raw_totals"][metric]
    stats = html.Div([
        stat(f"{label.lower()}, warehouse", report.compact(warehouse), unit),
        stat(f"{label.lower()}, raw files", report.compact(raw), unit, "sw-accent"),
        stat("difference", report.percent(raw / warehouse - 1, signed=True), "raw files against the warehouse"),
    ], className="dg-stats sw-stats-3")
    chart = chart_block(report.raw_gap_title(results, metric), figures.monthly_lines(data["monthly"], metric),
                        "sw-block")
    return [stats, chart]


def proof_view(results: dict) -> list:
    clean = results["variants"]["clean"]
    counts = report.dbt_counts(results, "clean")
    replay = results.get("daily_replay")
    stats = [
        stat("detections in the clean shop", f"{clean['quality']['detections']:,}", "the same shop without issues"),
        stat("dbt tests pass there", f"{counts['pass']:,} of {counts['pass'] + counts['warn'] + counts['error']:,}",
             "no warnings, no errors"),
    ]
    if replay:
        stats.append(stat("daily runs = full build", "yes" if replay["daily_equals_full"] else "no",
                          f"{replay['tables']} tables, first {replay['days']} days, byte for byte"))
    frame = report.reconcile_frame(results)
    frame = frame[frame["variant"] == "dirty"]
    rows = [html.Tr([html.Td(r["check"], className="sw-wrap"), html.Td(f"{r['checked']:,}", className="sw-num"),
                     html.Td(f"{r['agree']:,}", className="sw-num"),
                     html.Td(f"{r['agree'] / r['checked']:.0%}" if r["checked"] else "–", className="sw-num")])
            for r in frame.to_dict("records")]
    header = [html.Th("Check against the generator"), html.Th("Checked", className="sw-num"),
              html.Th("Agree", className="sw-num"), html.Th("Share", className="sw-num")]
    return [html.Div(stats, className="dg-stats sw-stats-3"),
            html.Div([html.Div("Facts the warehouse assembled itself", className="dg-chart-title"),
                      html.Div("Each one built from the shop's files only, then compared with the generator's own "
                               "tables.", className="dg-chart-sub"),
                      scroll_table(header, rows, "Reconciliation with the generator")], className="sw-chart-gap")]


# ---------------------------------------------------------------------------------------------------------------- #
# Page

def page():
    try:
        data = prepare()
    except FileNotFoundError as error:
        data, problem = None, str(error)
    header = html.Header(html.Div([
        html.Span(["Shop Data Warehouse", html.Span(".", className="dg-dot")], className="dg-wordmark"),
        html.A("Source on GitHub", href=REPO_URL, target="_blank", className="dg-link"),
    ], className="dg-wrap dg-topline"))
    hero = html.Div([
        html.P("Data warehouse of an online shop", className="dg-eyebrow"),
        html.H1(["From daily files to numbers", html.Br(), " you can ", html.Em("check"), "."], className="dg-h1"),
        html.P("The shop's systems drop CSV files every day. Each day is loaded once, dbt builds a star schema with "
               "tests, and every data quality issue the generator injected is checked against its answer key.",
               className="dg-lead"),
    ], className="dg-hero")
    if data is None:
        body = [hero, section(1, "Daily files", "The warehouse is not built yet.",
                              html.P(problem, className="dg-placeholder"), "loads")]
    else:
        results = data["results"]
        body = [
            hero,
            section(1, "Daily files, loaded once", "A day is checked against its manifest, then replaced in one "
                    "transaction: a rerun or a late day gives the same tables.", loads_view(data), "loads"),
            section(2, "Every injected issue, checked", "The generator lists each issue it put in the files with the "
                    "true value; the warehouse never sees that list.", [
                        quality_stats(results),
                        dmc.SegmentedControl(id="quality-table", data=TABLE_CHOICES, value=ALL_TABLES,
                                             className="sw-control sw-block", size="sm"),
                        html.Div(quality_view(results, ALL_TABLES), id="quality-view"),
                    ], "quality"),
            section(3, "What the raw files would say", "The same order lines counted without cleaning.", [
                dmc.SegmentedControl(id="metric", data=METRIC_CHOICES, value="net_revenue",
                                     className="sw-control", size="sm"),
                html.Div(gap_view(data, "net_revenue"), id="gap-view", className="sw-block"),
            ], "raw-files"),
            section(4, "Proof", "A shop without issues raises nothing, and facts built from the files match the "
                    "generator.", proof_view(results), "proof"),
        ]
    footer = html.Footer([
        html.P("Lumo is a fictional shop generated by Data-Generator v1.7.1 (seed 42). Amounts in PLN without VAT. "
               "Postal code reference: ZnajdzKod.pl na podstawie PRG (GUGiK) i TERYT (GUS)."),
        html.A(REPO_URL.removeprefix("https://"), href=REPO_URL, target="_blank", className="dg-link"),
    ], className="dg-footer")
    return dmc.MantineProvider(theme=t.MANTINE_THEME, children=html.Div([
        header,
        html.Main(html.Div([*body, footer], className="dg-wrap")),
    ], className="dg-page"))


# ---------------------------------------------------------------------------------------------------------------- #
# App and callbacks

app = Dash(__name__, title="Shop Data Warehouse", assets_folder=str(Path(__file__).parent / "assets"),
           suppress_callback_exceptions=True)
app.layout = page


@app.callback(Output("quality-view", "children"), Input("quality-table", "value"), prevent_initial_call=True)
def update_quality(table):
    return quality_view(prepare()["results"], table)


@app.callback(Output("gap-view", "children"), Input("metric", "value"), prevent_initial_call=True)
def update_gap(metric):
    return gap_view(prepare(), metric if metric in report.METRICS else "net_revenue")


def main():
    app.run(host="127.0.0.1", port=int(os.environ.get("SW_PORT", 8050)), debug=False)


if __name__ == "__main__":
    main()

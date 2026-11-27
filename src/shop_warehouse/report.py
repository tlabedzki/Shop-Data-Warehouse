"""
Numbers, tables and chart titles shared by the app and the README: one place, so the screen and the README never
disagree. Reads output/results.json (python main.py) and the dirty shop's warehouse.

Words come in two languages: English for the app and the public README, Polish for the README while the repository
is private (portfolio-readme).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import duckdb
import pandas as pd

from shop_warehouse.config import OUTPUT_ROOT, warehouse_path
from shop_warehouse.score import RAW_REPORT_LINES

RESULTS = OUTPUT_ROOT / "results.json"
LANGUAGES = ("en", "pl")
NBSP = " "

# (table, column, issue): what was wrong in the files, and what the warehouse does about it.
ISSUES = {
    "en": {
        ("customers", "phone_number", "format"): ("Phone written another way", "rewritten as +48 and nine digits"),
        ("customers", "phone_number", "missing"): ("Phone missing", "kept unknown"),
        ("customers", "email", "format"): ("E-mail in capitals or with spaces", "lower case, trimmed"),
        ("customers", "email", "missing"): ("E-mail missing", "kept unknown"),
        ("customers", "postal_code", "format"): ("Postal code without the dash", "rewritten as 00-000"),
        ("customers", "city", "typo"): ("City misspelt", "city of the postal code"),
        ("customers", "city", "missing"): ("City missing", "city of the postal code"),
        ("customers", "age", "outlier"): ("Impossible age (0, 150, 999)", "kept unknown"),
        ("customers", "age", "missing"): ("Age missing", "kept unknown"),
        ("customers", "customer_id", "duplicate_customer"): ("Second account of one person",
                                                             "merged by bank account"),
        ("products", "net_purchase_price", "outlier"): ("Purchase price typed in grosze", "divided by 100"),
        ("products", "color", "missing"): ("Colour missing", "kept unknown"),
        ("order_lines", "order_line_id", "duplicate_row"): ("Order line saved twice", "copy removed"),
        ("order_lines", "quantity", "outlier"): ("Quantity of 50 to 500 units", "recovered from the payment"),
        ("order_lines", "payment_provider", "missing"): ("Payment provider missing",
                                                         "taken from the order's other lines"),
    },
    "pl": {
        ("customers", "phone_number", "format"): ("Telefon zapisany inaczej", "zapis +48 i dziewięć cyfr"),
        ("customers", "phone_number", "missing"): ("Brak telefonu", "zostaje nieznany"),
        ("customers", "email", "format"): ("E-mail wielkimi literami albo ze spacjami", "małe litery, bez spacji"),
        ("customers", "email", "missing"): ("Brak e-maila", "zostaje nieznany"),
        ("customers", "postal_code", "format"): ("Kod pocztowy bez myślnika", "zapis 00-000"),
        ("customers", "city", "typo"): ("Literówka w mieście", "miasto z kodu pocztowego"),
        ("customers", "city", "missing"): ("Brak miasta", "miasto z kodu pocztowego"),
        ("customers", "age", "outlier"): ("Niemożliwy wiek (0, 150, 999)", "zostaje nieznany"),
        ("customers", "age", "missing"): ("Brak wieku", "zostaje nieznany"),
        ("customers", "customer_id", "duplicate_customer"): ("Drugie konto tej samej osoby",
                                                             "scalone po numerze konta bankowego"),
        ("products", "net_purchase_price", "outlier"): ("Cena zakupu wpisana w groszach", "podzielona przez 100"),
        ("products", "color", "missing"): ("Brak koloru", "zostaje nieznany"),
        ("order_lines", "order_line_id", "duplicate_row"): ("Linia zamówienia zapisana dwa razy", "kopia usunięta"),
        ("order_lines", "quantity", "outlier"): ("Ilość od 50 do 500 sztuk", "odtworzona z płatności"),
        ("order_lines", "payment_provider", "missing"): ("Brak operatora płatności",
                                                         "z innych linii zamówienia"),
    },
}
TABLE_LABELS = {
    "en": {"customers": "Customers", "products": "Products", "order_lines": "Order lines"},
    "pl": {"customers": "Klienci", "products": "Produkty", "order_lines": "Linie zamówień"},
}
LAYERS = [  # schema, what it holds (en, pl)
    ("raw", "the files as text, one extract date per row", "pliki jako tekst, z datą wyciągu"),
    ("staging", "typed and cleaned, each record once", "typy, czyszczenie, każdy rekord raz"),
    ("intermediate", "people, product versions, order status", "osoby, wersje produktów, status zamówień"),
    ("core", "star schema with contracts", "schemat gwiazdy z kontraktami"),
    ("marts", "daily sales, traffic, cohorts", "sprzedaż dzienna, ruch, kohorty"),
]
METRICS = {  # key: (label, unit) per language
    "net_revenue": {"en": ("Net revenue", "PLN"), "pl": ("Przychód netto", "zł")},
    "gross_margin": {"en": ("Gross margin", "PLN"), "pl": ("Marża brutto", "zł")},
    "units_kept": {"en": ("Units sold", "units"), "pl": ("Sprzedane sztuki", "szt.")},
}
WORDS = {
    "en": {"warehouse": "warehouse", "raw": "raw files", "fixed": "fixed", "caught": "found, kept unknown",
           "missed": "missed or fixed wrongly", "order_lines": "order lines"},
    "pl": {"warehouse": "hurtownia", "raw": "surowe pliki", "fixed": "naprawione", "caught": "złapane, nieznane",
           "missed": "przeoczone albo źle naprawione", "order_lines": "linii zamówień"},
}
MONTHS_PL = ["sty", "lut", "mar", "kwi", "maj", "cze", "lip", "sie", "wrz", "paź", "lis", "gru"]


def check(language: str) -> str:
    if language not in LANGUAGES:
        raise ValueError(f"Unknown language {language!r}; use one of {', '.join(LANGUAGES)}")
    return language


def load_results(path: Path = RESULTS) -> dict:
    if not path.exists():
        raise FileNotFoundError("No results yet. Run: python main.py")
    return json.loads(path.read_text(encoding="utf-8"))


def connect(variant: str = "dirty") -> duckdb.DuckDBPyConnection:
    path = warehouse_path(variant)
    if not path.exists():
        raise FileNotFoundError("No warehouse yet. Run: python main.py")
    return duckdb.connect(str(path), read_only=True)


# ---------------------------------------------------------------------------------------------------------------- #
# Formatting

def integer(value: float, language: str = "en") -> str:
    """13,451 in English, 13 451 in Polish (a non-breaking space)."""
    text = f"{round(value):,}".replace("-", "−")
    return text.replace(",", NBSP) if language == "pl" else text


def compact(value: float, language: str = "en", unit: str = "") -> str:
    """35.7M, 116k, 8,958; in Polish 35,7 mln, 116 tys., 8 958; a minus sign that is not a hyphen."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "–"
    size, sign = abs(value), "−" if value < 0 else ""
    if size >= 1e6:
        number = f"{size / 1e6:.1f}"
        text = f"{number.replace('.', ',')}{NBSP}mln" if language == "pl" else f"{number}M"
    elif size >= 1e5:
        text = f"{size / 1e3:.0f}{NBSP}tys." if language == "pl" else f"{size / 1e3:.0f}k"
    else:
        text = integer(size, language)
    return f"{sign}{text}" + (f"{NBSP}{unit}" if unit else "")


def percent(value: float, language: str = "en", signed: bool = False) -> str:
    text = f"{value:+.0%}" if signed else f"{value:.0%}"
    text = text.replace("-", "−")
    return text.replace(".", ",") if language == "pl" else text


def month(stamp, language: str = "en") -> str:
    return f"{MONTHS_PL[stamp.month - 1]} {stamp.year}" if language == "pl" else f"{stamp:%b %Y}"


def day(stamp, language: str = "en") -> str:
    return f"{stamp.day} {MONTHS_PL[stamp.month - 1]} {stamp.year}" if language == "pl" else f"{stamp:%d %b %Y}"


# ---------------------------------------------------------------------------------------------------------------- #
# Data quality against the answer key

def quality_frame(results: dict, table: str | None = None, language: str = "en") -> pd.DataFrame:
    """One row per kind of injected issue: what it is, what the warehouse does, and the outcome counts."""
    rows = []
    for item in results["variants"]["dirty"]["quality"]["by_issue"]:
        key = (item["table_name"], item["column_name"], item["issue_type"])
        problem, action = ISSUES[check(language)].get(key, (f"{key[1]} {key[2]}", ""))
        rows.append({"table": item["table_name"], "column": item["column_name"], "issue": item["issue_type"],
                     "problem": problem, "action": action, **{k: int(item[k]) for k in
                                                              ("injected", "fixed", "caught", "wrong", "missed")}})
    frame = pd.DataFrame(rows)
    if table:
        frame = frame[frame["table"] == table]
    return frame.sort_values(["injected", "problem"], ascending=[False, True]).reset_index(drop=True)


def quality_title(frame: pd.DataFrame, language: str = "en") -> tuple[str, str]:
    injected, fixed = int(frame["injected"].sum()), int(frame["fixed"].sum())
    missed = int(frame["missed"].sum() + frame["wrong"].sum())
    n = lambda value: integer(value, language)  # noqa: E731
    if language == "pl":
        head = (f"Hurtownia znajduje każdy z {n(injected)} błędów i naprawia {n(fixed)}" if not missed
                else f"{n(missed)} z {n(injected)} błędów przeoczone albo źle naprawione")
        sub = ("Jeden słupek to jeden rodzaj błędu. Petrol: wróciła prawdziwa wartość. Szary: błąd znaleziony, ale "
               "prawdziwej wartości nie ma w danych, więc hurtownia zostawia ją pustą.")
    else:
        head = (f"All {n(injected)} injected issues found, {n(fixed)} fixed" if not missed
                else f"{n(missed)} of {n(injected)} injected issues missed or fixed wrongly")
        sub = ("Each bar is one kind of issue. Teal: the true value is back. Grey: found, but the true value is not "
               "in the data, so the warehouse keeps it unknown.")
    return head, sub


# ---------------------------------------------------------------------------------------------------------------- #
# Raw files against the warehouse

def monthly(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Net revenue, gross margin and kept units per month: the warehouse and a report straight from the files."""
    warehouse = con.execute("""
        select date_trunc('month', order_date) as month, sum(net_revenue) as net_revenue,
               sum(gross_margin) as gross_margin, sum(units_kept) as units_kept
        from marts.mart_daily_sales group by 1""").df()
    raw = con.execute(f"""
        select date_trunc('month', order_date) as month, sum(net_revenue) as net_revenue,
               sum(gross_margin) as gross_margin, sum(units_kept) as units_kept
        from ({RAW_REPORT_LINES}) group by 1""").df()
    frame = warehouse.merge(raw, on="month", suffixes=("_warehouse", "_raw")).sort_values("month")
    for column in frame.columns.drop("month"):
        frame[column] = frame[column].astype(float)
    return frame.reset_index(drop=True)


def raw_gap(results: dict, metric: str) -> float:
    totals = results["variants"]["dirty"]
    return totals["raw_totals"][metric] / totals["totals"][metric] - 1


def raw_gap_title(results: dict, metric: str, language: str = "en") -> tuple[str, str]:
    label, unit = METRICS[metric][check(language)]
    gap = raw_gap(results, metric)
    if language == "pl":
        verb = "zawyża" if gap > 0 else "zaniża"
        return (f"Raport z surowych plików {verb} {label.lower()} o {percent(abs(gap), language)}",
                f"{label} w miesiącu, {unit}. Petrol: hurtownia po czyszczeniu. Miedź: te same linie policzone wprost "
                f"z plików, z kopiami, wpisanymi ilościami i cenami w groszach.")
    verb = "overstates" if gap > 0 else "understates"
    return (f"A report from the raw files {verb} {label.lower()} by {percent(abs(gap), language)}",
            f"{label} per month, {unit}. Teal: the warehouse after cleaning. Copper: the same lines counted straight "
            f"from the files, with copies, typed quantities and prices in grosze.")


# ---------------------------------------------------------------------------------------------------------------- #
# Loads and layers

def loads(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Rows landed per day for the busiest files."""
    frame = con.execute("""
        select extract_date as day, table_name, row_count from raw._load_log
        where table_name in ('order_lines', 'order_events', 'sessions')""").df()
    frame = frame.pivot(index="day", columns="table_name", values="row_count").reset_index()
    frame["day"] = pd.to_datetime(frame["day"])
    return frame.sort_values("day").reset_index(drop=True)


def loads_title(frame: pd.DataFrame, language: str = "en") -> tuple[str, str]:
    peak = frame.loc[frame["order_lines"].idxmax()]
    days, lines = integer(len(frame), language), integer(int(peak["order_lines"]), language)
    if language == "pl":
        return (f"{days} dziennych zrzutów, szczyt {day(peak['day'], language)}: {lines} linii zamówień",
                "Linie zamówień w pliku każdego dnia. Zdarzenia przychodzą jeszcze po ostatnim zamówieniu: dostawy, "
                "zwroty, opinie.")
    return (f"{days} daily drops, the busiest on {day(peak['day'], language)}: {lines} order lines",
            "Order lines in each day's file. Events keep coming after the last order: deliveries, returns, reviews.")


def layers(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Tables and rows of each layer of the warehouse."""
    rows = []
    for schema, note_en, note_pl in LAYERS:
        tables = [name for (name,) in con.execute(
            "select table_name from information_schema.tables where table_schema = ? order by 1", [schema]).fetchall()
            if not name.startswith("_")]
        count = sum(con.execute(f'select count(*) from {schema}."{name}"').fetchall()[0][0] for name in tables)
        rows.append({"layer": schema, "tables": len(tables), "rows": int(count), "note": note_en,
                     "note_pl": note_pl})
    return pd.DataFrame(rows)


RECONCILE_LABELS = {
    "en": {
        "order_status": "Order status from the event log = status in the generator",
        "payment_status": "Payment status = status in the generator",
        "is_late": "Late delivery = generator's flag",
        "price_on_order_day": "List price of the product version on the order day = price on the line",
        "customers": "Customers after merging second accounts = people in the generator",
    },
    "pl": {
        "order_status": "Status zamówienia z dziennika zdarzeń = status w generatorze",
        "payment_status": "Status płatności = status w generatorze",
        "is_late": "Spóźniona dostawa = znacznik generatora",
        "price_on_order_day": "Cena wersji produktu w dniu zamówienia = cena na linii",
        "customers": "Klienci po scaleniu drugich kont = osoby w generatorze",
    },
}


def reconcile_frame(results: dict, language: str = "en") -> pd.DataFrame:
    rows = []
    for variant in ("dirty", "clean"):
        for name, item in results["variants"][variant]["reconcile"].items():
            rows.append({"variant": variant, "name": name,
                         "check": RECONCILE_LABELS[check(language)].get(name, name),
                         "checked": item["checked"], "agree": item["agree"]})
    return pd.DataFrame(rows)


def dbt_counts(results: dict, variant: str) -> dict[str, int]:
    counts = results["variants"][variant]["dbt"]
    tests = {key.split(":")[1]: value for key, value in counts.items() if key.startswith("test:")}
    return {"pass": tests.get("pass", 0), "warn": tests.get("warn", 0),
            "error": tests.get("error", 0) + tests.get("fail", 0), "unit": counts.get("unit_test:pass", 0),
            "models": counts.get("model:success", 0)}

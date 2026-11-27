"""
README images and numbers in one run: the charts (the same Plotly code as the app, drawn in headless Chrome with Inter
from the repository), the animated hero (scripts/make_demo_svg.py) and every <!-- generated:... --> block of
README.md, in the README's language.

    python scripts/make_charts.py                # Polish README (private repository)
    python scripts/make_charts.py --lang en      # English README (before the repository goes public)
    python scripts/make_charts.py --no-demo      # charts and numbers only, keep the hero

Needs output/results.json and the warehouses from python main.py --daily, Chrome or Edge, and requirements-dev.txt.
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import make_demo_svg  # noqa: E402
from browser import Browser  # noqa: E402
from PIL import Image  # noqa: E402

from shop_warehouse import figures, report  # noqa: E402
from shop_warehouse import theme as t  # noqa: E402

IMG = ROOT / "docs" / "img"
README = ROOT / "README.md"
CACHE = ROOT / ".cache" / "charts"
FONTS = ROOT / "ui" / "assets" / "fonts"
CHART_WIDTH, PAD, SCALE = 712, 24, 2  # CSS pixels; the PNG is (712 + 2 * 24) * 2 = 1520 px wide


# ---------------------------------------------------------------------------------------------------------------- #
# Numbers

def compute(language: str) -> dict:
    results = report.load_results()
    con = report.connect("dirty")
    try:
        events = con.execute("select count(*) from raw.order_events").fetchall()[0][0]
        files = con.execute("select count(*) from raw._load_log").fetchall()[0][0]
        numbers = {"results": results, "monthly": report.monthly(con), "loads": report.loads(con),
                   "events": int(events), "files": int(files), "language": report.check(language)}
    finally:
        con.close()
    if "daily_replay" not in results:
        sys.exit("output/results.json has no daily replay: run python main.py --daily first.")
    return numbers


def blocks(numbers: dict, demo: dict | None) -> dict[str, str]:
    """Text of every generated block, in the README language."""
    lang, results = numbers["language"], numbers["results"]
    n = lambda value: report.integer(value, lang)  # noqa: E731
    pct = lambda value, signed=False: report.percent(value, lang, signed)  # noqa: E731
    money = lambda value: report.compact(value, lang)  # noqa: E731
    dirty, clean = results["variants"]["dirty"], results["variants"]["clean"]
    quality, replay = dirty["quality"], results["daily_replay"]
    issues = {(i["table_name"], i["column_name"], i["issue_type"]): i for i in quality["by_issue"]}
    quantity = issues[("order_lines", "quantity", "outlier")]
    provider = issues[("order_lines", "payment_provider", "missing")]
    dupes = issues[("customers", "customer_id", "duplicate_customer")]
    reconcile = {**dirty["reconcile"]}
    agree = all(item["agree"] == item["checked"] for v in ("dirty", "clean")
                for item in results["variants"][v]["reconcile"].values())
    counts, clean_counts = report.dbt_counts(results, "dirty"), report.dbt_counts(results, "clean")
    gap, margin_gap = report.raw_gap(results, "net_revenue"), report.raw_gap(results, "gross_margin")
    loads = numbers["loads"]
    peak = loads.loc[loads["order_lines"].idxmax()]
    missed = quality["missed"] + quality["wrong"]
    loads_title = report.loads_title(loads, lang)[0]
    quality_title = report.quality_title(report.quality_frame(results, language=lang), lang)[0]
    gap_title = report.raw_gap_title(results, "net_revenue", lang)[0]
    rows = quality_rows(results, lang)
    differ = ", ".join(replay["tables_that_differ"])
    images = {name: f"\n\n![{title}](docs/img/{name}.png)" for name, title in
              (("daily-loads", loads_title), ("quality-issues", quality_title), ("raw-vs-warehouse", gap_title))}

    if lang == "pl":
        out = {
            "result": (f"**Wynik.** Z {n(quality['injected'])} wstrzykniętych błędów hurtownia znajduje wszystkie: "
                       f"{n(quality['fixed'])} naprawia do prawdziwej wartości, a {n(quality['caught'])} zostawia jako "
                       f"nieznane, bo prawdy nie ma w danych. Nie podnosi ani jednego fałszywego alarmu. Raport "
                       f"liczony wprost z plików zawyżyłby przychód netto o {pct(gap)}."),
            "summary": (f"- **Trafione:** status {n(reconcile['order_status']['checked'])} zamówień złożony "
                        f"z {n(numbers['events'])} zdarzeń, cena wersji produktu w dniu zamówienia i scalenie "
                        f"{n(dupes['injected'])} drugich kont zgadzają się z generatorem w 100%.\n"
                        f"- **Chybione:** {n(quantity['caught'])} z {n(quantity['injected'])} niemożliwych ilości "
                        f"i {n(provider['caught'])} z {n(provider['injected'])} braków operatora płatności zostają "
                        f"nieznane, bo w danych nie ma skąd ich odtworzyć."),
            "loads": (f"Hurtownia przyjęła {n(dirty['days'])} dni po {n(numbers['files'] // dirty['days'])} plików "
                      f"({n(numbers['files'])} plików, {n(numbers['events'])} zdarzeń zamówień). Najwięcej linii "
                      f"zamówień, {n(int(peak['order_lines']))}, przyszło {report.day(peak['day'], lang)}, w tygodniu "
                      f"Black Friday.{images['daily-loads']}"),
            "quality": (f"dbt build na sklepie z błędami: {n(counts['pass'])} testów zielonych i {n(counts['warn'])} "
                        f"ostrzeżeń, po jednym na regułę jakości; {n(counts['unit'])} testów jednostkowych reguł "
                        f"przechodzi. Klucz odpowiedzi: {n(quality['fixed'])} błędów naprawionych, "
                        f"{n(quality['caught'])} złapanych bez możliwej naprawy, {n(missed)} przeoczonych albo źle "
                        f"naprawionych, {n(quality['false_alarms'])} fałszywych alarmów. Jeszcze "
                        f"{n(quality['copies_on_second_accounts'])} wykryć to kopie błędu oryginału na drugich kontach "
                        f"(generator kopiuje konto razem z jego błędami).{images['quality-issues']}"),
            "core": ("| Fakt złożony przez hurtownię | Sprawdzone | Zgodne |\n|---|---:|---:|\n"
                     + "\n".join(f"| {r['check']} | {n(r['checked'])} | {n(r['agree'])} |"
                                 for r in report.reconcile_frame(results, lang).to_dict("records")
                                 if r["variant"] == "dirty")),
            "gap": (f"Przychód netto w hurtowni: {money(dirty['totals']['net_revenue'])} zł, w raporcie z surowych "
                    f"plików {money(dirty['raw_totals']['net_revenue'])} zł ({pct(gap, True)}). Marża brutto: "
                    f"{money(dirty['totals']['gross_margin'])} zł kontra {money(dirty['raw_totals']['gross_margin'])} "
                    f"zł ({pct(margin_gap, True)}). Klientów {n(dirty['totals']['customers'])}, a kont w plikach "
                    f"{n(dirty['raw_totals']['customers'])}.{images['raw-vs-warehouse']}"),
            "daily": (f"Pierwsze {n(replay['days'])} dni ładowane dzień po dniu dają {n(replay['tables'])} tabel "
                      f"warstw core, marts i quality równych bajt w bajt pełnemu ładowaniu tych samych dni "
                      f"({'zgodne' if replay['daily_equals_full'] else 'różnice: ' + differ})."),
            "verdicts": verdicts(numbers, rows, agree, clean, clean_counts),
        }
    else:
        out = {
            "result": (f"**Result.** Of {n(quality['injected'])} injected issues the warehouse finds every one: it "
                       f"fixes {n(quality['fixed'])} to the true value, keeps {n(quality['caught'])} unknown because "
                       f"the truth is not in the data, and raises no false alarm. A report counted straight from the "
                       f"files would overstate net revenue by {pct(gap)}."),
            "summary": (f"- **What worked:** the status of {n(reconcile['order_status']['checked'])} orders built "
                        f"from {n(numbers['events'])} events, the product version's price on the order day and the "
                        f"merge of {n(dupes['injected'])} second accounts agree with the generator 100%.\n"
                        f"- **What missed:** {n(quantity['caught'])} of {n(quantity['injected'])} impossible "
                        f"quantities and {n(provider['caught'])} of {n(provider['injected'])} missing payment "
                        f"providers stay unknown: nothing in the data tells the true value."),
            "loads": (f"The warehouse took {n(dirty['days'])} days of {n(numbers['files'] // dirty['days'])} files "
                      f"({n(numbers['files'])} files, {n(numbers['events'])} order events). The busiest file, "
                      f"{report.day(peak['day'], lang)}, brought {n(int(peak['order_lines']))} order lines in the "
                      f"Black Friday week.{images['daily-loads']}"),
            "quality": (f"dbt build on the shop with issues: {n(counts['pass'])} tests pass and {n(counts['warn'])} "
                        f"warn, one per quality rule; {n(counts['unit'])} unit tests of the rules pass. Against the "
                        f"answer key: {n(quality['fixed'])} issues fixed, {n(quality['caught'])} found without a "
                        f"possible fix, {n(missed)} missed or fixed wrongly, {n(quality['false_alarms'])} false "
                        f"alarms. Another {n(quality['copies_on_second_accounts'])} detections are copies of the "
                        f"original's issue on second accounts (the generator copies an account with its issues)."
                        f"{images['quality-issues']}"),
            "core": ("| Fact the warehouse built | Checked | Agree |\n|---|---:|---:|\n"
                     + "\n".join(f"| {r['check']} | {n(r['checked'])} | {n(r['agree'])} |"
                                 for r in report.reconcile_frame(results, lang).to_dict("records")
                                 if r["variant"] == "dirty")),
            "gap": (f"Net revenue in the warehouse: {money(dirty['totals']['net_revenue'])} PLN, in a report from "
                    f"the raw files {money(dirty['raw_totals']['net_revenue'])} PLN ({pct(gap, True)}). Gross margin: "
                    f"{money(dirty['totals']['gross_margin'])} PLN against "
                    f"{money(dirty['raw_totals']['gross_margin'])} PLN ({pct(margin_gap, True)}). "
                    f"{n(dirty['totals']['customers'])} customers, while the files hold "
                    f"{n(dirty['raw_totals']['customers'])} accounts.{images['raw-vs-warehouse']}"),
            "daily": (f"The first {n(replay['days'])} days loaded one by one give {n(replay['tables'])} tables of the "
                      f"core, marts and quality layers equal byte for byte to a full load of the same days "
                      f"({'equal' if replay['daily_equals_full'] else 'differ: ' + differ})."),
            "verdicts": verdicts(numbers, rows, agree, clean, clean_counts),
        }
    if demo:
        alt = demo["alt"]
        dark = '  <source media="(prefers-color-scheme: dark)" srcset="docs/img/app-demo-dark.svg">'
        out["hero"] = f'<picture>\n{dark}\n  <img alt="{alt}" src="docs/img/app-demo.svg">\n</picture>'
    return out


def quality_rows(results: dict, lang: str) -> list[dict]:
    return report.quality_frame(results, language=lang).to_dict("records")


VERDICT_WORDS = {
    "pl": {"header": "| Pytanie | Odpowiedź hurtowni | Prawda | Ocena |", "fixed": "naprawione",
           "unknown": "nieznane", "key": "w kluczu", "hit": "trafione", "partial": "częściowo",
           "no_truth": "trafione, prawdy nie ma w danych", "miss": "chybione",
           "q_fixed": "Błędy, których prawda jest w danych (rodzaje: {kinds}): czy wraca prawdziwa wartość?",
           "q_unknown": "Braki i niemożliwe wartości (rodzaje: {kinds}): czy hurtownia je łapie bez zgadywania?",
           "q_one": "{name}: czy da się naprawić?",
           "facts": "| Status, płatność, spóźnienie, cena, klienci: czy zgadzają się z generatorem? "
                    "| jak w rozdziale 5 | tabele generatora | {verdict} |",
           "control": "Kontrola: ten sam sklep bez błędów daje {detections} wykryć, a {passed} z {total} testów dbt "
                      "przechodzi bez ostrzeżeń. Fałszywe alarmy na sklepie z błędami: {false}. Pełna lista rodzajów "
                      "błędów: [docs/quality-issues.md](docs/quality-issues.md)."},
    "en": {"header": "| Question | Warehouse answer | Truth | Verdict |", "fixed": "fixed", "unknown": "unknown",
           "key": "in the key", "hit": "hit", "partial": "partial", "no_truth": "hit, no truth in the data",
           "miss": "miss",
           "q_fixed": "Issues whose truth is in the data ({kinds} kinds): does the true value come back?",
           "q_unknown": "Missing and impossible values ({kinds} kinds): are they caught without guessing?",
           "q_one": "{name}: can it be fixed?",
           "facts": "| Status, payment, lateness, price, customers: do they agree with the generator? | as in "
                    "chapter 5 | generator tables | {verdict} |",
           "control": "Control: the same shop without issues gives {detections} detections, and {passed} of {total} "
                      "dbt tests pass without a warning. False alarms on the shop with issues: {false}. Every kind "
                      "of issue: [docs/quality-issues.md](docs/quality-issues.md)."},
}


def outcome(row: dict) -> str:
    if row["missed"] + row["wrong"]:
        return "miss"
    if row["caught"] and row["fixed"]:
        return "partial"
    return "no_truth" if row["caught"] else "hit"


def verdicts(numbers: dict, rows: list[dict], agree: bool, clean: dict, clean_counts: dict) -> str:
    """The verdict table: every miss and partial on its own row, the rest grouped by outcome."""
    lang = numbers["language"]
    words = VERDICT_WORDS[lang]
    n = lambda value: report.integer(value, lang)  # noqa: E731
    quality = numbers["results"]["variants"]["dirty"]["quality"]
    lines = [words["header"], "|---|---|---|---|"]

    def answer(fixed: int, caught: int) -> str:
        parts = ([f"{words['fixed']} {n(fixed)}"] if fixed else []) + ([f"{words['unknown']} {n(caught)}"]
                                                                       if caught else [])
        return ", ".join(parts)

    for kind, question in (("hit", "q_fixed"), ("no_truth", "q_unknown")):
        group = [row for row in rows if outcome(row) == kind]
        if group:
            fixed, caught = sum(r["fixed"] for r in group), sum(r["caught"] for r in group)
            injected = sum(r["injected"] for r in group)
            lines.append(f"| {words[question].format(kinds=n(len(group)))} | {answer(fixed, caught)} | {n(injected)} "
                         f"{words['key']} | {words[kind]} |")
    for row in rows:
        kind = outcome(row)
        if kind in ("partial", "miss"):
            lines.append(f"| {words['q_one'].format(name=row['problem'])} | {answer(row['fixed'], row['caught'])} | "
                         f"{n(row['injected'])} {words['key']} | {words[kind]} |")
    lines.append(words["facts"].format(verdict=words["hit"] if agree else words["miss"]))
    total = clean_counts["pass"] + clean_counts["warn"] + clean_counts["error"]
    control = words["control"].format(detections=n(clean["quality"]["detections"]), passed=n(clean_counts["pass"]),
                                      total=n(total), false=n(quality["false_alarms"]))
    return "\n".join(lines) + "\n\n" + control


QUALITY_DOC = {
    "pl": ("# Rodzaje błędów kontra klucz odpowiedzi",
           "| Błąd w plikach | Tabela | Co robi hurtownia | W kluczu | Naprawione | Nieznane | Przeoczone "
           "| Źle naprawione |"),
    "en": ("# Kinds of issues against the answer key",
           "| Issue in the files | Table | What the warehouse does | In the key | Fixed | Unknown | Missed "
           "| Fixed wrongly |"),
}


def quality_doc(numbers: dict) -> str:
    """docs/quality-issues.md: every kind of injected issue with its outcome counts."""
    lang = numbers["language"]
    n = lambda value: report.integer(value, lang)  # noqa: E731
    title, header = QUALITY_DOC[lang]
    rows = report.quality_frame(numbers["results"], language=lang).to_dict("records")
    body = "\n".join(f"| {r['problem']} | {report.TABLE_LABELS[lang][r['table']]} | {r['action']} | {n(r['injected'])} "
                     f"| {n(r['fixed'])} | {n(r['caught'])} | {n(r['missed'])} | {n(r['wrong'])} |" for r in rows)
    note = ("<!-- generated by scripts/make_charts.py from output/results.json; do not edit -->")
    return f"{title}\n\n{note}\n\n{header}\n|---|---|---|---:|---:|---:|---:|---:|\n{body}\n"


def wrap(text: str) -> str:
    """Prose and list items wrapped at 120 characters, never after a one-letter word; tables and images stay."""
    out = []
    for paragraph in text.split("\n\n"):
        if paragraph.startswith(("|", "!", "<")):
            out.append(paragraph)
        elif paragraph.startswith("- "):
            out.append("\n".join(textwrap.fill(keep_together(item), 120, subsequent_indent="  ",
                                                break_on_hyphens=False, break_long_words=False)
                                  for item in paragraph.split("\n")))
        else:
            out.append(textwrap.fill(keep_together(paragraph), 120, break_on_hyphens=False,
                                     break_long_words=False))
    return "\n\n".join(out)


def write_readme(texts: dict[str, str]) -> None:
    readme = README.read_text(encoding="utf-8")
    for name, text in texts.items():
        text = wrap(text)
        pattern = re.compile(rf"(<!-- generated:{name} -->\n)(?:.*?\n)?(<!-- /generated:{name} -->)", re.S)
        if not pattern.search(readme):
            raise SystemExit(f"README.md has no block <!-- generated:{name} -->")
        readme = pattern.sub(lambda match, text=text: match.group(1) + text + "\n" + match.group(2), readme)
    README.write_text(readme, encoding="utf-8", newline="\n")


# ---------------------------------------------------------------------------------------------------------------- #
# Charts

def font_faces() -> str:
    css = (ROOT / "ui" / "assets" / "fonts.css").read_text(encoding="utf-8")
    return css.replace("url('fonts/", f"url('{FONTS.as_uri()}/")


def keep_together(text: str) -> str:
    """No one-letter word at the end of a line (Polish typography): a non-breaking space after it."""
    return re.sub(r"(?<=\s)([aiouwzAIOUWZ]) ", lambda match: match.group(1) + "\u00a0", text)


def chart_page(title: str, subtitle: str, figure) -> str:
    title, subtitle = keep_together(title), keep_together(subtitle)
    figure.update_layout(width=CHART_WIDTH, autosize=False)
    body = figure.to_html(full_html=False, include_plotlyjs=True, config={"staticPlot": True})
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{font_faces()}
html, body {{ margin: 0; background: {t.PAGE}; }}
#chart {{ width: {CHART_WIDTH}px; padding: {PAD}px; background: {t.PAGE}; font-family: {t.SANS_STACK};
         -webkit-font-smoothing: antialiased; }}
.title {{ font-size: 21px; font-weight: 600; letter-spacing: -0.01em; color: {t.INK}; line-height: 1.3; }}
.sub {{ margin-top: 4px; font-size: 14px; color: {t.MUTED}; line-height: 1.45; }}
.graph {{ margin-top: 14px; }}
.graph text {{ font-feature-settings: {t.NUMBER_FEATURES}; }}
</style></head><body><div id="chart"><div class="title">{title}</div><div class="sub">{subtitle}</div>
<div class="graph">{body}</div></div></body></html>"""


def charts(numbers: dict) -> list[tuple[str, str]]:
    lang, results = numbers["language"], numbers["results"]
    frame = report.quality_frame(results, language=lang)
    return [
        ("daily-loads", chart_page(*report.loads_title(numbers["loads"], lang),
                                   figures.loads_area(numbers["loads"], lang, height=240))),
        ("quality-issues", chart_page(*report.quality_title(frame, lang), figures.quality_bars(frame, lang))),
        ("raw-vs-warehouse", chart_page(*report.raw_gap_title(results, "net_revenue", lang),
                                        figures.monthly_lines(numbers["monthly"], "net_revenue", lang))),
    ]


async def draw(pages: list[tuple[str, str]]) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    IMG.mkdir(parents=True, exist_ok=True)
    async with Browser() as page:
        await page.viewport(CHART_WIDTH + 2 * PAD, 900, SCALE)
        for name, html in pages:
            path = CACHE / f"{name}.html"
            path.write_text(html, encoding="utf-8")
            await page.open(path.as_uri())
            await page.until("document.fonts.status === 'loaded' && !!document.querySelector('.main-svg')")
            await page.js("document.fonts.ready.then(() => true)")
            await asyncio.sleep(0.5)
            target = IMG / f"{name}.png"
            await page.shot("#chart", target)
            Image.open(target).convert("RGB").save(target, optimize=True)  # solid white, no alpha channel
            print(f"Saved docs/img/{name}.png")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lang", choices=report.LANGUAGES, default="pl", help="language of README.md")
    parser.add_argument("--no-demo", action="store_true", help="keep the animated hero as it is")
    parser.add_argument("--reuse-shots", action="store_true", help="build the hero from the kept screenshots")
    args = parser.parse_args()
    numbers = compute(args.lang)
    asyncio.run(draw(charts(numbers)))
    demo = None
    if not args.no_demo:
        demo = make_demo_svg.make(reuse=args.reuse_shots, language=args.lang)
    write_readme(blocks(numbers, demo))
    (ROOT / "docs" / "quality-issues.md").write_text(quality_doc(numbers), encoding="utf-8", newline="\n")
    print("Updated the generated blocks of README.md")


if __name__ == "__main__":
    main()

"""
Build docs/img/app-demo.svg and app-demo-dark.svg, the animated demo at the top of the README.

    python scripts/make_demo_svg.py [--shots DIR] [--reuse] [--quality 70] [--res 1.25] [--lang en|pl]

The demo is an illustration made of screenshots of the real app, not a recording. One loop of 13.5 s: the view rests
on "Every injected issue, checked", the cursor picks "Order lines" (the chart and table show the order line issues),
the page glides down to "What the raw files would say", the cursor picks "Gross margin" (the gap between the warehouse
and the raw files changes), goes back to "Net revenue", the page glides up and "All tables" brings the first frame
back: every switch in the loop is a click, so nothing jumps at the seam.

The script starts the Dash app on 127.0.0.1 and takes full-page screenshots 960 CSS px wide at device scale factor 2
(headless Chrome or Edge on a free DevTools port, scripts/browser.py) of three states: all tables with net revenue,
order lines with net revenue, order lines with gross margin. The numbers each state shows come from shop_warehouse
.report, the same code as the app and the README, and the script stops if the app shows other numbers. The cursor,
the clicks and the scrollbar are vectors; scroll positions come from the screenshots' geometry.

Only CSS animations of transform and opacity inside the SVG, no script and no external file: GitHub shows README
images through <img>. With prefers-reduced-motion the image shows the first frame without motion. The two files differ
only in the browser frame (light and dark GitHub theme). --shots keeps the screenshots and geometry in DIR; --reuse
builds from them without starting the app; two builds from the same screenshots give the same bytes.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from browser import Browser, stop_tree, wait_for  # noqa: E402

from shop_warehouse import report  # noqa: E402
from shop_warehouse import theme as look  # noqa: E402

OUT_DIR = ROOT / "docs" / "img"
CSS_W, DSF = 960, 2  # app page width in CSS px, screenshot pixels per CSS px
VIEW = 820  # CSS px of the page in view
W = 1000  # SVG width
K = W / CSS_W
BAR = 36  # browser bar above the page
LIMIT = 500 * 1024  # bytes per SVG
EASE = "cubic-bezier(.65,0,.35,1)"
EASE_OUT = "cubic-bezier(.22,1,.36,1)"
INK = look.INK
CURSOR = "M0 0V17.2L4.3 13.3L7.2 20.1L10.3 18.8L7.5 12.2H13.2Z"  # arrow, tip at 0,0
FRAMES = {  # browser frame in GitHub's light and dark theme; the app keeps its own light page
    "light": {"bar": "#f6f8fa", "border": "#d0d7de", "dot": "#d0d7de", "pill": "#ffffff", "pill_text": "#57606a"},
    "dark": {"bar": "#161b22", "border": "#30363d", "dot": "#484f58", "pill": "#0d1117", "pill_text": "#8b949e"},
}
HIDDEN = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}

TABLE, METRIC = "order_lines", "gross_margin"  # what the demo picks
# state: (table filter, metric)
STATES = {"all": ("all", "net_revenue"), "lines": (TABLE, "net_revenue"), "margin": (TABLE, METRIC)}

# Timeline (seconds)
T = 13.5
LAG = 0.3  # the app redraws after a click
CLICK_TABLE = 1.6
DOWN = (2.7, 3.9)
CLICK_METRIC = 4.8
CLICK_BACK = 7.8
UP = (8.7, 9.9)
CLICK_ALL = 10.8


def numbers() -> dict:
    """What each state must show: the quality chart title and the three stats of the raw files section."""
    results = report.load_results()
    out = {}
    for name, (table, metric) in STATES.items():
        frame = report.quality_frame(results, None if table == "all" else table)
        totals = results["variants"]["dirty"]
        out[name] = {
            "quality_title": report.quality_title(frame)[0],
            "gap_stats": [report.compact(totals["totals"][metric]), report.compact(totals["raw_totals"][metric]),
                          report.percent(report.raw_gap(results, metric), signed=True)],
        }
    out["net_gap"] = report.percent(report.raw_gap(results, "net_revenue"))
    out["margin_gap"] = report.percent(abs(report.raw_gap(results, METRIC)))
    out["injected"] = results["variants"]["dirty"]["quality"]["injected"]
    return out


def alt_text(values: dict, language: str = "pl") -> str:
    """The description of the demo, for the SVG title and the README <img alt>."""
    injected = report.integer(values["injected"], language)
    if language == "pl":
        return (f"Aplikacja Shop Data Warehouse w ilustracji: wykres {injected} wstrzykniętych błędów zawęża się do "
                f"linii zamówień, strona zjeżdża do porównania z surowymi plikami, które zawyżają przychód netto "
                f"o {values['net_gap']}, a przełącznik pokazuje marżę brutto zaniżoną o {values['margin_gap']}.")
    return (f"Shop Data Warehouse app, illustrated: the chart of {injected} injected issues narrows to order lines, "
            f"the page scrolls to the raw files, which overstate net revenue by {values['net_gap']}, and a switch "
            f"shows gross margin understated by {values['margin_gap']}.")


# ---- 1. screenshots ----------------------------------------------------------------------------------------------

GEOMETRY_JS = """(() => {
  const box = e => { const r = e.getBoundingClientRect();
    return {x: r.left, y: r.top + scrollY, w: r.width, h: r.height}; };
  const labels = id => Object.fromEntries([...document.querySelectorAll('#' + id + ' label')]
    .map(e => [e.textContent, box(e)]));
  return JSON.stringify({
    quality: box(document.getElementById('quality')), raw: box(document.getElementById('raw-files')),
    quality_control: box(document.getElementById('quality-table')),
    table_labels: labels('quality-table'), metric_labels: labels('metric'),
    quality_title: document.querySelector('#quality-view .dg-chart-title').textContent,
    gap_stats: [...document.querySelectorAll('#gap-view .dg-stat-value')].map(e => e.textContent),
    gap_chart: box(document.querySelector('#gap-view .dg-chart')),
    page_bg: getComputedStyle(document.querySelector('.dg-page')).backgroundColor,
    height: document.documentElement.scrollHeight});
})()"""

TABLE_LABEL = {"all": "All tables", **report.TABLE_LABELS["en"]}
METRIC_LABEL = {key: labels["en"][0] for key, labels in report.METRICS.items()}


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def capture(port: int, shots: Path, values: dict) -> None:
    geometry = {}
    async with Browser() as page:
        await page.viewport(CSS_W, 900, DSF)
        for name, (table, metric) in STATES.items():
            await page.open(f"http://127.0.0.1:{port}/")
            await page.until("!!document.querySelector('#quality-view .main-svg') && "
                             "!!document.querySelector('#gap-view .main-svg')")
            for control, label in (("quality-table", TABLE_LABEL[table]), ("metric", METRIC_LABEL[metric])):
                await page.js(f"[...document.querySelectorAll('#{control} label')]"
                              f".find(e => e.textContent === {json.dumps(label)}).click()")
            want = values[name]
            await page.until(f"document.querySelector('#quality-view .dg-chart-title').textContent === "
                             f"{json.dumps(want['quality_title'])} && [...document.querySelectorAll("
                             f"'#gap-view .dg-stat-value')].map(e => e.textContent).join('|') === "
                             f"{json.dumps('|'.join(want['gap_stats']))}")
            await page.js("document.fonts.ready.then(() => true)")
            await page.js("document.activeElement && document.activeElement.blur(); window.scrollTo(0, 0)")
            await page.send("Input.dispatchMouseEvent", type="mouseMoved", x=2, y=2)
            await asyncio.sleep(1.5)
            height = await page.js("document.documentElement.scrollHeight")
            shot = await page.send("Page.captureScreenshot", format="png", captureBeyondViewport=True,
                                   clip={"x": 0, "y": 0, "width": CSS_W, "height": height, "scale": 1})
            (shots / f"{name}.png").write_bytes(base64.b64decode(shot["data"]))
            geometry[name] = json.loads(await page.js(GEOMETRY_JS))
            print(name, height, geometry[name]["quality_title"], "|", " | ".join(geometry[name]["gap_stats"]))
    (shots / "geometry.json").write_text(json.dumps(geometry, indent=1), encoding="utf-8")


def take_screenshots(shots: Path, values: dict) -> None:
    port = free_port()
    env = {**os.environ, "SW_PORT": str(port)}
    app = subprocess.Popen([sys.executable, "-m", "ui.app"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, **HIDDEN)
    try:
        wait_for(f"http://127.0.0.1:{port}/")
        asyncio.run(capture(port, shots, values))
    finally:
        stop_tree(app)


def check(geo: dict, values: dict) -> None:
    """Stop when the screenshots are not these states, show other numbers or have a layout the overlays break."""
    if set(geo) != set(STATES):
        sys.exit("The screenshots are not the states of this script: run without --reuse.")
    for name in STATES:
        shown = [geo[name]["quality_title"], geo[name]["gap_stats"]]
        wanted = [values[name]["quality_title"], values[name]["gap_stats"]]
        if shown != wanted:
            sys.exit(f"The app shows {shown} in {name}, the report gives {wanted}: retake the screenshots.")
    if abs(geo["all"]["quality"]["y"] - geo["lines"]["quality"]["y"]) > 2:
        sys.exit("The issue section moves between the states: the overlays would not line up.")
    if abs(geo["lines"]["raw"]["y"] - geo["margin"]["raw"]["y"]) > 2:
        sys.exit("The raw files section moves between the states: the overlays would not line up.")


# ---- 2. animation ------------------------------------------------------------------------------------------------

class Motion:
    """CSS keyframes on one timeline. Each track: (seconds, value, easing to the next stop)."""

    def __init__(self, total: float):
        self.total = total
        self.css: list[str] = []
        self.count = 0

    def track(self, prop: str, stops: list, rest) -> str:
        """A class animating prop through stops; rest is the value without motion (prefers-reduced-motion)."""
        self.count += 1
        name = f"m{self.count}"
        stops = sorted(stops, key=lambda s: s[0])
        if stops[0][0] > 0:
            stops.insert(0, (0, stops[0][1], "linear"))
        if stops[-1][0] < self.total:
            stops.append((self.total, stops[-1][1], "linear"))
        frames = "".join(f"{s / self.total * 100:.3f}%{{{prop}:{value};animation-timing-function:{ease}}}"
                         for s, value, ease in stops)
        self.css.append(f"@keyframes {name}{{{frames}}}.{name}{{{prop}:{rest};"
                        f"animation:{name} {self.total:g}s linear 0s infinite both}}")
        return name


def tr(x: float, y: float) -> str:
    return f"translate({x:.1f}px,{y:.1f}px)"


def css_color(value: str) -> str:
    """rgb(1, 2, 3) to #010203."""
    parts = [int(float(p)) for p in value[value.index("(") + 1:value.index(")")].split(",")[:3]]
    return "#{:02x}{:02x}{:02x}".format(*parts)


def window(on: float, off: float, fade: float = 0.22) -> list:
    """Opacity: hidden until `on`, shown until `off`, both with a short fade."""
    return [(0, 0, "linear"), (on, 0, EASE), (on + fade, 1, "linear"), (off, 1, EASE), (off + fade, 0, "linear")]


def center(box: dict, scroll: float) -> tuple[float, float]:
    return box["x"] + box["w"] / 2, box["y"] + box["h"] / 2 - scroll


def build(shots: Path, quality: int, res: float, language: str) -> tuple[dict[str, str], dict]:
    geo = json.loads((shots / "geometry.json").read_text(encoding="utf-8"))
    values = numbers()
    check(geo, values)
    images = {name: Image.open(shots / f"{name}.png").convert("RGB") for name in geo}
    for name, im in images.items():
        if im.width != CSS_W * DSF:
            sys.exit(f"{name}.png is not {CSS_W} CSS px at device scale factor {DSF}: run without --reuse.")
    first, lines, margin = geo["all"], geo["lines"], geo["margin"]
    page_bg = css_color(first["page_bg"])
    top = first["quality"]["y"] - 16
    bottom = min(lines["raw"]["y"] - 16, lines["height"] - VIEW)
    chart = lines["gap_chart"]
    if chart["y"] + chart["h"] > bottom + VIEW:
        sys.exit("The raw files chart does not fit in the view below its section title: raise VIEW.")
    height = max(g["height"] for g in geo.values())

    def image(name: str, y0: float, y1: float) -> str:
        """A band of a screenshot (CSS px) as a WebP <image> in page px."""
        crop = images[name].crop((0, round(y0 * DSF), CSS_W * DSF, round(y1 * DSF)))
        size = (round(CSS_W * K * res), max(1, round((y1 - y0) * K * res)))
        buffer = io.BytesIO()
        crop.resize(size, Image.LANCZOS).save(buffer, "WEBP", quality=quality, method=6)
        encoded = base64.b64encode(buffer.getvalue()).decode()
        return (f'<image x="0" y="{y0 * K:.2f}" width="{CSS_W * K:.2f}" height="{(y1 - y0) * K:.2f}" '
                f'preserveAspectRatio="none" href="data:image/webp;base64,{encoded}"/>')

    m = Motion(T)
    page: list[str] = []  # page coordinates, moved by the scroll
    view: list[str] = []  # fixed in the view: cursor, click rings, scrollbar

    # 1. the page: all tables at the top; order lines from the first click to the last; gross margin in between
    page.append(f'<rect width="{CSS_W * K:.2f}" height="{height * K:.2f}" fill="{page_bg}"/>')
    page.append(image("all", top - 8, top + VIEW + 8))
    page.append(f'<g class="{m.track("opacity", window(CLICK_TABLE + LAG, CLICK_ALL + LAG), 0)}">'
                f'{image("lines", top - 8, bottom + VIEW + 8)}</g>')
    page.append(f'<g class="{m.track("opacity", window(CLICK_METRIC + LAG, CLICK_BACK + LAG), 0)}">'
                f'{image("margin", bottom - 8, bottom + VIEW + 8)}</g>')

    # 2. the scroll: down to the raw files after the first click, back up before the last one
    scroll = [(0, top), (DOWN[0], top), (DOWN[1], bottom), (UP[0], bottom), (UP[1], top), (T, top)]
    scroll_stops = [(t, v, EASE if i + 1 < len(scroll) and scroll[i + 1][1] != v else "linear")
                    for i, (t, v) in enumerate(scroll)]
    scrolling = m.track("transform", [(t, tr(0, -v * K), e) for t, v, e in scroll_stops], tr(0, -top * K))
    thumb_h = VIEW * VIEW / height
    room = VIEW - thumb_h - 6

    def thumb_y(v: float) -> float:
        return v / (height - VIEW) * room

    scrollbar = m.track("transform", [(t, tr(0, thumb_y(v) * K), e) for t, v, e in scroll_stops],
                        tr(0, thumb_y(top) * K))
    view.append(f'<rect class="{scrollbar}" x="{(CSS_W - 7) * K:.2f}" y="{3 * K:.2f}" width="{4 * K:.2f}" '
                f'height="{thumb_h * K:.2f}" rx="{2 * K:.2f}" fill="{INK}" opacity="0.28"/>')

    # 3. the cursor (view coordinates) and its four clicks
    rest = (720, 640)
    clicks = [
        (CLICK_TABLE, center(first["table_labels"][TABLE_LABEL[TABLE]], top)),
        (CLICK_METRIC, center(lines["metric_labels"][METRIC_LABEL[METRIC]], bottom)),
        (CLICK_BACK, center(margin["metric_labels"][METRIC_LABEL["net_revenue"]], bottom)),
        (CLICK_ALL, center(lines["table_labels"][TABLE_LABEL["all"]], top)),
    ]
    path = [(0, rest, "linear"), (0.5, rest, EASE)]
    for t0, point in clicks:
        path += [(t0 - 0.12, point, "linear"), (t0 + 0.35, point, EASE)]
    path += [(CLICK_ALL + 1.4, rest, "linear")]
    # stay on the control while the page scrolls is wrong: move away during the scroll, back after
    path = sorted(path + [(DOWN[0] - 0.1, (rest[0], rest[1]), EASE), (UP[0] - 0.1, (rest[0], rest[1]), EASE)],
                  key=lambda s: s[0])
    cursor_move = m.track("transform", [(t, tr(px * K, py * K), e) for t, (px, py), e in path],
                          tr(rest[0] * K, rest[1] * K))
    cursor_show = m.track("opacity", [(0, 1, "linear")], 0)
    press = [(0, "scale(1)", "linear")]
    for t0, _ in clicks:
        press += [(t0 - 0.08, "scale(1)", EASE_OUT), (t0, "scale(.88)", "linear"), (t0 + 0.12, "scale(.88)", EASE_OUT),
                  (t0 + 0.3, "scale(1)", "linear")]
    cursor_press = m.track("transform", press, "scale(1)")
    for t0, (px, py) in clicks:
        ring = m.track("transform", [(t0, "scale(.2)", EASE_OUT), (t0 + 0.5, "scale(1)", "linear"),
                                     (t0 + 0.51, "scale(.2)", "linear")], "scale(1)")
        fade = m.track("opacity", [(t0 - 0.01, 0, "linear"), (t0, 0.45, EASE_OUT), (t0 + 0.5, 0, "linear")], 0)
        view.append(f'<g transform="translate({px * K:.1f} {py * K:.1f})"><g class="{fade}"><circle class="{ring}" '
                    f'r="18" fill="{look.PRIMARY}" fill-opacity="0.35"/></g></g>')
    view.append(f'<g class="{cursor_show}"><g class="{cursor_move}"><g class="{cursor_press}">'
                f'<path d="{CURSOR}" transform="scale(1.15)" fill="{INK}" stroke="#ffffff" stroke-width="1.3" '
                f'stroke-linejoin="round" filter="url(#shadow)"/></g></g></g>')

    alt = alt_text(values, language)
    vh = VIEW * K
    H = BAR + vh
    css = "".join(m.css) + "@media (prefers-reduced-motion:reduce){*{animation:none!important}}"
    content = (f'<g clip-path="url(#view)"><g transform="translate(0 {BAR})"><g class="{scrolling}">{"".join(page)}'
               f'</g>{"".join(view)}</g></g>')
    out = {}
    for theme, colors in FRAMES.items():
        dots = "".join(f'<circle cx="{18 + i * 16}" cy="{BAR / 2}" r="5" fill="{colors["dot"]}"/>' for i in range(3))
        host, pill_w = "127.0.0.1:8050", 150
        out[theme] = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H:.0f}" width="{W}" height="{H:.0f}" '
            f'role="img" aria-label="{alt}"><title>{alt}</title><defs><style>{css}</style>'
            f'<clipPath id="frame"><rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1:.1f}" rx="10"/></clipPath>'
            f'<clipPath id="view"><rect x="0" y="{BAR}" width="{W}" height="{vh:.1f}"/></clipPath>'
            f'<filter id="shadow" x="-50%" y="-50%" width="200%" height="200%"><feDropShadow dx="0" dy="1.2" '
            f'stdDeviation="1.4" flood-color="#000" flood-opacity="0.35"/></filter></defs>'
            f'<g clip-path="url(#frame)"><rect width="{W}" height="{H:.1f}" fill="{page_bg}"/>{content}'
            f'<rect width="{W}" height="{BAR}" fill="{colors["bar"]}"/>'
            f'<line x1="0" y1="{BAR - 0.5}" x2="{W}" y2="{BAR - 0.5}" stroke="{colors["border"]}"/>{dots}'
            f'<rect x="{W / 2 - pill_w / 2}" y="{BAR / 2 - 11}" width="{pill_w}" height="22" rx="11" '
            f'fill="{colors["pill"]}" stroke="{colors["border"]}"/>'
            f'<text x="{W / 2}" y="{BAR / 2 + 4.3}" text-anchor="middle" font-size="12.5" '
            f'fill="{colors["pill_text"]}" style="font-family:ui-monospace,SFMono-Regular,Consolas,monospace">'
            f'{host}</text></g>'
            f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1:.1f}" rx="10" fill="none" '
            f'stroke="{colors["border"]}"/></svg>')
    return out, {"alt": alt, **values}


def make(shots: Path | None = None, reuse: bool = False, quality: int = 70, res: float = 1.25,
         language: str = "pl") -> dict:
    """Screenshots (unless reuse), then both SVG files; returns the alt text and the numbers shown."""
    shots = shots or ROOT / "output" / "demo-shots"
    shots.mkdir(parents=True, exist_ok=True)
    if not (reuse and (shots / "geometry.json").exists()):
        take_screenshots(shots, numbers())
    svgs, shown = build(shots, quality, res, language)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for theme, svg in svgs.items():
        path = OUT_DIR / ("app-demo.svg" if theme == "light" else "app-demo-dark.svg")
        path.write_text(svg, encoding="utf-8", newline="\n")
        print(f"{path.name}: {path.stat().st_size / 1024:.0f} KB, loop {T:g} s")
        if path.stat().st_size > LIMIT:
            sys.exit(f"{path.name} is over {LIMIT // 1024} KB: lower --quality or --res.")
    return shown


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--shots", type=Path, help="keep the screenshots and geometry in this folder")
    parser.add_argument("--reuse", action="store_true", help="build from --shots without starting the app")
    parser.add_argument("--quality", type=int, default=70, help="WebP quality of the screenshots")
    parser.add_argument("--res", type=float, default=1.25, help="image pixels per SVG pixel")
    parser.add_argument("--lang", choices=("pl", "en"), default="pl", help="language of the description")
    args = parser.parse_args()
    make(args.shots, args.reuse, args.quality, args.res, args.lang)


if __name__ == "__main__":
    main()

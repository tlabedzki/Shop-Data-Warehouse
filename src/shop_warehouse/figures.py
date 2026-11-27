"""
Plotly figures shared by the app and the README charts, in the portfolio look: teal for the warehouse, one copper
mark for what to notice (the raw files, an issue that got through), mist for the rest, value labels at the bars.
Words and number formats follow the language (English for the app, the README's language for its images).
"""
from __future__ import annotations

import math

import pandas as pd
import plotly.graph_objects as go

from shop_warehouse import report
from shop_warehouse import theme as t

CONFIG = {"displayModeBar": False}


def _num(size: int, color) -> dict:
    return {"family": t.NUM_STACK, "size": size, "color": color}


def _layout(fig: go.Figure, height: int, **extra) -> go.Figure:
    margin = extra.pop("margin", {"l": 8, "r": 8, "t": 12, "b": 8})
    fig.update_layout(
        height=height, margin=margin, paper_bgcolor=t.PAGE, plot_bgcolor=t.PAGE,
        font={"family": t.SANS_STACK, "size": 13, "color": t.TEXT}, showlegend=False,
        hoverlabel={"bgcolor": t.PAGE, "bordercolor": t.LINE,
                    "font": {"family": t.SANS_STACK, "color": t.INK, "size": 13}},
        barcornerradius=4, dragmode=False, **{"bargap": 0.32, **extra},
    )
    return fig


def quality_bars(frame: pd.DataFrame, language: str = "en", height: int | None = None) -> go.Figure:
    """One bar per kind of issue: fixed (teal), caught but unknowable (mist), missed or fixed wrongly (copper)."""
    words = report.WORDS[language]
    frame = frame.iloc[::-1]
    labels = [label.replace("-", "\u2010") for label in frame["problem"]]
    fig = go.Figure()
    for column, color in (("fixed", t.PRIMARY), ("caught", t.MIST), ("missed", t.ACCENT)):
        values = frame[column] + (frame["wrong"] if column == "missed" else 0)
        fig.add_bar(y=labels, x=values, orientation="h", name=words[column], marker={"color": color},
                    customdata=[report.integer(v, language) for v in values],
                    hovertemplate=f"%{{y}}<br><b>%{{customdata}}</b> {words[column]}<extra></extra>")
    fig.add_scatter(y=labels, x=frame["injected"], mode="text",
                    text=[report.integer(v, language) for v in frame["injected"]], textposition="middle right",
                    textfont=_num(13, t.TEXT), hoverinfo="skip", cliponaxis=False)
    fig.update_yaxes(showgrid=False, showline=False, ticks="", tickfont={"color": t.TEXT}, fixedrange=True,
                     ticklabelstandoff=8)
    fig.update_xaxes(visible=False, range=[0, float(frame["injected"].max()) * 1.12], fixedrange=True)
    return _layout(fig, height or 30 * len(frame) + 24, barmode="stack", bargap=0.3,
                   margin={"l": 8, "r": 56, "t": 8, "b": 8})


def _time_axis(fig: go.Figure, months: pd.Series, language: str) -> None:
    """Ticks in January and July, month names in the language of the chart."""
    ticks = [stamp for stamp in pd.to_datetime(months) if stamp.month in (1, 7) and stamp.day == 1]
    fig.update_xaxes(showgrid=False, showline=False, ticks="", tickvals=ticks,
                     ticktext=[report.month(stamp, language) for stamp in ticks], tickfont=_num(12, t.MUTED),
                     fixedrange=True)


def _value_axis(fig: go.Figure, values: pd.DataFrame | pd.Series, language: str) -> None:
    """A few round gridlines labelled in the chart's number format; below zero when a value is."""
    top = float(values.max().max()) if isinstance(values, pd.DataFrame) else float(values.max())
    low = min(0.0, float(values.min().min()) if isinstance(values, pd.DataFrame) else float(values.min()))
    span = top - low
    step = 10 ** math.floor(math.log10(span)) if span > 0 else 1
    if span / step < 2:
        step /= 5
    elif span / step < 5:
        step /= 2
    first = math.floor(low / step)
    ticks = [step * i for i in range(first, int(top // step) + 1)]
    fig.update_yaxes(gridcolor=t.LINE, zeroline=low < 0, zerolinecolor=t.MUTED, zerolinewidth=1, showline=False,
                     ticks="", tickvals=ticks, ticktext=[report.compact(v, language) if v else "" for v in ticks],
                     tickfont=_num(12, t.MUTED), fixedrange=True, range=[low - span * 0.04, top + span * 0.06])


def monthly_lines(frame: pd.DataFrame, metric: str, language: str = "en", height: int = 340) -> go.Figure:
    """The warehouse (teal line with area) against a report straight from the raw files (copper)."""
    words = report.WORDS[language]
    unit = report.METRICS[metric][language][1]
    fig = go.Figure()
    series = ((f"{metric}_warehouse", words["warehouse"], t.PRIMARY, 2.5, True),
              (f"{metric}_raw", words["raw"], t.ACCENT, 2.0, False))
    for column, name, color, width, area in series:
        fig.add_scatter(x=frame["month"], y=frame[column], mode="lines", name=name,
                        line={"color": color, "width": width}, fill="tozeroy" if area else None,
                        fillcolor=t.AREA if area else None,
                        customdata=[[report.month(m, language), report.compact(v, language)]
                                    for m, v in zip(frame["month"], frame[column], strict=True)],
                        hovertemplate=f"%{{customdata[0]}}<br>{name} <b>%{{customdata[1]}}</b> {unit}<extra></extra>")
        last = frame.iloc[-1]
        fig.add_annotation(x=last["month"], y=last[column], text=f"<b>{name}</b>", showarrow=False, xanchor="left",
                           xshift=8, font={"family": t.SANS_STACK, "size": 13, "color": color})
    _time_axis(fig, frame["month"], language)
    _value_axis(fig, frame[[f"{metric}_warehouse", f"{metric}_raw"]], language)
    return _layout(fig, height, margin={"l": 8, "r": 104, "t": 12, "b": 8})


def loads_area(frame: pd.DataFrame, language: str = "en", height: int = 220) -> go.Figure:
    """Order lines in each day's file; the busiest day in copper."""
    words = report.WORDS[language]
    peak = frame.loc[frame["order_lines"].idxmax()]
    fig = go.Figure()
    fig.add_scatter(x=frame["day"], y=frame["order_lines"], mode="lines", line={"color": t.PRIMARY, "width": 1.5},
                    fill="tozeroy", fillcolor=t.AREA,
                    customdata=[report.day(d, language) for d in frame["day"]],
                    hovertemplate=f"%{{customdata}}<br><b>%{{y}}</b> {words['order_lines']}<extra></extra>")
    fig.add_scatter(x=[peak["day"]], y=[peak["order_lines"]], mode="markers+text",
                    marker={"color": t.ACCENT, "size": 8}, text=[report.integer(peak["order_lines"], language)],
                    textposition="middle left", textfont=_num(13, t.ACCENT), hoverinfo="skip", cliponaxis=False)
    months = pd.Series(pd.date_range(frame["day"].min(), frame["day"].max(), freq="MS"))
    _time_axis(fig, months, language)
    _value_axis(fig, frame["order_lines"], language)
    return _layout(fig, height, margin={"l": 8, "r": 16, "t": 12, "b": 8})

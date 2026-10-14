"""
The Accessibility tab's three score gauges, as Plotly figures for plotly.js.

The same indicator the Streamlit page draws (`views/module_report.py::_score_gauge`),
smaller, at a fixed pixel size for the same reason: Plotly sizes the number
relative to the trace's box at draw time, so a responsive box can draw it
invisibly small before layout settles. Colours come from `report_model`, which
also decides when a gauge is grey.
"""

import json

import plotly.graph_objects as go

GAUGE_WIDTH = 170
GAUGE_HEIGHT = 110


def gauge(label, pct, colour):
    """A figure as plain JSON-able data. `pct` is None when there is no score."""
    has_score = pct is not None
    r, g, b = int(colour[1:3], 16), int(colour[3:5], 16), int(colour[5:7], 16)
    figure = go.Figure(go.Indicator(
        mode="gauge+number",
        value=pct if has_score else 0,
        number=({"suffix": "%", "font": {"size": 20, "color": colour}} if has_score
                else {"valueformat": "", "suffix": "--", "font": {"size": 20, "color": colour}}),
        title={"text": label, "font": {"size": 11, "color": colour}},
        gauge={"axis": {"range": [0, 100], "visible": False},
               "bar": {"color": colour, "thickness": 1},
               "bgcolor": f"rgba({r},{g},{b},0.12)",
               "borderwidth": 0, "shape": "angular"},
    ))
    figure.update_layout(width=GAUGE_WIDTH, height=GAUGE_HEIGHT,
                         margin=dict(l=15, r=15, t=32, b=0),
                         paper_bgcolor="rgba(0,0,0,0)", font={"color": "#6B7280"})
    return json.loads(figure.to_json())


def gauges_for(ally):
    """One gauge per score in report_model.ally_summary()'s `scores`."""
    return [{"data_id": f"gauge-{i}-data", "sub": sub, "figure": gauge(label, pct, colour)}
            for i, (label, pct, sub, colour) in enumerate(ally.get("scores", []))]


def _line(title, dates, values, colour, percent):
    figure = go.Figure(go.Scatter(
        x=dates, y=values, mode="lines+markers",
        line={"color": colour, "width": 2}, marker={"size": 7},
        hovertemplate="%{x|%d-%m-%Y}: %{y:.1f}" + ("%" if percent else "") + "<extra></extra>"))
    figure.update_layout(
        title={"text": title, "font": {"size": 13}}, height=260,
        margin=dict(l=50, r=20, t=40, b=40), paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)", font={"color": "#6B7280"},
        xaxis={"type": "date", "tickformat": "%d-%m-%Y"},
        yaxis={"ticksuffix": "%" if percent else "", "rangemode": "tozero" if not percent else "normal"})
    return json.loads(figure.to_json())


def trend_figures(trend):
    """The two Trends charts from processing.ally_trend()'s frame: the weighted
    score (as a percentage) and the files uploaded. Dates are ISO strings."""
    dates = [d.strftime("%Y-%m-%d") for d in trend.index]
    return [
        {"data_id": "trend-score-data", "figure": _line(
            "Average accessibility score over time", dates,
            [round(v * 100, 2) for v in trend["Overall score"]], "#2563EB", True)},
        {"data_id": "trend-files-data", "figure": _line(
            "Content uploaded over time", dates,
            [int(v) for v in trend["Files uploaded"]], "#059669", False)},
    ]

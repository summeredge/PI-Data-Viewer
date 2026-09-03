"""Plotly trend chart creation."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go


def create_trend_figure(
    df: pd.DataFrame,
    selected_columns: list[str] | None = None,
    axis_mode: str = "shared",
) -> go.Figure:
    """Create an interactive line chart from a time-indexed DataFrame."""

    if not isinstance(df, pd.DataFrame):
        raise TypeError("df must be a pandas DataFrame")
    if not isinstance(df.index, pd.DatetimeIndex):
        raise TypeError("df must use a pandas DatetimeIndex")
    if axis_mode not in {"shared", "independent"}:
        raise ValueError("axis_mode must be 'shared' or 'independent'")

    figure = go.Figure()
    columns = (
        df.columns
        if selected_columns is None
        else [column for column in df.columns if column in selected_columns]
    )
    for index, column in enumerate(columns):
        trace = go.Scatter(
            x=df.index,
            y=df[column],
            mode="lines",
            name=str(column),
            hovertemplate=(
                "%{x|%Y-%m-%d %H:%M:%S}<br>%{y}<extra>%{fullData.name}</extra>"
            ),
        )
        if axis_mode == "independent" and index:
            trace.yaxis = f"y{index + 1}"
        figure.add_trace(trace)

    xaxis = {
        "title": "Time",
        "type": "date",
        "tickformat": "%Y-%m-%d\n%H:%M:%S",
        "rangeslider": {"visible": False},
    }
    valid_index = df.index.dropna()
    if len(valid_index):
        xaxis.update(
            minallowed=valid_index.min(),
            maxallowed=valid_index.max(),
        )

    y_axes = {"yaxis": {"title": "Value", "fixedrange": True}}
    if axis_mode == "independent":
        y_axes["yaxis"]["title"] = str(columns[0]) if len(columns) else "Value"
        for index, column in enumerate(columns[1:], start=2):
            y_axes[f"yaxis{index}"] = {
                "title": str(column) if index == 2 else None,
                "overlaying": "y",
                "side": "right",
                "fixedrange": True,
                "showgrid": False,
                "showticklabels": index == 2,
            }

    figure.update_layout(
        template="plotly_white",
        hovermode="x unified",
        xaxis=xaxis,
        **y_axes,
        legend={"title": "Tag"},
        margin={"l": 60, "r": 30, "t": 30, "b": 60},
    )
    return figure


create_trend_chart = create_trend_figure


def create_distribution_figure(values, color: str) -> go.Figure:
    """Create the compact histogram and fitted normal curve used by a card."""

    numeric = np.asarray(list(values), dtype=float)
    numeric = numeric[np.isfinite(numeric)]
    figure = go.Figure()
    if not numeric.size:
        figure.add_annotation(
            text="无有效数据",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
            font={"color": "#6b7280"},
        )
        _set_distribution_layout(figure, 1)
        return figure

    minimum = float(numeric.min())
    maximum = float(numeric.max())
    if minimum == maximum:
        counts = np.array([numeric.size])
        centers = np.array([minimum])
        widths = np.array([max(abs(minimum) * 0.05, 1.0)])
        bin_width = 1.0
    else:
        bin_count = min(12, max(1, int(np.ceil(np.sqrt(numeric.size)))))
        counts, edges = np.histogram(numeric, bins=bin_count, range=(minimum, maximum))
        centers = (edges[:-1] + edges[1:]) / 2
        widths = np.diff(edges) * 0.9
        bin_width = (maximum - minimum) / bin_count

    figure.add_trace(
        go.Bar(
            x=centers,
            y=counts,
            width=widths,
            marker={"color": color, "opacity": 0.6},
            hovertemplate="%{y}<extra></extra>",
            showlegend=False,
        )
    )

    curve_y = np.array([])
    std = float(numeric.std(ddof=0))
    if std > 0 and minimum < maximum:
        mean = float(numeric.mean())
        curve_x = np.linspace(minimum, maximum, 41)
        density = np.exp(-0.5 * ((curve_x - mean) / std) ** 2) / (
            std * np.sqrt(2 * np.pi)
        )
        curve_y = density * numeric.size * bin_width
        figure.add_trace(
            go.Scatter(
                x=curve_x,
                y=curve_y,
                mode="lines",
                line={"color": color, "width": 2},
                hoverinfo="skip",
                showlegend=False,
            )
        )

    max_y = max(float(counts.max()), float(curve_y.max()) if curve_y.size else 0.0)
    _set_distribution_layout(figure, max(max_y * 1.1, 1.0))
    return figure


def _set_distribution_layout(figure: go.Figure, max_y: float) -> None:
    figure.update_layout(
        template="plotly_white",
        height=115,
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        paper_bgcolor="white",
        plot_bgcolor="white",
        showlegend=False,
        bargap=0.08,
        xaxis={"visible": False, "fixedrange": True},
        yaxis={"visible": False, "fixedrange": True, "range": [0, max_y]},
    )

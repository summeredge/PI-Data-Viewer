"""Plotly trend chart creation."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go


def create_trend_figure(
    df: pd.DataFrame, selected_columns: list[str] | None = None
) -> go.Figure:
    """Create an interactive line chart from a time-indexed DataFrame."""

    if not isinstance(df, pd.DataFrame):
        raise TypeError("df must be a pandas DataFrame")
    if not isinstance(df.index, pd.DatetimeIndex):
        raise TypeError("df must use a pandas DatetimeIndex")

    figure = go.Figure()
    columns = (
        df.columns
        if selected_columns is None
        else [column for column in df.columns if column in selected_columns]
    )
    for column in columns:
        figure.add_trace(
            go.Scatter(
                x=df.index,
                y=df[column],
                mode="lines",
                name=str(column),
                hovertemplate=(
                    "%{x|%Y-%m-%d %H:%M:%S}<br>%{y}<extra>%{fullData.name}</extra>"
                ),
            )
        )

    figure.update_layout(
        template="plotly_white",
        hovermode="x unified",
        xaxis={
            "title": "Time",
            "type": "date",
            "tickformat": "%Y-%m-%d\n%H:%M:%S",
            "rangeslider": {"visible": False},
        },
        yaxis={"title": "Value"},
        legend={"title": "Tag"},
        margin={"l": 60, "r": 30, "t": 30, "b": 60},
    )
    return figure


create_trend_chart = create_trend_figure

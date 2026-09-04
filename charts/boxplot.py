"""Plotly box plot creation."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go


def _message_figure(message: str) -> go.Figure:
    figure = go.Figure()
    figure.add_annotation(
        text=message,
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        showarrow=False,
        font={"color": "#6b7280", "size": 16},
    )
    figure.update_layout(
        template="plotly_white",
        title="Box Plot",
        height=600,
        margin={"l": 60, "r": 30, "t": 55, "b": 60},
        xaxis={"visible": False},
        yaxis={"visible": False},
    )
    return figure


def create_boxplot_figure(
    dataframe: pd.DataFrame,
    selected_columns: list | tuple | None = None,
) -> go.Figure:
    """Create one Plotly box trace for each selected numeric column."""

    if not isinstance(dataframe, pd.DataFrame):
        raise TypeError("dataframe must be a pandas DataFrame")
    if selected_columns is not None and not isinstance(selected_columns, (list, tuple)):
        raise TypeError("selected_columns must be a list or tuple")

    columns = (
        list(dataframe.columns)
        if selected_columns is None
        else [column for column in dataframe.columns if column in selected_columns]
    )
    if not columns:
        return _message_figure("请至少选择一个变量")

    figure = go.Figure()
    for column in columns:
        values = pd.to_numeric(dataframe[column], errors="coerce").to_numpy(dtype=float)
        values = values[np.isfinite(values)]
        if values.size:
            figure.add_trace(
                go.Box(
                    y=values,
                    name=str(column),
                    boxpoints="outliers",
                    marker={"size": 5},
                )
            )

    if not figure.data:
        return _message_figure("所选变量无有效数值数据")

    figure.update_layout(
        template="plotly_white",
        title="Box Plot",
        height=600,
        margin={"l": 60, "r": 30, "t": 55, "b": 60},
        xaxis={"title": "Variable"},
        yaxis={"title": "Value"},
        showlegend=False,
    )
    return figure


create_boxplot_chart = create_boxplot_figure

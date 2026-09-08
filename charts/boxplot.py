"""Plotly box plot creation."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from backend.pi_reader import MAX_TAGS


_BOX_COLUMNS = MAX_TAGS


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
        title="箱线图",
        height=600,
        margin={"l": 60, "r": 30, "t": 55, "b": 60},
        xaxis={"visible": False},
        yaxis={"visible": False},
    )
    return figure


def create_boxplot_figure(
    dataframe: pd.DataFrame,
    selected_columns: list | tuple | None = None,
    axis_mode: str = "independent",
) -> go.Figure:
    """Create one Plotly box trace for each selected numeric column."""

    if not isinstance(dataframe, pd.DataFrame):
        raise TypeError("dataframe must be a pandas DataFrame")
    if selected_columns is not None and not isinstance(selected_columns, (list, tuple)):
        raise TypeError("selected_columns must be a list or tuple")
    if axis_mode not in {"independent", "shared"}:
        raise ValueError("axis_mode must be 'independent' or 'shared'")

    columns = (
        list(dataframe.columns)
        if selected_columns is None
        else [column for column in dataframe.columns if column in selected_columns]
    )
    if not columns:
        return _message_figure("请至少选择一个变量")

    values_by_column = []
    for column in columns:
        values = pd.to_numeric(dataframe[column], errors="coerce").to_numpy(dtype=float)
        values = values[np.isfinite(values)]
        if values.size:
            values_by_column.append((column, values))

    if not values_by_column:
        return _message_figure("所选变量无有效数值数据")

    figure = make_subplots(
        rows=1,
        cols=_BOX_COLUMNS,
        shared_yaxes=axis_mode == "shared",
        column_widths=[1 / _BOX_COLUMNS] * _BOX_COLUMNS,
    )
    for index, (column, values) in enumerate(values_by_column, start=1):
        figure.add_trace(
            go.Box(
                y=values,
                name=str(column),
                boxpoints="outliers",
                marker={"size": 5},
            ),
            row=1,
            col=index,
        )
        figure.update_xaxes(
            visible=True,
            tickangle=-30,
            automargin=True,
            row=1,
            col=index,
        )
        figure.update_yaxes(visible=True, automargin=True, row=1, col=index)

    for empty_index in range(len(values_by_column) + 1, _BOX_COLUMNS + 1):
        figure.update_xaxes(visible=False, row=1, col=empty_index)
        figure.update_yaxes(visible=False, row=1, col=empty_index)

    figure.update_layout(
        template="plotly_white",
        title="箱线图",
        height=600,
        margin={"l": 60, "r": 30, "t": 55, "b": 110},
        showlegend=False,
    )
    return figure

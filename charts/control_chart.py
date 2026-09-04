"""Plotly I-MR control chart creation."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from backend.spc import calculate_imr


DEFAULT_MAX_CONTROL_POINTS = 45_000
MAX_CONTROL_POINTS = 135_000
SINGLE_VARIABLE_MESSAGE = (
    "I-MR Chart requires exactly one selected variable. Please select one Tag."
)
_VALUE_COLOR = "#1769b0"
_LIMIT_COLOR = "#b54708"
_CENTER_COLOR = "#374151"
_OUTLIER_COLOR = "#b42318"


def _message_figure(message: str) -> go.Figure:
    figure = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        subplot_titles=("Individual Chart", "Moving Range Chart"),
    )
    figure.add_annotation(
        text=message,
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        showarrow=False,
        font={"color": "#6b7280", "size": 16},
    )
    _set_layout(figure)
    return figure


def _selected_column(dataframe: pd.DataFrame, selected_columns) -> str | None:
    if selected_columns is None:
        columns = list(dataframe.columns)
    elif isinstance(selected_columns, (list, tuple)):
        columns = [column for column in dataframe.columns if column in selected_columns]
    else:
        columns = []
    return columns[0] if len(columns) == 1 else None


def _resolve_max_points(value) -> int:
    if value in (None, ""):
        return DEFAULT_MAX_CONTROL_POINTS
    try:
        requested = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("最大控制图点数必须是正整数") from exc
    if requested < 1:
        raise ValueError("最大控制图点数必须是正整数")
    return min(requested, MAX_CONTROL_POINTS)


def _sample_positions(length: int, max_points: int, required) -> list[int]:
    if length <= max_points:
        return list(range(length))

    base = (
        [
            int(index * (length - 1) / (max_points - 1))
            for index in range(max_points)
        ]
        if max_points > 1
        else [0]
    )
    required = sorted(set(required))
    if len(required) >= max_points:
        return required[:max_points]

    remaining = max_points - len(required)
    available = [position for position in base if position not in required]
    if len(available) > remaining:
        chosen = np.linspace(0, len(available) - 1, remaining, dtype=int)
        available = [available[index] for index in chosen]
    return sorted(set(required + available))


def _add_limit_trace(
    figure: go.Figure,
    index: pd.Index,
    value: float,
    name: str,
    row: int,
    dash: str,
) -> None:
    figure.add_trace(
        go.Scatter(
            x=[index[0], index[-1]],
            y=[value, value],
            mode="lines",
            name=name,
            line={
                "color": _CENTER_COLOR if name in {"CL", "MR CL"} else _LIMIT_COLOR,
                "dash": dash,
                "width": 1.5,
            },
            hovertemplate=f"{name}: %{{y}}<extra></extra>",
        ),
        row=row,
        col=1,
    )


def _set_layout(figure: go.Figure) -> None:
    figure.update_layout(
        template="plotly_white",
        title="I-MR Chart",
        height=760,
        hovermode="x unified",
        margin={"l": 65, "r": 30, "t": 70, "b": 85},
        legend={
            "orientation": "h",
            "x": 0,
            "xanchor": "left",
            "y": -0.12,
            "yanchor": "top",
        },
    )
    figure.update_xaxes(
        type="date",
        tickformat="%Y-%m-%d\n%H:%M:%S",
        row=1,
        col=1,
    )
    figure.update_xaxes(
        title_text="Time",
        type="date",
        tickformat="%Y-%m-%d\n%H:%M:%S",
        row=2,
        col=1,
    )
    figure.update_yaxes(title_text="Value", fixedrange=True, row=1, col=1)
    figure.update_yaxes(
        title_text="Moving Range", fixedrange=True, row=2, col=1
    )


def create_control_chart(
    dataframe: pd.DataFrame,
    selected_columns: list | tuple | None = None,
    max_points: int = DEFAULT_MAX_CONTROL_POINTS,
) -> go.Figure:
    """Create an Individual and Moving Range chart from one selected column."""

    if not isinstance(dataframe, pd.DataFrame):
        raise TypeError("dataframe must be a pandas DataFrame")
    if not isinstance(dataframe.index, pd.DatetimeIndex):
        raise TypeError("dataframe must use a pandas DatetimeIndex")

    column = _selected_column(dataframe, selected_columns)
    if column is None:
        return _message_figure(SINGLE_VARIABLE_MESSAGE)

    try:
        result = calculate_imr(dataframe[column])
    except ValueError as exc:
        return _message_figure(str(exc))
    values = result["values"]
    moving_range = result["moving_range"]
    individual_outliers = result["individual_outliers"]
    moving_range_outliers = result["moving_range_outliers"]
    max_points = _resolve_max_points(max_points)
    required = np.flatnonzero(
        individual_outliers.to_numpy(dtype=bool)
        | moving_range_outliers.to_numpy(dtype=bool)
    )
    positions = _sample_positions(len(values), max_points, required)
    display_values = values.iloc[positions]
    display_moving_range = moving_range.iloc[positions]
    display_individual_outliers = individual_outliers.iloc[positions]
    display_moving_range_outliers = moving_range_outliers.iloc[positions]

    figure = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.12,
        subplot_titles=("Individual Chart", "Moving Range Chart"),
    )
    hovertemplate = "%{x|%Y-%m-%d %H:%M:%S}<br>值: %{y}<extra>%{fullData.name}</extra>"
    figure.add_trace(
        go.Scattergl(
            x=display_values.index,
            y=display_values,
            mode="lines+markers",
            name=str(column),
            line={"color": _VALUE_COLOR, "width": 1.2},
            marker={"size": 4},
            hovertemplate=hovertemplate,
        ),
        row=1,
        col=1,
    )
    if display_individual_outliers.any():
        figure.add_trace(
            go.Scattergl(
                x=display_values.index,
                y=display_values.where(display_individual_outliers),
                mode="markers",
                name="异常点",
                marker={"color": _OUTLIER_COLOR, "size": 8},
                hovertemplate=hovertemplate,
                showlegend=False,
            ),
            row=1,
            col=1,
        )
    _add_limit_trace(
        figure,
        display_values.index,
        result["individual_cl"],
        "CL",
        1,
        "dash",
    )
    _add_limit_trace(
        figure,
        display_values.index,
        result["individual_ucl"],
        "UCL",
        1,
        "dot",
    )
    _add_limit_trace(
        figure,
        display_values.index,
        result["individual_lcl"],
        "LCL",
        1,
        "dot",
    )

    figure.add_trace(
        go.Scattergl(
            x=display_moving_range.index,
            y=display_moving_range,
            mode="lines+markers",
            name="Moving Range",
            line={"color": "#6d28d9", "width": 1.2},
            marker={"size": 4},
            hovertemplate=hovertemplate,
        ),
        row=2,
        col=1,
    )
    if display_moving_range_outliers.any():
        figure.add_trace(
            go.Scattergl(
                x=display_moving_range.index,
                y=display_moving_range.where(display_moving_range_outliers),
                mode="markers",
                name="MR异常点",
                marker={"color": _OUTLIER_COLOR, "size": 8},
                hovertemplate=hovertemplate,
                showlegend=False,
            ),
            row=2,
            col=1,
        )
    _add_limit_trace(figure, display_moving_range.index, result["mr_cl"], "MR CL", 2, "dash")
    _add_limit_trace(
        figure,
        display_moving_range.index,
        result["mr_ucl"],
        "MR UCL",
        2,
        "dot",
    )
    _add_limit_trace(
        figure,
        display_moving_range.index,
        result["mr_lcl"],
        "MR LCL",
        2,
        "dot",
    )
    _set_layout(figure)
    return figure


create_control_chart_figure = create_control_chart

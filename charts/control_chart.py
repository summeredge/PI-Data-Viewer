"""Plotly I-MR control chart creation."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from backend.spc import calculate_imr, calculate_staged_imr


DEFAULT_MAX_CONTROL_POINTS = 45_000
MAX_CONTROL_POINTS = 135_000
SINGLE_VARIABLE_MESSAGE = "I-MR 控制图仅支持单变量，请只选择一个位号"
_VALUE_COLOR = "#1769b0"
_LIMIT_COLOR = "#b54708"
_CENTER_COLOR = "#374151"
_OUTLIER_COLOR = "#b42318"
_BOUNDARY_COLOR = "#6b7280"


def _message_figure(message: str) -> go.Figure:
    figure = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        subplot_titles=("单值图", "移动极差图"),
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
        chosen = np.linspace(0, len(required) - 1, max_points, dtype=int)
        return [required[index] for index in chosen]

    remaining = max_points - len(required)
    available = [position for position in base if position not in required]
    if len(available) > remaining:
        chosen = np.linspace(0, len(available) - 1, remaining, dtype=int)
        available = [available[index] for index in chosen]
    return sorted(set(required + available))


def _add_limit_trace(
    figure: go.Figure,
    segments: list[tuple[pd.Timestamp, pd.Timestamp, float]],
    name: str,
    row: int,
    dash: str,
    labels: bool = False,
) -> None:
    """Draw one control limit segment per stage.

    None breakers stop a segment at its stage boundary instead of joining the
    next stage's limit line. `labels` only adds the numeric text, never changes
    the value that is drawn.
    """
    color = (
        _CENTER_COLOR
        if name in {"中心线（CL）", "移动极差中心线（MR CL）"}
        else _LIMIT_COLOR
    )
    figure.add_trace(
        go.Scatter(
            x=[
                stamp
                for start, end, _ in segments
                for stamp in (start, end, None)
            ],
            y=[
                limit
                for _, _, limit in segments
                for limit in (limit, limit, None)
            ],
            mode="lines",
            name=name,
            line={"color": color, "dash": dash, "width": 1.5},
            hovertemplate=f"{name}: %{{y}}<extra></extra>",
        ),
        row=row,
        col=1,
    )
    if labels:
        figure.add_trace(
            go.Scatter(
                x=[start + (end - start) / 2 for start, end, _ in segments],
                y=[limit for _, _, limit in segments],
                mode="text",
                text=[f"{limit:.6g}" for _, _, limit in segments],
                textposition="top center",
                textfont={"color": color, "size": 10},
                name=f"{name}标签",
                showlegend=False,
                hoverinfo="skip",
            ),
            row=row,
            col=1,
        )


def _add_stage_markers(figure: go.Figure, boundaries) -> None:
    """Dashed boundary line on both plots, plus the stage names on the I chart."""
    for boundary in boundaries:
        for row in (1, 2):
            figure.add_vline(
                x=boundary,
                line={"color": _BOUNDARY_COLOR, "dash": "dash", "width": 1},
                row=row,
                col=1,
            )
    for stage_number, start in enumerate([None, *boundaries], start=1):
        # 阶段名紧贴本阶段起点右侧；阶段 1 没有左边界，用纸坐标钉在图左侧。
        first = start is None
        figure.add_annotation(
            x=0.004 if first else start,
            y=0.985,
            xref="paper" if first else "x",
            yref="y domain",
            text=f"阶段 {stage_number}",
            showarrow=False,
            xanchor="left",
            yanchor="top",
            font={"color": _BOUNDARY_COLOR, "size": 11},
        )


def _set_layout(figure: go.Figure) -> None:
    figure.update_layout(
        template="plotly_white",
        title="I-MR 控制图",
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
        title_text="时间",
        type="date",
        tickformat="%Y-%m-%d\n%H:%M:%S",
        row=2,
        col=1,
    )
    figure.update_yaxes(title_text="数值", fixedrange=True, row=1, col=1)
    figure.update_yaxes(
        title_text="移动极差", fixedrange=True, row=2, col=1
    )


def _add_signal_trace(
    figure: go.Figure,
    values: pd.Series,
    signals: pd.Series,
    test_results: dict[int, pd.Series],
    positions: list[int],
    name: str,
    row: int,
) -> None:
    if not signals.any():
        return
    failed_tests = [
        [test for test, failed in test_results.items() if failed.iloc[position]]
        for position in positions
    ]
    labels = ["、".join(f"检验 {test}" for test in tests) for tests in failed_tests]
    display_numbers = [", ".join(map(str, tests)) for tests in failed_tests]
    figure.add_trace(
        go.Scattergl(
            x=values.index,
            y=values.where(signals),
            mode="markers+text",
            name=name,
            marker={"color": _OUTLIER_COLOR, "size": 8},
            text=display_numbers,
            textposition="top center",
            textfont={"color": _OUTLIER_COLOR, "size": 10},
            customdata=labels,
            hovertemplate=(
                "%{x|%Y-%m-%d %H:%M:%S}<br>值: %{y}"
                "<br>%{customdata}<extra></extra>"
            ),
            showlegend=False,
        ),
        row=row,
        col=1,
    )


def _signal_series(stage: dict, key: str) -> pd.Series:
    """Signals re-indexed to the stage values so .iloc() lines up with positions."""
    return stage[key].reindex(stage["values"].index, fill_value=False)


def _stage_positions(stages, max_points: int) -> list[list[int]]:
    """Split the display point budget across stages in proportion to size."""
    weights = np.array([len(stage["values"]) for stage in stages], dtype=float)
    shares = np.maximum(1, np.floor(weights / weights.sum() * max_points))
    return [
        _sample_positions(
            len(stage["values"]),
            min(int(share), len(stage["values"])),
            np.flatnonzero(
                _signal_series(stage, "individual_signals").to_numpy(dtype=bool)
                | _signal_series(stage, "moving_range_signals").to_numpy(dtype=bool)
            ),
        )
        for stage, share in zip(stages, shares)
    ]


def _stage_limits(stages, key: str) -> list[tuple[pd.Timestamp, pd.Timestamp, float]]:
    """One limit segment per stage, ending at that stage's own last sample."""
    return [
        (stage["values"].index[0], stage["values"].index[-1], stage[key])
        for stage in stages
    ]


def create_control_chart(
    dataframe: pd.DataFrame,
    selected_columns: list | tuple | None = None,
    max_points: int = DEFAULT_MAX_CONTROL_POINTS,
    tests=None,
    boundaries=None,
    limit_labels: bool = False,
) -> go.Figure:
    """Create an Individual and Moving Range chart from one selected column.

    `boundaries` splits the series into stages, each with its own control limits
    and its own restart of moving ranges and special-cause runs; without
    boundaries the chart is the unchanged single-stage chart.
    """

    if not isinstance(dataframe, pd.DataFrame):
        raise TypeError("dataframe must be a pandas DataFrame")
    if not isinstance(dataframe.index, pd.DatetimeIndex):
        raise TypeError("dataframe must use a pandas DatetimeIndex")

    column = _selected_column(dataframe, selected_columns)
    if column is None:
        return _message_figure(SINGLE_VARIABLE_MESSAGE)

    stamps = [] if boundaries is None else list(boundaries)
    try:
        stages = (
            calculate_staged_imr(dataframe[column], stamps, tests=tests)
            if stamps
            else [dict(calculate_imr(dataframe[column], tests=tests), stage=1)]
        )
    except ValueError as exc:
        return _message_figure(str(exc))
    max_points = _resolve_max_points(max_points)
    positions = _stage_positions(stages, max_points)

    figure = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.12,
        subplot_titles=("单值图", "移动极差图"),
    )
    hovertemplate = "%{x|%Y-%m-%d %H:%M:%S}<br>值: %{y}<extra>%{fullData.name}</extra>"
    for stage, stage_positions in zip(stages, positions):
        first_stage = stage["stage"] == 1
        display_values = stage["values"].iloc[stage_positions]
        display_moving_range = stage["moving_range"].iloc[stage_positions]
        figure.add_trace(
            go.Scattergl(
                x=display_values.index,
                y=display_values,
                mode="lines+markers",
                name=str(column),
                line={"color": _VALUE_COLOR, "width": 1.2},
                marker={"size": 4},
                hovertemplate=hovertemplate,
                showlegend=first_stage,
            ),
            row=1,
            col=1,
        )
        _add_signal_trace(
            figure,
            display_values,
            _signal_series(stage, "individual_signals").iloc[stage_positions],
            stage["individual_tests"],
            stage_positions,
            "异常点",
            1,
        )
        figure.add_trace(
            go.Scattergl(
                x=display_moving_range.index,
                y=display_moving_range,
                mode="lines+markers",
                name="移动极差",
                line={"color": "#6d28d9", "width": 1.2},
                marker={"size": 4},
                hovertemplate=hovertemplate,
                showlegend=first_stage,
            ),
            row=2,
            col=1,
        )
        _add_signal_trace(
            figure,
            display_moving_range,
            _signal_series(stage, "moving_range_signals").iloc[stage_positions],
            stage["moving_range_tests"],
            stage_positions,
            "MR异常点",
            2,
        )

    for key, name, row, dash in (
        ("individual_cl", "中心线（CL）", 1, "dash"),
        ("individual_ucl", "上控制限（UCL）", 1, "dot"),
        ("individual_lcl", "下控制限（LCL）", 1, "dot"),
        ("mr_cl", "移动极差中心线（MR CL）", 2, "dash"),
        ("mr_ucl", "移动极差上控制限（MR UCL）", 2, "dot"),
        ("mr_lcl", "移动极差下控制限（MR LCL）", 2, "dot"),
    ):
        # 单段图不加标签，保持未启用阶段时的图形与以前一致。
        _add_limit_trace(
            figure,
            _stage_limits(stages, key),
            name,
            row,
            dash,
            limit_labels and len(stages) > 1,
        )
    if stamps:
        _add_stage_markers(figure, stamps)
    _set_layout(figure)
    return figure

"""Plotly XY scatter-matrix creation."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


MAX_SCATTER_VARIABLES = 3
DEFAULT_MAX_SCATTER_POINTS = 100_000
MAX_TOTAL_SCATTER_POINTS = 300_000


def calculate_scatter_dimensions(rows: int, cols: int) -> tuple[int, int]:
    """Return the fixed dimensions used by non-3x3 scatter matrices."""

    if int(rows) == int(cols) == 2:
        return 840, 840
    width = min(840, max(420, 280 * max(1, int(cols))))
    height = min(720, max(420, 240 * max(1, int(rows))))
    return width, height


def _selected_columns(columns, axis_label: str) -> list:
    if not isinstance(columns, (list, tuple)):
        raise ValueError(f"请至少选择一个{axis_label}变量")

    selected = [column for column in columns if column not in (None, "")]
    if not selected:
        raise ValueError(f"请至少选择一个{axis_label}变量")
    if len(selected) > MAX_SCATTER_VARIABLES:
        raise ValueError(f"{axis_label}变量最多选择{MAX_SCATTER_VARIABLES}个")
    if len(set(selected)) != len(selected):
        raise ValueError(f"{axis_label}变量不能重复")
    return selected


def _max_points(value, pair_count: int) -> int:
    if value in (None, ""):
        requested = DEFAULT_MAX_SCATTER_POINTS
    else:
        try:
            requested = int(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("最大散点数量必须是正整数") from exc
        if requested < 1:
            raise ValueError("最大散点数量必须是正整数")
    return min(
        requested,
        DEFAULT_MAX_SCATTER_POINTS,
        MAX_TOTAL_SCATTER_POINTS // pair_count,
    )


def prepare_scatter_frame(
    df: pd.DataFrame,
    x_columns,
    y_columns,
    max_points=DEFAULT_MAX_SCATTER_POINTS,
) -> tuple[list, list, pd.DataFrame, pd.DataFrame]:
    """Validate selections, keep finite rows, and deterministically sample them."""

    if not isinstance(df, pd.DataFrame):
        raise TypeError("df must be a pandas DataFrame")

    x_selected = _selected_columns(x_columns, "X")
    y_selected = _selected_columns(y_columns, "Y")
    missing = [
        column
        for column in [*x_selected, *y_selected]
        if column not in df.columns
    ]
    if missing:
        raise ValueError(f"变量不存在：{', '.join(map(str, missing))}")

    max_points = _max_points(
        max_points, len(x_selected) * len(y_selected)
    )
    columns = list(dict.fromkeys([*x_selected, *y_selected]))
    numeric = df.loc[:, columns].apply(pd.to_numeric, errors="coerce")
    valid_mask = np.isfinite(numeric.to_numpy(dtype=float)).all(axis=1)
    valid = numeric.loc[valid_mask]
    if valid.empty:
        raise ValueError("无有效数据，无法生成散点矩阵")

    display = valid
    if len(display) > max_points:
        positions = np.linspace(0, len(display) - 1, max_points, dtype=int)
        display = display.iloc[positions]
    return x_selected, y_selected, valid, display


def create_scatter_figure(
    df: pd.DataFrame,
    x_columns,
    y_columns,
    max_points=DEFAULT_MAX_SCATTER_POINTS,
) -> go.Figure:
    """Create an interactive Plotly XY scatter matrix."""

    x_selected, y_selected, _, display = prepare_scatter_frame(
        df, x_columns, y_columns, max_points
    )
    rows = len(y_selected)
    cols = len(x_selected)
    subplot_options = (
        {"horizontal_spacing": 0.04, "vertical_spacing": 0.04}
        if (rows, cols) == (3, 3)
        else {}
    )
    figure = make_subplots(
        rows=rows,
        cols=cols,
        **subplot_options,
    )
    customdata = [str(value) for value in display.index]

    for row, y_column in enumerate(y_selected, start=1):
        for column, x_column in enumerate(x_selected, start=1):
            figure.add_trace(
                go.Scattergl(
                    x=display[x_column],
                    y=display[y_column],
                    customdata=customdata,
                    mode="markers",
                    name=f"{y_column} vs {x_column}",
                    marker={"size": 6, "opacity": 0.75},
                    hovertemplate=(
                        f"时间: %{{customdata}}<br>"
                        f"{x_column}: %{{x}}<br>"
                        f"{y_column}: %{{y}}<extra></extra>"
                    ),
                    showlegend=False,
                ),
                row=row,
                col=column,
            )
            figure.update_xaxes(title_text=str(x_column), row=row, col=column)
            figure.update_yaxes(title_text=str(y_column), row=row, col=column)

    figure.update_layout(
        template="plotly_white",
        title="XY 散点矩阵",
        autosize=True,
        hovermode="closest",
        showlegend=False,
        margin={"l": 60, "r": 60, "t": 60, "b": 60},
    )
    if (rows, cols) != (3, 3):
        width, height = calculate_scatter_dimensions(rows, cols)
        figure.update_layout(
            width=width,
            height=height,
            margin={"l": 60, "r": 30, "t": 55, "b": 60},
        )
    return figure


create_scatter_chart = create_scatter_figure

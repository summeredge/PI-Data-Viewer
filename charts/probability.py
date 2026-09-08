"""Normal probability plot rendering for the shared DataFrame."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from scipy import stats


SINGLE_VARIABLE_MESSAGE = "概率图仅支持单变量，请只选择一个变量"
NO_SELECTION_MESSAGE = "请选择一个变量"
NO_VALID_DATA_MESSAGE = "所选变量无有效数值数据"
INSUFFICIENT_DATA_MESSAGE = "有效数值点不足，至少需要 3 个有限数值点"
CONSTANT_DATA_MESSAGE = "所有有效数值相同，无法生成有意义的概率图"
INVALID_FIT_MESSAGE = "无法计算有效的正态拟合参考线"

_PROBABILITY_TICKS = (1, 5, 10, 20, 50, 80, 90, 95, 99)


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
        title="概率图",
        height=600,
        margin={"l": 70, "r": 30, "t": 55, "b": 70},
        xaxis={"visible": False},
        yaxis={"visible": False},
    )
    return figure


def create_probability_plot_figure(
    dataframe: pd.DataFrame,
    selected_columns: list | tuple | None = None,
) -> go.Figure:
    """Create a normal probability plot using one selected DataFrame column."""

    if not isinstance(selected_columns, (list, tuple)) or not selected_columns:
        return _message_figure(NO_SELECTION_MESSAGE)
    if len(selected_columns) != 1:
        return _message_figure(SINGLE_VARIABLE_MESSAGE)
    if dataframe is None or not isinstance(dataframe, pd.DataFrame):
        return _message_figure(NO_VALID_DATA_MESSAGE)

    column = selected_columns[0]
    if column not in dataframe.columns:
        return _message_figure(NO_VALID_DATA_MESSAGE)

    try:
        values = pd.to_numeric(dataframe[column], errors="coerce").to_numpy(
            dtype=float,
            na_value=np.nan,
        )
    except (TypeError, ValueError):
        return _message_figure(NO_VALID_DATA_MESSAGE)
    values = values[np.isfinite(values)]

    if values.size == 0:
        return _message_figure(NO_VALID_DATA_MESSAGE)
    if values.size < 3:
        return _message_figure(INSUFFICIENT_DATA_MESSAGE)
    if np.all(values == values[0]):
        return _message_figure(CONSTANT_DATA_MESSAGE)

    try:
        (theoretical_quantiles, ordered_values), (slope, intercept, _) = stats.probplot(
            values, dist="norm"
        )
    except (TypeError, ValueError, FloatingPointError):
        return _message_figure(INVALID_FIT_MESSAGE)

    theoretical_quantiles = np.asarray(theoretical_quantiles, dtype=float)
    ordered_values = np.asarray(ordered_values, dtype=float)
    slope = float(slope)
    intercept = float(intercept)
    if (
        not np.isfinite(theoretical_quantiles).all()
        or not np.isfinite(ordered_values).all()
        or not np.isfinite(slope)
        or not np.isfinite(intercept)
        or slope == 0
    ):
        return _message_figure(INVALID_FIT_MESSAGE)

    fit_x = np.array([ordered_values[0], ordered_values[-1]], dtype=float)
    fit_y = (fit_x - intercept) / slope
    if not np.isfinite(fit_y).all():
        return _message_figure(INVALID_FIT_MESSAGE)

    probabilities = stats.norm.cdf(theoretical_quantiles) * 100
    tick_pairs = [
        (probability, stats.norm.ppf(probability / 100))
        for probability in _PROBABILITY_TICKS
    ]
    lower, upper = theoretical_quantiles[[0, -1]]
    visible_ticks = [
        (probability, tick)
        for probability, tick in tick_pairs
        if probability == 50 or lower <= tick <= upper
    ]

    column_label = str(column) or "数值"
    figure = go.Figure()
    figure.add_trace(
        go.Scattergl(
            name="概率点",
            x=ordered_values,
            y=theoretical_quantiles,
            mode="markers",
            marker={"color": "#176b87", "size": 7},
            customdata=probabilities,
            hovertemplate=(
                "数值：%{x}<br>"
                "累积概率：%{customdata:.3f}%<extra></extra>"
            ),
        )
    )
    figure.add_trace(
        go.Scatter(
            name="正态拟合",
            x=fit_x,
            y=fit_y,
            mode="lines",
            line={"color": "#b42318", "width": 2},
            hovertemplate="正态拟合<extra></extra>",
        )
    )
    figure.update_layout(
        template="plotly_white",
        title=f"概率图 - {column_label}",
        height=600,
        margin={"l": 80, "r": 30, "t": 55, "b": 70},
        hovermode="closest",
        showlegend=True,
    )
    figure.update_xaxes(title_text=column_label)
    figure.update_yaxes(
        title_text="累积概率（%）",
        tickmode="array",
        tickvals=[tick for _, tick in visible_ticks],
        ticktext=[f"{probability:g}%" for probability, _ in visible_ticks],
    )
    return figure

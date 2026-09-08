"""Plotly rendering for normal process capability analysis."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from scipy.stats import norm


SINGLE_VARIABLE_MESSAGE = "能力分析仅支持单变量，请只选择一个变量"
NO_SELECTION_MESSAGE = "请至少选择一个变量"
NO_RESULT_MESSAGE = "无法生成能力分析"


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
        title="正态能力分析",
        height=600,
        margin={"l": 70, "r": 30, "t": 55, "b": 70},
        xaxis={"visible": False},
        yaxis={"visible": False},
    )
    return figure


def _selected_column(dataframe: pd.DataFrame, selected_columns) -> str | None:
    if not isinstance(selected_columns, (list, tuple)) or len(selected_columns) != 1:
        return None
    column = selected_columns[0]
    return column if column in dataframe.columns else None


def create_capability_figure(
    dataframe: pd.DataFrame,
    selected_columns,
    capability_result: dict[str, object] | None,
) -> go.Figure:
    """Create a normal capability histogram from a calculated result."""

    if not isinstance(dataframe, pd.DataFrame):
        raise TypeError("dataframe must be a pandas DataFrame")
    if not isinstance(selected_columns, (list, tuple)) or not selected_columns:
        return _message_figure(NO_SELECTION_MESSAGE)
    if len(selected_columns) != 1:
        return _message_figure(SINGLE_VARIABLE_MESSAGE)
    if _selected_column(dataframe, selected_columns) is None:
        return _message_figure(NO_RESULT_MESSAGE)
    if not isinstance(capability_result, dict):
        return _message_figure(NO_RESULT_MESSAGE)

    try:
        values = np.asarray(
            pd.to_numeric(capability_result["values"], errors="coerce"),
            dtype=float,
        )
        values = values[np.isfinite(values)]
        mean = float(capability_result["mean"])
        within_sigma = float(capability_result["within_sigma"])
        overall_sigma = float(capability_result["overall_sigma"])
        lsl = capability_result.get("lsl")
        usl = capability_result.get("usl")
        lsl = None if lsl is None else float(lsl)
        usl = None if usl is None else float(usl)
    except (KeyError, TypeError, ValueError, OverflowError):
        return _message_figure(NO_RESULT_MESSAGE)

    if (
        not values.size
        or not np.isfinite(mean)
        or not np.isfinite(within_sigma)
        or not np.isfinite(overall_sigma)
        or within_sigma <= 0
        or overall_sigma <= 0
        or any(limit is not None and not np.isfinite(limit) for limit in (lsl, usl))
    ):
        return _message_figure(NO_RESULT_MESSAGE)

    extent = [float(values.min()), float(values.max()), mean]
    extent.extend(limit for limit in (lsl, usl) if limit is not None)
    lower, upper = min(extent), max(extent)
    span = upper - lower
    padding = max(span * 0.05, 1e-12)
    x_values = np.linspace(lower - padding, upper + padding, 200)
    within_density = norm.pdf(x_values, loc=mean, scale=within_sigma)
    overall_density = norm.pdf(x_values, loc=mean, scale=overall_sigma)
    curve_max = max(float(within_density.max()), float(overall_density.max()), 1e-12)
    column_label = str(selected_columns[0]) or "数值"

    figure = go.Figure()
    figure.add_trace(
        go.Histogram(
            x=values,
            histnorm="probability density",
            name="直方图",
            marker_color="#8ecae6",
            opacity=0.7,
            hovertemplate="数值：%{x}<br>密度：%{y}<extra></extra>",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=x_values,
            y=within_density,
            mode="lines",
            name="组内正态曲线",
            line={"color": "#b42318", "width": 2},
            hovertemplate="组内正态曲线<extra></extra>",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=x_values,
            y=overall_density,
            mode="lines",
            name="整体正态曲线",
            line={"color": "#176b87", "width": 2, "dash": "dash"},
            hovertemplate="整体正态曲线<extra></extra>",
        )
    )
    for name, limit in (("规格下限（LSL）", lsl), ("规格上限（USL）", usl)):
        if limit is not None:
            figure.add_trace(
                go.Scatter(
                    x=[limit, limit],
                    y=[0, curve_max * 1.05],
                    mode="lines",
                    name=name,
                    line={"color": "#c2410c", "dash": "dot", "width": 2},
                    hovertemplate=f"{name}: %{{x}}<extra></extra>",
                )
            )

    figure.update_layout(
        template="plotly_white",
        title=f"正态能力分析 - {column_label}",
        height=600,
        barmode="overlay",
        hovermode="x unified",
        margin={"l": 70, "r": 30, "t": 55, "b": 70},
        showlegend=True,
    )
    figure.update_xaxes(title_text=column_label, range=[lower - padding, upper + padding])
    figure.update_yaxes(title_text="概率密度")
    return figure

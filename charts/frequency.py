"""Plotly rendering for a single-variable FFT amplitude spectrum."""

from __future__ import annotations

import numpy as np
import plotly.graph_objects as go


NO_SELECTION_MESSAGE = "请至少选择一个变量"
SINGLE_VARIABLE_MESSAGE = "Frequency Analysis 仅支持单变量，请只选择一个变量"


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
        title="Frequency Analysis",
        height=600,
        margin={"l": 70, "r": 30, "t": 55, "b": 70},
        xaxis={"visible": False},
        yaxis={"visible": False},
    )
    return figure


def create_frequency_figure(
    selected_column,
    frequency_result: dict[str, object] | None,
) -> go.Figure:
    """Create a positive-frequency FFT amplitude spectrum and peak marker."""

    if isinstance(selected_column, (list, tuple)):
        if not selected_column:
            return _message_figure(NO_SELECTION_MESSAGE)
        if len(selected_column) != 1:
            return _message_figure(SINGLE_VARIABLE_MESSAGE)
        selected_column = selected_column[0]
    if not selected_column or not isinstance(frequency_result, dict):
        return _message_figure(NO_SELECTION_MESSAGE if not selected_column else "尚未生成频谱")

    try:
        frequencies = np.asarray(frequency_result["frequency_cph"], dtype=float)
        amplitudes = np.asarray(frequency_result["amplitude"], dtype=float)
        if frequencies.ndim != 1 or amplitudes.ndim != 1:
            raise ValueError
        if frequencies.size != amplitudes.size:
            raise ValueError
        valid = np.isfinite(frequencies) & np.isfinite(amplitudes) & (frequencies > 0)
        frequencies = frequencies[valid]
        amplitudes = amplitudes[valid]
        if not frequencies.size:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        return _message_figure("无法生成有效频谱")

    peak_index = int(np.argmax(amplitudes))
    dominant_frequency = float(frequency_result.get("dominant_frequency_cph", frequencies[peak_index]))
    dominant_amplitude = float(frequency_result.get("dominant_amplitude", amplitudes[peak_index]))
    if not np.isfinite(dominant_frequency) or dominant_frequency <= 0:
        dominant_frequency = float(frequencies[peak_index])
    if not np.isfinite(dominant_amplitude):
        dominant_amplitude = float(amplitudes[peak_index])
    marker_index = int(np.argmin(np.abs(frequencies - dominant_frequency)))
    dominant_frequency = float(frequencies[marker_index])
    dominant_amplitude = float(amplitudes[marker_index])
    periods = 1.0 / frequencies

    figure = go.Figure()
    figure.add_trace(
        go.Scattergl(
            name="FFT Spectrum",
            x=frequencies,
            y=amplitudes,
            mode="lines",
            line={"color": "#1769b0", "width": 1.2},
            customdata=periods,
            hovertemplate=(
                "Frequency: %{x:.6g} cycles/hour<br>"
                "Period: %{customdata:.6g} h<br>"
                "Amplitude: %{y:.6g}<extra></extra>"
            ),
        )
    )
    figure.add_trace(
        go.Scattergl(
            name="Dominant Peak",
            x=[dominant_frequency],
            y=[dominant_amplitude],
            mode="markers",
            marker={"color": "#b42318", "size": 10},
            hovertemplate=(
                "Frequency: %{x:.6g} cycles/hour<br>"
                f"Period: {1.0 / dominant_frequency:.6g} h<br>"
                "Amplitude: %{y:.6g}<extra></extra>"
            ),
        )
    )
    figure.add_annotation(
        text=(
            f"Dominant: {dominant_frequency:.2f} cycles/hour"
            f"<br>Period: {1.0 / dominant_frequency:.2f} h"
        ),
        x=dominant_frequency,
        y=dominant_amplitude,
        xref="x",
        yref="y",
        showarrow=True,
        arrowhead=2,
        ax=40,
        ay=-40,
    )
    figure.update_layout(
        template="plotly_white",
        title=f"Frequency Analysis - {selected_column}",
        height=600,
        margin={"l": 75, "r": 30, "t": 75, "b": 70},
        hovermode="closest",
        showlegend=True,
    )
    figure.update_xaxes(title_text="Frequency (cycles/hour)", rangemode="tozero")
    figure.update_yaxes(title_text="Amplitude", rangemode="tozero")
    return figure

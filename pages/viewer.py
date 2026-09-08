"""Dash page for querying and displaying PI historical data."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from dash import Input, Output, State, callback_context, dcc, html
from dash.exceptions import PreventUpdate
import plotly.graph_objects as go

from backend.capability import calculate_normal_capability
from backend.dataframe_store import get_dataframe, store_dataframe
from backend.frequency import calculate_fft_spectrum
from backend.pi_reader import INTERVAL_OPTIONS, MAX_TAGS, normalize_tags, read_pi_data
from backend.statistics import calculate_series_summary
from charts.scatter import (
    DEFAULT_MAX_SCATTER_POINTS,
    MAX_SCATTER_VARIABLES,
    calculate_scatter_dimensions,
    create_scatter_figure,
)
from charts.boxplot import create_boxplot_figure
from charts.capability import (
    NO_SELECTION_MESSAGE as CAPABILITY_NO_SELECTION_MESSAGE,
    SINGLE_VARIABLE_MESSAGE as CAPABILITY_SINGLE_VARIABLE_MESSAGE,
    create_capability_figure,
)
from charts.control_chart import (
    DEFAULT_MAX_CONTROL_POINTS,
    SINGLE_VARIABLE_MESSAGE,
    create_control_chart,
)
from charts.frequency import (
    SINGLE_VARIABLE_MESSAGE as FREQUENCY_SINGLE_VARIABLE_MESSAGE,
    create_frequency_figure,
)
from charts.probability import (
    SINGLE_VARIABLE_MESSAGE as PROBABILITY_SINGLE_VARIABLE_MESSAGE,
    create_probability_plot_figure,
)
from charts.trend import create_distribution_figure, create_trend_figure


_PI_SOURCE = "pi"
_FILE_SOURCE = "file"
_MAX_SELECTED_COLUMNS = MAX_TAGS
_DEFAULT_MAX_PLOT_POINTS = 45_000
_MIN_PLOT_POINTS = 100
_MAX_PLOT_POINTS = 135_000
_view_revision = 0
_STAT_COLORS = (
    "#176b87",
    "#c2410c",
    "#6d28d9",
    "#15803d",
    "#b91c1c",
    "#ca8a04",
    "#a21caf",
    "#475569",
)
_STATISTICS_GRID_STYLE = {
    "display": "grid",
    "gridTemplateColumns": "repeat(4, minmax(0, 1fr))",
    "gap": "10px",
    "alignItems": "start",
}
_STATISTICS_CARD_STYLE = {
    "minWidth": 0,
    "overflow": "hidden",
}
_PI_QUERY_STYLE = {
    "display": "flex",
    "flexDirection": "column",
    "gap": "0.5rem",
}
_FILE_UPLOAD_STYLE = {
    "display": "none",
}
_TREND_CONTROL_STYLE = {"width": "100%", "height": "32px"}
_CONTROL_CHART_TEST_OPTIONS = [
    {"label": "检验 1：单点超过 3σ 控制限（Minitab 默认）", "value": 1},
    {"label": "检验 2：连续 9 点位于中心线同一侧", "value": 2},
    {"label": "检验 3：连续 6 点持续上升或下降", "value": 3},
    {"label": "检验 4：连续 14 点交替升降", "value": 4},
    {"label": "检验 5：3 点中有 2 点超过同侧 2σ", "value": 5},
    {"label": "检验 6：5 点中有 4 点超过同侧 1σ", "value": 6},
    {"label": "检验 7：连续 15 点位于中心线 1σ 内", "value": 7},
    {"label": "检验 8：连续 8 点位于中心线 1σ 外", "value": 8},
]
_UPLOAD_CLIENTSIDE_FUNCTION = """
async function(n_clicks) {
    if (!n_clicks) {
        return [window.dash_clientside.no_update, window.dash_clientside.no_update];
    }
    const input = document.getElementById("file-upload");
    if (!input || !input.files || !input.files.length) {
        return [window.dash_clientside.no_update, "请先选择文件"];
    }

    const form = new FormData();
    form.append("file", input.files[0]);
    const status = document.getElementById("upload-status");
    if (status) status.textContent = "正在上传…";

    try {
        const response = await fetch("/api/upload", {
            method: "POST",
            body: form,
        });
        const result = await response.json();
        if (!response.ok) {
            const message = result.error || "上传失败";
            return [{ok: false, error: message}, `上传失败：${message}`];
        }
        return [result, `上传成功：${result.filename}（${result.rows} 行）`];
    } catch (error) {
        const message = error.message || "上传失败";
        return [{ok: false, error: message}, `上传失败：${message}`];
    } finally {
        input.value = "";
    }
}
"""


def parse_tags(value: str) -> list[str]:
    if not isinstance(value, str):
        raise ValueError("请输入至少一个位号")
    return normalize_tags(value.replace(",", "\n").splitlines())


def _empty_figure():
    return create_trend_figure(pd.DataFrame(index=pd.DatetimeIndex([], name="Timestamp")))


def _empty_scatter_figure():
    figure = go.Figure()
    figure.update_layout(template="plotly_white")
    return figure


def _empty_boxplot_figure():
    return create_boxplot_figure(pd.DataFrame(), [])


def _empty_control_chart_figure():
    return create_control_chart(
        pd.DataFrame(index=pd.DatetimeIndex([], name="Timestamp")), []
    )


def _empty_frequency_figure():
    return create_frequency_figure(None, None)


def _empty_probability_plot_figure():
    return create_probability_plot_figure(pd.DataFrame(), [])


def _empty_capability_figure():
    return create_capability_figure(pd.DataFrame(), [], None)


def _empty_capability_summary():
    return html.Div()


def _format_capability_value(value) -> str:
    if value is None:
        return "—"
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return "—"
    return f"{value:.6g}" if math.isfinite(value) else "—"


def _capability_summary(result) -> html.Div:
    if not isinstance(result, dict):
        return _empty_capability_summary()

    sections = (
        (
            "过程数据",
            (
                ("样本数", str(result.get("sample_size", "—"))),
                ("均值", _format_capability_value(result.get("mean"))),
                ("组内标准差", _format_capability_value(result.get("within_sigma"))),
                ("整体标准差", _format_capability_value(result.get("overall_sigma"))),
                ("规格下限（LSL）", _format_capability_value(result.get("lsl"))),
                ("规格上限（USL）", _format_capability_value(result.get("usl"))),
            ),
        ),
        (
            "潜在过程能力",
            (
                ("潜在能力（Cp）", _format_capability_value(result.get("cp"))),
                ("修正能力（Cpk）", _format_capability_value(result.get("cpk"))),
                ("下侧能力（CPL）", _format_capability_value(result.get("cpl"))),
                ("上侧能力（CPU）", _format_capability_value(result.get("cpu"))),
            ),
        ),
        (
            "整体过程能力",
            (
                ("整体性能（Pp）", _format_capability_value(result.get("pp"))),
                ("修正性能（Ppk）", _format_capability_value(result.get("ppk"))),
                ("下侧性能（PPL）", _format_capability_value(result.get("ppl"))),
                ("上侧性能（PPU）", _format_capability_value(result.get("ppu"))),
            ),
        ),
    )
    return html.Div(
        [
            html.Div(
                [
                    html.H4(title, className="capability-summary-title"),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Span(label, className="capability-summary-label"),
                                    html.Strong(value, className="capability-summary-value"),
                                ],
                                className="capability-summary-item",
                            )
                            for label, value in items
                        ],
                        className="capability-summary-items",
                    ),
                ],
                className="capability-summary-section",
            )
            for title, items in sections
        ],
        className="capability-summary-content",
    )


def _format_frequency_value(value, suffix="") -> str:
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return "—"
    return f"{value:.6g}{suffix}" if math.isfinite(value) else "—"


def _format_sampling_interval(seconds) -> str:
    try:
        seconds = float(seconds)
    except (TypeError, ValueError, OverflowError):
        return "—"
    if not math.isfinite(seconds):
        return "—"
    if math.isclose(seconds / 3600, round(seconds / 3600), rel_tol=0, abs_tol=1e-9):
        return f"{seconds / 3600:g} 小时"
    if math.isclose(seconds / 60, round(seconds / 60), rel_tol=0, abs_tol=1e-9):
        return f"{seconds / 60:g} 分钟"
    return f"{seconds:.6g} 秒"


def _empty_frequency_summary():
    return html.Div()


def _frequency_summary(result) -> html.Div:
    if not isinstance(result, dict):
        return _empty_frequency_summary()
    rows = (
        ("样本数", str(result.get("sample_size", "—"))),
        (
            "采样间隔",
            _format_sampling_interval(result.get("sampling_interval_seconds")),
        ),
        ("时长", _format_frequency_value(result.get("duration_hours"), " 小时")),
        (
            "奈奎斯特频率",
            _format_frequency_value(result.get("nyquist_cph"), " 次/小时"),
        ),
        (
            "频率分辨率",
            _format_frequency_value(
                result.get("frequency_resolution_cph"), " 次/小时"
            ),
        ),
        (
            "主频",
            _format_frequency_value(
                result.get("dominant_frequency_cph"), " 次/小时"
            ),
        ),
        (
            "主周期",
            _format_frequency_value(result.get("dominant_period_hours"), " 小时"),
        ),
        ("主振幅", _format_frequency_value(result.get("dominant_amplitude"))),
    )
    return html.Div(
        [
            html.Div(
                [
                    html.Span(label, className="frequency-summary-label"),
                    html.Strong(value, className="frequency-summary-value"),
                ],
                className="frequency-summary-item",
            )
            for label, value in rows
        ],
        className="frequency-summary-content",
    )


def _selected_columns(frame: pd.DataFrame, selected_columns=None) -> list:
    columns = list(frame.columns)
    if selected_columns is None:
        return columns[:_MAX_SELECTED_COLUMNS]
    if not isinstance(selected_columns, (list, tuple)):
        return []
    return [column for column in columns if column in selected_columns][:_MAX_SELECTED_COLUMNS]


def _variable_selection_state(frame: pd.DataFrame, selected_columns=None):
    columns = list(frame.columns)
    options = [{"label": str(column), "value": column} for column in columns]
    selected = _selected_columns(frame, selected_columns)
    if selected_columns is None:
        message = (
            f"变量超过{_MAX_SELECTED_COLUMNS}个，默认选择前{_MAX_SELECTED_COLUMNS}个变量，"
            f"最多选择{_MAX_SELECTED_COLUMNS}个变量"
            if len(columns) > _MAX_SELECTED_COLUMNS
            else ""
        )
    elif isinstance(selected_columns, (list, tuple)) and len(selected_columns) > _MAX_SELECTED_COLUMNS:
        message = f"最多选择{_MAX_SELECTED_COLUMNS}个变量，已保留前{_MAX_SELECTED_COLUMNS}个变量"
    else:
        message = ""
    return options, selected, message


def _parse_trend_time(value, label: str):
    if value in (None, ""):
        return None
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{label}格式无效") from exc
    if pd.isna(timestamp):
        raise ValueError(f"{label}格式无效")
    return timestamp


def _resolve_max_plot_points(value, _series_count: int = 1) -> int:
    if value in (None, ""):
        requested = _DEFAULT_MAX_PLOT_POINTS
    else:
        try:
            requested = int(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("最大绘图点数必须是整数") from exc
    return min(_MAX_PLOT_POINTS, max(_MIN_PLOT_POINTS, requested))


def _sample_trend_positions(frame: pd.DataFrame, selected_columns, max_points: int) -> list[int]:
    if len(frame) <= max_points:
        return list(range(len(frame)))

    max_points = max(2, int(max_points))
    columns = list(selected_columns)
    bucket_count = max(1, (max_points - 2) // (2 * max(1, len(columns))))
    positions = {0, len(frame) - 1}
    numeric = frame.loc[:, columns].apply(pd.to_numeric, errors="coerce")
    boundaries = np.linspace(0, len(frame), bucket_count + 1, dtype=int)

    for start, end in zip(boundaries[:-1], boundaries[1:]):
        if start >= end:
            continue
        bucket = numeric.iloc[start:end]
        for column in columns:
            values = bucket[column].to_numpy(dtype=float)
            finite = np.isfinite(values)
            if not finite.any():
                continue
            valid_positions = np.flatnonzero(finite)
            finite_values = values[finite]
            positions.add(start + int(valid_positions[np.argmin(finite_values)]))
            positions.add(start + int(valid_positions[np.argmax(finite_values)]))

    if len(positions) < max_points:
        for position in np.linspace(0, len(frame) - 1, max_points, dtype=int):
            positions.add(int(position))
            if len(positions) >= max_points:
                break
    return sorted(positions)[:max_points]


def _prepare_trend_frame(
    frame: pd.DataFrame,
    selected_columns,
    start_time=None,
    end_time=None,
    max_points=_DEFAULT_MAX_PLOT_POINTS,
):
    selected = _selected_columns(frame, selected_columns)
    if not selected:
        raise ValueError("请至少选择一个变量")

    start = _parse_trend_time(start_time, "显示开始时间")
    end = _parse_trend_time(end_time, "显示结束时间")
    if start is not None and end is not None and end < start:
        raise ValueError("显示结束时间不能早于显示开始时间")

    filtered = frame.loc[:, selected]
    try:
        if start is not None:
            filtered = filtered.loc[filtered.index >= start]
        if end is not None:
            filtered = filtered.loc[filtered.index <= end]
    except TypeError as exc:
        raise ValueError("显示时间与数据时间格式不兼容") from exc
    if filtered.empty:
        raise ValueError("图表时间范围内无数据")

    effective_max_points = _resolve_max_plot_points(max_points, len(selected))
    display = filtered
    if len(display) > effective_max_points:
        positions = _sample_trend_positions(display, selected, effective_max_points)
        display = display.iloc[positions]
    return selected, filtered, display, effective_max_points


def _render_trend_frame(
    frame: pd.DataFrame,
    selected_columns,
    axis_mode="shared",
    start_time=None,
    end_time=None,
    max_points=_DEFAULT_MAX_PLOT_POINTS,
):
    selected, full_frame, display_frame, effective_max_points = _prepare_trend_frame(
        frame,
        selected_columns,
        start_time,
        end_time,
        max_points,
    )
    requested_max_points = (
        _DEFAULT_MAX_PLOT_POINTS if max_points in (None, "") else int(max_points)
    )
    max_points_status = (
        f"配置最大点数 {requested_max_points}，实际每个位号上限 {effective_max_points}"
        if requested_max_points != effective_max_points
        else f"每个位号最大点数 {effective_max_points}"
    )
    return (
        create_trend_figure(display_frame, selected, axis_mode),
        _statistics_cards(full_frame, selected),
        f"趋势图已生成，原始 {len(full_frame)} 点，显示 {len(display_frame)} 点，"
        f"{max_points_status}。",
    )


def _format_stat_value(value) -> str:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "-"
    if not math.isfinite(value):
        return "-"
    absolute = abs(value)
    if absolute > 0 and (absolute < 0.001 or absolute >= 1_000_000):
        return f"{value:.2e}"
    decimals = 0 if absolute >= 10_000 else 1 if absolute >= 100 else 2 if absolute >= 1 else 4
    return f"{value:,.{decimals}f}".rstrip("0").rstrip(".")


def _statistics_card(column, series: pd.Series, index: int):
    summary = calculate_series_summary(series)
    rows = (
        ("均值", _format_stat_value(summary["mean"])),
        ("标准差", _format_stat_value(summary["std"])),
        ("最大值", _format_stat_value(summary["max"])),
        ("最小值", _format_stat_value(summary["min"])),
        ("极差", _format_stat_value(summary["range"])),
        ("中位数", _format_stat_value(summary["median"])),
        (
            "有效点数/占比",
            f"{summary['count']} / {summary['ratio'] * 100:.1f}%",
        ),
    )
    return html.Div(
        [
            html.H3(
                str(column),
                style={
                    "margin": "0 0 8px",
                    "fontSize": "15px",
                    "overflowWrap": "anywhere",
                },
            ),
            html.Dl(
                [
                    html.Div(
                        [
                            html.Dt(
                                label,
                                style={
                                    "color": "#6b7280",
                                    "whiteSpace": "nowrap",
                                },
                            ),
                            html.Dd(
                                value,
                                style={
                                    "margin": 0,
                                    "textAlign": "right",
                                    "fontVariantNumeric": "tabular-nums",
                                },
                            ),
                        ],
                        style={
                            "display": "grid",
                            "gridTemplateColumns": "90px 1fr",
                            "gap": "8px",
                            "fontSize": "13px",
                        },
                    )
                    for label, value in rows
                ],
                style={"display": "grid", "gap": "4px", "margin": 0},
            ),
            html.Div(
                "数值分布",
                style={
                    "marginTop": "10px",
                    "marginBottom": "4px",
                    "color": "#6b7280",
                    "fontSize": "13px",
                },
            ),
            dcc.Graph(
                figure=create_distribution_figure(
                    summary["values"], _STAT_COLORS[index % len(_STAT_COLORS)]
                ),
                config={"displayModeBar": False, "displaylogo": False},
                style={"height": "115px", "width": "100%"},
            ),
            html.Div(
                [
                    html.Span(_format_stat_value(summary["min"])),
                    html.Span(_format_stat_value(summary["max"])),
                ],
                style={
                    "display": "flex",
                    "justifyContent": "space-between",
                    "gap": "8px",
                    "color": "#6b7280",
                    "fontSize": "13px",
                    "fontVariantNumeric": "tabular-nums",
                },
            ),
        ],
        className="statistics-card",
        style=_STATISTICS_CARD_STYLE,
    )


def _statistics_cards(frame: pd.DataFrame, selected_columns: list) -> list:
    return [
        _statistics_card(column, frame[column], index)
        for index, column in enumerate(selected_columns)
    ]


def _next_revision() -> int:
    global _view_revision
    _view_revision += 1
    return _view_revision


def _load_viewer(
    n_clicks,
    tag_value,
    start_time,
    end_time,
    source=_PI_SOURCE,
    upload_result=None,
    selected_columns=None,
    interval="1m",
):
    if source == _FILE_SOURCE:
        if not isinstance(upload_result, dict):
            return "请选择文件", [], [], False
        if not upload_result.get("ok"):
            message = upload_result.get("error") or "上传失败"
            return f"文件读取失败：{message}", [], [], False
        frame = get_dataframe()
        if frame is None:
            return "文件上传成功但没有可用数据", [], [], False
    else:
        if not n_clicks:
            return "", [], [], False

        try:
            tags = parse_tags(tag_value)
        except ValueError as exc:
            return str(exc), [], [], False

        try:
            frame = read_pi_data(tags, start_time, end_time, interval)
        except Exception as exc:
            message = str(exc) or exc.__class__.__name__
            return f"数据读取失败：{message}", [], [], False

        store_dataframe(frame)
    current = get_dataframe()
    if current is None or current.empty:
        return "查询时间范围内无数据", [], [], False

    options, selected, status = _variable_selection_state(current, selected_columns)
    if not selected:
        return "请至少选择一个变量", options, selected, True
    return status, options, selected, True


def _viewer_state(options, status, ready):
    return {
        "options": options,
        "status": status,
        "ready": ready,
        "revision": _next_revision(),
    }


def update_variable_options(viewer_state, selected_columns):
    if not isinstance(viewer_state, dict):
        return []
    raw_options = viewer_state.get("options", [])
    if not isinstance(raw_options, list):
        return []
    options = [dict(option) for option in raw_options if isinstance(option, dict)]
    selected_columns = selected_columns if isinstance(selected_columns, list) else []
    if len(selected_columns) >= _MAX_SELECTED_COLUMNS:
        for option in options:
            option["disabled"] = option.get("value") not in selected_columns
    return options


def _triggered_id():
    if not callback_context.triggered:
        return None
    return callback_context.triggered[0]["prop_id"].split(".", 1)[0]


def update_trend_time_controls(viewer_state):
    if not isinstance(viewer_state, dict) or not viewer_state.get("ready"):
        return None, None
    current = get_dataframe()
    if current is None or not isinstance(current.index, pd.DatetimeIndex):
        return None, None
    valid_index = current.index.dropna()
    if not len(valid_index):
        return None, None
    return (
        valid_index.min().strftime("%Y-%m-%dT%H:%M:%S"),
        valid_index.max().strftime("%Y-%m-%dT%H:%M:%S"),
    )


def update_show_trend_state(viewer_state, selected_columns):
    return not (
        isinstance(viewer_state, dict)
        and viewer_state.get("ready")
        and isinstance(selected_columns, (list, tuple))
        and bool(selected_columns)
    )


def update_data_state(
    n_clicks,
    upload_result,
    clear_clicks,
    source,
    tag_value,
    start_time,
    end_time,
    interval="1m",
):
    triggered_id = _triggered_id()
    if triggered_id == "clear-data-button":
        current = get_dataframe()
        if current is None or current.empty:
            return _viewer_state([], "尚未加载数据", False), []
        options, _, _ = _variable_selection_state(current, [])
        return _viewer_state(options, "请至少选择一个变量", True), []

    if triggered_id == "query-button" and source != _PI_SOURCE:
        return _viewer_state([], "请切换到 PI 服务器模式", False), []
    if triggered_id == "upload-result" and source != _FILE_SOURCE:
        return _viewer_state([], "请切换到本地文件模式", False), []
    if triggered_id not in {"query-button", "upload-result"}:
        return _viewer_state([], "尚未加载数据", False), []

    status, options, selected, ready = _load_viewer(
        n_clicks,
        tag_value,
        start_time,
        end_time,
        source,
        upload_result,
        selected_columns=[],
        interval=interval,
    )
    return _viewer_state(options, status, ready), selected


def render_trend_view(
    viewer_state,
    show_clicks=0,
    selected_columns=None,
    axis_mode="shared",
    start_time=None,
    end_time=None,
    max_points=_DEFAULT_MAX_PLOT_POINTS,
):
    state = viewer_state if isinstance(viewer_state, dict) else {}
    if _triggered_id() == "viewer-state" or not show_clicks:
        return _empty_figure(), [], state.get("status", "")
    if not state.get("ready"):
        return _empty_figure(), [], state.get("status", "")
    current = get_dataframe()
    if current is None:
        return _empty_figure(), [], "尚未加载数据"
    try:
        figure, cards, status = _render_trend_frame(
            current,
            selected_columns,
            axis_mode,
            start_time,
            end_time,
            max_points,
        )
    except (TypeError, ValueError) as exc:
        return _empty_figure(), [], str(exc)
    return figure, cards, status


def _scatter_columns(*values) -> list:
    if len(values) == 1 and isinstance(values[0], (list, tuple)):
        values = tuple(values[0])
    return [value for value in values if value not in (None, "")]


def _render_scatter_frame(
    frame: pd.DataFrame,
    x_columns,
    y_columns,
    max_points=DEFAULT_MAX_SCATTER_POINTS,
):
    return (
        create_scatter_figure(frame, x_columns, y_columns, max_points),
        "",
    )


def render_scatter_view(
    viewer_state,
    show_clicks=0,
    x_1=None,
    x_2=None,
    x_3=None,
    y_1=None,
    y_2=None,
    y_3=None,
    max_points=DEFAULT_MAX_SCATTER_POINTS,
):
    state = viewer_state if isinstance(viewer_state, dict) else {}
    if _triggered_id() == "viewer-state" or not show_clicks:
        return _empty_scatter_figure(), ""
    if not state.get("ready"):
        return _empty_scatter_figure(), state.get("status", "尚未加载数据")

    current = get_dataframe()
    if current is None:
        return _empty_scatter_figure(), "尚未加载数据"
    try:
        return _render_scatter_frame(
            current,
            _scatter_columns(x_1, x_2, x_3),
            _scatter_columns(y_1, y_2, y_3),
            max_points,
        )
    except (TypeError, ValueError) as exc:
        return _empty_scatter_figure(), str(exc)


def _boxplot_frame_style(figure) -> dict:
    """每个箱体固定为子图列宽的 1/8 = 1/8 页面宽度；空位号始终 100% 容纳提示。"""

    return {"width": "100%"}


def render_boxplot_view(
    viewer_state,
    selected_columns=None,
    axis_mode="independent",
    tab_value="boxplot-tab",
):
    if tab_value != "boxplot-tab":
        raise PreventUpdate
    state = viewer_state if isinstance(viewer_state, dict) else {}
    if not state.get("ready"):
        figure = _empty_boxplot_figure()
        return figure, "未选择变量", state.get("status") or "尚未加载数据", _boxplot_frame_style(figure)

    current = get_dataframe()
    if current is None:
        figure = _empty_boxplot_figure()
        return figure, "未选择变量", "尚未加载数据", _boxplot_frame_style(figure)

    selected = _selected_columns(current, selected_columns)
    if not selected:
        figure = create_boxplot_figure(current, [])
        return figure, "未选择变量", "请至少选择一个变量", _boxplot_frame_style(figure)

    try:
        figure = create_boxplot_figure(current, selected, axis_mode)
    except (TypeError, ValueError) as exc:
        return (
            _empty_boxplot_figure(),
            ", ".join(map(str, selected)),
            str(exc),
            {"width": "100%"},
        )
    frame_style = _boxplot_frame_style(figure)
    if current.empty:
        return figure, ", ".join(map(str, selected)), "暂无可用数据", frame_style
    status = "" if figure.data else "所选变量无有效数值数据"
    return figure, ", ".join(map(str, selected)), status, frame_style


def render_control_chart_view(
    viewer_state,
    selected_columns=None,
    tests=None,
    tab_value="control-chart-tab",
):
    if tab_value != "control-chart-tab":
        raise PreventUpdate
    state = viewer_state if isinstance(viewer_state, dict) else {}
    if not state.get("ready"):
        return (
            _empty_control_chart_figure(),
            "未选择变量",
            state.get("status") or "尚未加载数据",
        )

    current = get_dataframe()
    if current is None:
        return _empty_control_chart_figure(), "未选择变量", "尚未加载数据"

    selected = _selected_columns(current, selected_columns)
    selected_text = ", ".join(map(str, selected)) or "未选择变量"
    if len(selected) != 1:
        return (
            create_control_chart(current, selected, tests=tests),
            selected_text,
            SINGLE_VARIABLE_MESSAGE,
        )

    try:
        figure = create_control_chart(
            current,
            selected,
            max_points=DEFAULT_MAX_CONTROL_POINTS,
            tests=tests,
        )
    except (TypeError, ValueError) as exc:
        return _empty_control_chart_figure(), selected_text, str(exc)
    if current.empty:
        return figure, selected_text, "暂无可用数据"
    return figure, selected_text, "" if figure.data else "所选变量无有效数值数据"


def render_frequency_view(
    viewer_state,
    selected_columns=None,
    tab_value="frequency-analysis-tab",
):
    if tab_value != "frequency-analysis-tab":
        raise PreventUpdate
    state = viewer_state if isinstance(viewer_state, dict) else {}
    if not state.get("ready"):
        return (
            _empty_frequency_figure(),
            _empty_frequency_summary(),
            "未选择变量",
            state.get("status") or "尚未加载数据",
        )

    current = get_dataframe()
    if current is None:
        return _empty_frequency_figure(), _empty_frequency_summary(), "未选择变量", "尚未加载数据"

    selected = [] if selected_columns is None else _selected_columns(current, selected_columns)
    selected_text = ", ".join(map(str, selected)) or "未选择变量"
    if not selected:
        return (
            _empty_frequency_figure(),
            _empty_frequency_summary(),
            selected_text,
            "请至少选择一个变量",
        )
    if len(selected) != 1:
        return (
            create_frequency_figure(selected, None),
            _empty_frequency_summary(),
            selected_text,
            FREQUENCY_SINGLE_VARIABLE_MESSAGE,
        )

    try:
        result = calculate_fft_spectrum(current[selected[0]])
        figure = create_frequency_figure(selected[0], result)
    except (TypeError, ValueError) as exc:
        return _empty_frequency_figure(), _empty_frequency_summary(), selected_text, str(exc)
    return figure, _frequency_summary(result), selected_text, ""


def render_probability_plot_view(
    viewer_state,
    selected_columns=None,
    tab_value="probability-plot-tab",
):
    if tab_value != "probability-plot-tab":
        raise PreventUpdate
    state = viewer_state if isinstance(viewer_state, dict) else {}
    if not state.get("ready"):
        return (
            _empty_probability_plot_figure(),
            "未选择变量",
            state.get("status") or "尚未加载数据",
        )

    current = get_dataframe()
    if current is None:
        return _empty_probability_plot_figure(), "未选择变量", "尚未加载数据"

    selected = [] if selected_columns is None else _selected_columns(current, selected_columns)
    selected_text = ", ".join(map(str, selected)) or "未选择变量"
    if len(selected) > 1:
        return (
            create_probability_plot_figure(current, selected),
            selected_text,
            PROBABILITY_SINGLE_VARIABLE_MESSAGE,
        )
    if not selected:
        return (
            create_probability_plot_figure(current, []),
            selected_text,
            "请至少选择一个变量",
        )

    try:
        figure = create_probability_plot_figure(current, selected)
    except (TypeError, ValueError) as exc:
        return _empty_probability_plot_figure(), selected_text, str(exc)
    if current.empty:
        return figure, selected_text, "暂无可用数据"
    return figure, selected_text, "" if figure.data else "所选变量无法生成概率图"


def render_capability_view(
    viewer_state,
    selected_columns=None,
    lsl=None,
    usl=None,
    tab_value="capability-tab",
):
    if tab_value != "capability-tab":
        raise PreventUpdate
    state = viewer_state if isinstance(viewer_state, dict) else {}
    if not state.get("ready"):
        return (
            _empty_capability_figure(),
            _empty_capability_summary(),
            "未选择变量",
            state.get("status") or "尚未加载数据",
        )

    current = get_dataframe()
    if current is None:
        return (
            _empty_capability_figure(),
            _empty_capability_summary(),
            "未选择变量",
            "尚未加载数据",
        )

    selected = [] if selected_columns is None else _selected_columns(current, selected_columns)
    selected_text = ", ".join(map(str, selected)) or "未选择变量"
    if not selected:
        return (
            create_capability_figure(current, [], None),
            _empty_capability_summary(),
            selected_text,
            CAPABILITY_NO_SELECTION_MESSAGE,
        )
    if len(selected) != 1:
        return (
            create_capability_figure(current, selected, None),
            _empty_capability_summary(),
            selected_text,
            CAPABILITY_SINGLE_VARIABLE_MESSAGE,
        )

    try:
        result = calculate_normal_capability(current[selected[0]], lsl=lsl, usl=usl)
        figure = create_capability_figure(current, selected, result)
    except (TypeError, ValueError) as exc:
        return (
            create_capability_figure(current, selected, None),
            _empty_capability_summary(),
            selected_text,
            str(exc),
        )
    return figure, _capability_summary(result), selected_text, ""


def update_scatter_variable_options(viewer_state):
    if not isinstance(viewer_state, dict):
        options = []
    else:
        raw_options = viewer_state.get("options", [])
        options = [dict(option) for option in raw_options if isinstance(option, dict)]
    return options, options, options, options, options, options


def update_show_scatter_state(viewer_state):
    return not (
        isinstance(viewer_state, dict) and viewer_state.get("ready")
    )


def update_scatter_graph_style(
    tab_value,
    x_1=None,
    x_2=None,
    x_3=None,
    y_1=None,
    y_2=None,
    y_3=None,
):
    rows = len(_scatter_columns(y_1, y_2, y_3))
    cols = len(_scatter_columns(x_1, x_2, x_3))
    if (rows, cols) == (3, 3):
        return {
            "width": "100%",
            "maxWidth": "100%",
            "height": "auto",
            "aspectRatio": "1 / 1",
        }
    width, height = calculate_scatter_dimensions(rows, cols)
    return {
        "width": f"{width}px",
        "maxWidth": "100%",
        "height": f"{height}px",
    }


def update_source_controls(source):
    if source == _FILE_SOURCE:
        return {**_PI_QUERY_STYLE, "display": "none"}, {
            **_FILE_UPLOAD_STYLE,
            "display": "block",
        }
    return _PI_QUERY_STYLE, _FILE_UPLOAD_STYLE


def update_load_status(viewer_state):
    state = viewer_state if isinstance(viewer_state, dict) else {}
    if state.get("ready"):
        return state.get("status") or "数据已加载"
    return state.get("status") or "尚未加载数据"


def _has_figure_data(figure) -> bool:
    data = figure.get("data") if isinstance(figure, dict) else getattr(figure, "data", ())
    return bool(data)


def update_trend_empty_state(figure):
    return {"display": "none"} if _has_figure_data(figure) else {"display": "flex"}


def update_scatter_empty_state(figure):
    return {"display": "none"} if _has_figure_data(figure) else {"display": "flex"}


layout = html.Div(
    [
        dcc.Store(id="viewer-state"),
        html.Header(
            [
                html.Div("历史数据查看器", className="eyebrow"),
                html.H1("PI 数据查看器"),
                html.P(
                    "读取 PI 历史数据或本地文件，先查看摘要，再生成趋势与散点图。",
                    className="page-description",
                ),
            ],
            className="page-header",
        ),
        html.Div(
            [
                html.Aside(
                    [
                        html.H2("位号浏览器", className="panel-title"),
                        html.Label("数据来源", className="field-label-text"),
                        dcc.RadioItems(
                            id="data-source",
                            options=[
                                {"label": "PI 服务器", "value": _PI_SOURCE},
                                {"label": "本地文件", "value": _FILE_SOURCE},
                            ],
                            value=_PI_SOURCE,
                            inline=True,
                            className="source-switch",
                        ),
                        html.Details(
                            [
                                html.Summary("基础参数", className="details-summary"),
                                html.Label(
                                    [
                                        html.Span(
                                            f"PI 位号（每行一个，最多{MAX_TAGS}个）",
                                            className="field-label-copy",
                                        ),
                                        dcc.Textarea(
                                            id="tag-input",
                                            placeholder="TAG001.PV\nTAG002.PV",
                                            className="text-input tag-input",
                                            style={"width": "100%", "height": "120px"},
                                        ),
                                    ],
                                    className="field-label",
                                ),
                                html.Label(
                                    [
                                        html.Span("开始时间", className="field-label-copy"),
                                        dcc.Input(
                                            id="start-time",
                                            type="text",
                                            placeholder="支持:\n2026-09-01 00:00:00\n*\n*-1h",
                                            className="text-input",
                                            style={"width": "100%"},
                                        ),
                                    ],
                                    className="field-label",
                                ),
                                html.Label(
                                    [
                                        html.Span("结束时间", className="field-label-copy"),
                                        dcc.Input(
                                            id="end-time",
                                            type="text",
                                            placeholder="支持:\n2026-09-01 00:00:00\n*\n*-1h",
                                            className="text-input",
                                            style={"width": "100%"},
                                        ),
                                    ],
                                    className="field-label",
                                ),
                                html.Label(
                                    "采样间隔",
                                    htmlFor="interval",
                                    className="field-label-copy",
                                ),
                                dcc.Dropdown(
                                    id="interval",
                                    options=[
                                        {
                                            "label": f"{value[:-1]} {'分钟' if value.endswith('m') else '小时'}",
                                            "value": value,
                                        }
                                        for value in INTERVAL_OPTIONS
                                    ],
                                    value=INTERVAL_OPTIONS[0],
                                    clearable=False,
                                    className="select-control",
                                ),
                                html.Button(
                                    "查询",
                                    id="query-button",
                                    n_clicks=0,
                                    type="button",
                                    className="primary-button",
                                ),
                            ],
                            id="pi-query-controls",
                            open=True,
                            className="parameter-section",
                            style=_PI_QUERY_STYLE,
                        ),
                        html.Div(
                            [
                                dcc.Store(id="upload-result"),
                                html.Label("选择 CSV / Excel 文件", className="field-label-text"),
                                html.Div(
                                    id="file-input-container",
                                    children="正在准备文件控件…",
                                    className="file-input-container",
                                ),
                                html.Button(
                                    "上传并加载",
                                    id="file-upload-button",
                                    n_clicks=0,
                                    type="button",
                                    className="primary-button",
                                ),
                                html.Div(
                                    id="upload-status",
                                    className="status-message",
                                    role="status",
                                    **{"aria-live": "polite"},
                                ),
                            ],
                            id="file-upload-controls",
                            className="file-upload-section",
                            style=_FILE_UPLOAD_STYLE,
                        ),
                        html.H3("可用标签", className="panel-subtitle"),
                        dcc.Checklist(
                            id="variable-selector",
                            options=[],
                            value=[],
                            className="variable-checklist",
                            labelStyle={"display": "block"},
                            inputStyle={"marginRight": "0.4rem"},
                        ),
                        html.Button(
                            "清空选择",
                            id="clear-data-button",
                            n_clicks=0,
                            type="button",
                            className="secondary-button",
                        ),
                    ],
                    className="parameter-panel",
                ),
                html.Main(
                    [
                        dcc.Tabs(
                            id="viewer-tabs",
                            value="trend-tab",
                            className="viewer-tabs",
                            parent_className="viewer-tabs-parent",
                            content_className="viewer-tabs-content",
                            children=[
                                dcc.Tab(
                                    label="趋势图",
                                    value="trend-tab",
                                    className="viewer-tab",
                                    selected_className="viewer-tab-selected",
                                    children=[
                                        html.Div(
                                            [
                                                html.Label(
                                                    [
                                                        html.Span(
                                                            "显示开始时间",
                                                            className="field-label-copy",
                                                        ),
                                                        dcc.Input(
                                                            id="trend-start-time",
                                                            type="datetime-local",
                                                            step=1,
                                                            className="text-input",
                                                            style=_TREND_CONTROL_STYLE,
                                                        ),
                                                    ],
                                                    className="field-label trend-basic-field",
                                                ),
                                                html.Label(
                                                    [
                                                        html.Span(
                                                            "显示结束时间",
                                                            className="field-label-copy",
                                                        ),
                                                        dcc.Input(
                                                            id="trend-end-time",
                                                            type="datetime-local",
                                                            step=1,
                                                            className="text-input",
                                                            style=_TREND_CONTROL_STYLE,
                                                        ),
                                                    ],
                                                    className="field-label trend-basic-field",
                                                ),
                                                html.Label(
                                                    [
                                                        html.Span(
                                                            "最大绘图点数",
                                                            className="field-label-copy",
                                                        ),
                                                        dcc.Input(
                                                            id="trend-max-points",
                                                            type="number",
                                                            min=_MIN_PLOT_POINTS,
                                                            max=_MAX_PLOT_POINTS,
                                                            step=1,
                                                            value=_DEFAULT_MAX_PLOT_POINTS,
                                                            className="text-input",
                                                            style=_TREND_CONTROL_STYLE,
                                                        ),
                                                    ],
                                                    className="field-label trend-basic-field",
                                                ),
                                                html.Label(
                                                    [
                                                        html.Span("Y 轴", className="field-label-copy"),
                                                        dcc.Dropdown(
                                                            id="trend-axis-mode",
                                                            options=[
                                                                {
                                                                    "label": "同一 Y 轴",
                                                                    "value": "shared",
                                                                },
                                                                {
                                                                    "label": "独立 Y 轴",
                                                                    "value": "independent",
                                                                },
                                                            ],
                                                            value="independent",
                                                            clearable=False,
                                                            className="select-control",
                                                            style=_TREND_CONTROL_STYLE,
                                                        ),
                                                    ],
                                                    className="field-label trend-basic-field",
                                                ),
                                                html.Button(
                                                    "显示趋势",
                                                    id="show-trend-button",
                                                    n_clicks=0,
                                                    disabled=True,
                                                    type="button",
                                                    className="primary-button",
                                                    style=_TREND_CONTROL_STYLE
                                                    | {
                                                        "minHeight": "32px",
                                                    },
                                                ),
                                            ],
                                            id="trend-controls",
                                            className="trend-controls",
                                            style={
                                                "display": "grid",
                                                "gridTemplateColumns": "repeat(5, minmax(0, 1fr))",
                                                "gap": "0.5rem",
                                                "alignItems": "stretch",
                                            },
                                        ),
                                        dcc.Loading(
                                            id="trend-loading",
                                            type="dot",
                                            color="#176b87",
                                            custom_spinner=html.Div(
                                                "正在生成趋势图…",
                                                className="loading-message",
                                            ),
                                            children=html.Div(
                                                [
                                                    html.Div(
                                                        [
                                                            html.Strong("暂无趋势结果"),
                                                            html.Span(
                                                                "加载数据后，点击“显示趋势”查看时间序列。"
                                                            ),
                                                        ],
                                                        id="trend-empty-state",
                                                        className="empty-state",
                                                        role="status",
                                                        **{"aria-live": "polite"},
                                                    ),
                                                    dcc.Graph(
                                                        id="trend-graph",
                                                        className="trend-graph",
                                                        config={
                                                            "displaylogo": False,
                                                            "scrollZoom": True,
                                                        },
                                                        style={"height": "600px"},
                                                    ),
                                                ],
                                                className="visualization-frame",
                                            ),
                                        ),
                                        html.Div(
                                            [
                                                html.Div(
                                                    [
                                                        html.H2("基础统计", className="section-subtitle"),
                                                        html.Div(
                                                            id="statistics-cards",
                                                            className="statistics-cards",
                                                            children=[],
                                                            style=_STATISTICS_GRID_STYLE,
                                                        ),
                                                    ],
                                                    className="detail-content",
                                                ),
                                            ],
                                            className="detail-section",
                                        ),
                                    ],
                                ),
                                dcc.Tab(
                                    label="散点矩阵",
                                    value="scatter-tab",
                                    className="viewer-tab",
                                    selected_className="viewer-tab-selected",
                                    children=[
                                        html.Div(
                                            [
                                                html.Button(
                                                    "显示矩阵",
                                                    id="show-scatter-button",
                                                    n_clicks=0,
                                                    disabled=True,
                                                    type="button",
                                                    className="primary-button",
                                                    style=_TREND_CONTROL_STYLE
                                                    | {"width": "100px", "height": "38px"},
                                                ),
                                            ],
                                            className="scatter-title-row",
                                        ),
                                        html.Div(
                                            [
                                                html.Div(
                                                    [
                                                        html.Label(
                                                            [
                                                                html.Span(
                                                                    f"X 变量 {index}",
                                                                    className="field-label-copy",
                                                                ),
                                                                dcc.Dropdown(
                                                                    id=f"scatter-x-{index}",
                                                                    options=[],
                                                                    placeholder="请选择变量",
                                                                    className="select-control",
                                                                ),
                                                            ],
                                                            className="field-label",
                                                        ),
                                                    ],
                                                    className="scatter-axis-field",
                                                )
                                                for index in range(1, MAX_SCATTER_VARIABLES + 1)
                                            ],
                                            className="scatter-axis-group",
                                        ),
                                        html.Div(
                                            [
                                                html.Div(
                                                    [
                                                        html.Label(
                                                            [
                                                                html.Span(
                                                                    f"Y 变量 {index}",
                                                                    className="field-label-copy",
                                                                ),
                                                                dcc.Dropdown(
                                                                    id=f"scatter-y-{index}",
                                                                    options=[],
                                                                    placeholder="请选择变量",
                                                                    className="select-control",
                                                                ),
                                                            ],
                                                            className="field-label",
                                                        ),
                                                    ],
                                                    className="scatter-axis-field",
                                                )
                                                for index in range(1, MAX_SCATTER_VARIABLES + 1)
                                            ],
                                            className="scatter-axis-group",
                                        ),
                                        html.Div(
                                            id="scatter-status",
                                            className="status-message",
                                            role="status",
                                            children="尚未生成散点矩阵",
                                            **{"aria-live": "polite"},
                                        ),
                                        dcc.Loading(
                                            id="scatter-loading",
                                            type="dot",
                                            color="#176b87",
                                            custom_spinner=html.Div(
                                                "正在生成散点矩阵…",
                                                className="loading-message",
                                            ),
                                            children=html.Div(
                                                [
                                                    html.Div(
                                                        [
                                                            html.Strong("暂无散点结果"),
                                                            html.Span(
                                                                "选择 X/Y 变量后，点击按钮生成矩阵。"
                                                            ),
                                                        ],
                                                        id="scatter-empty-state",
                                                        className="empty-state",
                                                        role="status",
                                                        **{"aria-live": "polite"},
                                                    ),
                                                    dcc.Graph(
                                                        id="scatter-graph",
                                                        className="scatter-graph",
                                                        responsive=True,
                                                        config={
                                                            "displaylogo": False,
                                                            "scrollZoom": False,
                                                        },
                                                        style={
                                                            "width": "420px",
                                                            "maxWidth": "100%",
                                                            "height": "420px",
                                                        },
                                                    ),
                                                ],
                                                className="scatter-visualization-frame",
                                            ),
                                        ),
                                    ],
                                ),
                                dcc.Tab(
                                    label="箱线图",
                                    value="boxplot-tab",
                                    className="viewer-tab",
                                    selected_className="viewer-tab-selected",
                                    children=[
                                        html.Label(
                                            [
                                                html.Span(
                                                    "Y轴显示",
                                                    className="field-label-copy",
                                                ),
                                                dcc.RadioItems(
                                                    id="boxplot-axis-mode",
                                                    options=[
                                                        {
                                                            "label": "独立尺度（默认）",
                                                            "value": "independent",
                                                        },
                                                        {"label": "统一尺度", "value": "shared"},
                                                    ],
                                                    value="independent",
                                                    inline=True,
                                                    className="source-switch",
                                                ),
                                            ],
                                            className="field-label",
                                        ),
                                        html.P(
                                            [
                                                "当前选择变量：",
                                                html.Span(
                                                    "未选择变量",
                                                    id="boxplot-selected-columns",
                                                ),
                                            ],
                                            className="section-help",
                                        ),
                                        html.Div(
                                            id="boxplot-status",
                                            className="status-message",
                                            role="status",
                                            children="尚未生成箱线图",
                                            **{"aria-live": "polite"},
                                        ),
                                        html.Div(
                                            dcc.Loading(
                                                id="boxplot-loading",
                                                type="dot",
                                                color="#176b87",
                                                custom_spinner=html.Div(
                                                    "正在生成箱线图…",
                                                    className="loading-message",
                                                ),
                                                children=dcc.Graph(
                                                    id="boxplot-graph",
                                                    className="boxplot-graph",
                                                    figure=_empty_boxplot_figure(),
                                                    config={
                                                        "displaylogo": False,
                                                        "scrollZoom": False,
                                                    },
                                                    style={"height": "600px"},
                                                ),
                                            ),
                                            className="visualization-frame boxplot-visualization-frame",
                                            id="boxplot-visualization-frame",
                                        ),
                                    ],
                                ),
                                dcc.Tab(
                                    label="概率图",
                                    value="probability-plot-tab",
                                    className="viewer-tab",
                                    selected_className="viewer-tab-selected",
                                    children=[
                                        html.P(
                                            [
                                                "当前选择变量：",
                                                html.Span(
                                                    "未选择变量",
                                                    id="probability-plot-selected-columns",
                                                ),
                                            ],
                                            className="section-help",
                                        ),
                                        html.Div(
                                            id="probability-plot-status",
                                            className="status-message",
                                            role="status",
                                            children="尚未生成概率图",
                                            **{"aria-live": "polite"},
                                        ),
                                        dcc.Loading(
                                            id="probability-plot-loading",
                                            type="dot",
                                            color="#176b87",
                                            custom_spinner=html.Div(
                                                "正在生成概率图…",
                                                className="loading-message",
                                            ),
                                            children=html.Div(
                                                dcc.Graph(
                                                    id="probability-plot-graph",
                                                    className="probability-plot-graph",
                                                    figure=_empty_probability_plot_figure(),
                                                    config={
                                                        "displaylogo": False,
                                                        "scrollZoom": False,
                                                    },
                                                    style={"height": "600px"},
                                                ),
                                                className="visualization-frame probability-plot-visualization-frame",
                                            ),
                                        ),
                                    ],
                                ),
                                dcc.Tab(
                                    label="能力分析",
                                    value="capability-tab",
                                    className="viewer-tab",
                                    selected_className="viewer-tab-selected",
                                    children=[
                                        html.P(
                                            "正态能力分析假设过程处于稳定状态且数据近似正态分布。可用概率图检查分布，并结合控制图判断过程稳定性。",
                                            className="section-help",
                                        ),
                                        html.Div(
                                            [
                                                html.Label(
                                                    [
                                                        html.Span("规格下限（LSL）", className="field-label-copy"),
                                                        dcc.Input(
                                                            id="capability-lsl",
                                                            type="number",
                                                            debounce=True,
                                                            placeholder="可选",
                                                            className="text-input",
                                                        ),
                                                    ],
                                                    className="field-label",
                                                ),
                                                html.Label(
                                                    [
                                                        html.Span("规格上限（USL）", className="field-label-copy"),
                                                        dcc.Input(
                                                            id="capability-usl",
                                                            type="number",
                                                            debounce=True,
                                                            placeholder="可选",
                                                            className="text-input",
                                                        ),
                                                    ],
                                                    className="field-label",
                                                ),
                                            ],
                                            className="capability-specification-controls",
                                        ),
                                        html.P(
                                            [
                                                "当前选择变量：",
                                                html.Span(
                                                    "未选择变量",
                                                    id="capability-selected-columns",
                                                ),
                                            ],
                                            className="section-help",
                                        ),
                                        html.Div(
                                            id="capability-status",
                                            className="status-message",
                                            role="status",
                                            children="尚未生成能力分析",
                                            **{"aria-live": "polite"},
                                        ),
                                        dcc.Loading(
                                            id="capability-loading",
                                            type="dot",
                                            color="#176b87",
                                            custom_spinner=html.Div(
                                                "正在生成能力分析…",
                                                className="loading-message",
                                            ),
                                            children=dcc.Graph(
                                                id="capability-graph",
                                                className="capability-graph",
                                                figure=_empty_capability_figure(),
                                                config={
                                                    "displaylogo": False,
                                                    "scrollZoom": False,
                                                },
                                                style={"height": "600px"},
                                            ),
                                        ),
                                        html.Div(
                                            id="capability-summary",
                                            className="capability-summary",
                                            children=_empty_capability_summary(),
                                        ),
                                    ],
                                ),
                                dcc.Tab(
                                    label="控制图",
                                    value="control-chart-tab",
                                    className="viewer-tab",
                                    selected_className="viewer-tab-selected",
                                    children=[
                                        html.P(
                                            [
                                                "当前选择变量：",
                                                html.Span(
                                                    "未选择变量",
                                                    id="control-chart-selected-columns",
                                                ),
                                            ],
                                            className="section-help",
                                        ),
                                        html.Label(
                                            [
                                                html.Span(
                                                    "判异检验",
                                                    className="field-label-copy",
                                                ),
                                                dcc.Dropdown(
                                                    id="control-chart-tests",
                                                    options=_CONTROL_CHART_TEST_OPTIONS,
                                                    value=[1],
                                                    multi=True,
                                                    placeholder="不执行判异检验",
                                                    className="select-control",
                                                ),
                                            ],
                                            className="field-label control-chart-tests",
                                        ),
                                        html.P(
                                            "Minitab 默认仅启用检验 1；I 图支持检验 1–8，MR 图仅使用检验 1–4。",
                                            className="section-help control-chart-test-help",
                                        ),
                                        html.Div(
                                            id="control-chart-status",
                                            className="status-message",
                                            role="status",
                                            children="尚未生成控制图",
                                            **{"aria-live": "polite"},
                                        ),
                                        dcc.Loading(
                                            id="control-chart-loading",
                                            type="dot",
                                            color="#176b87",
                                            custom_spinner=html.Div(
                                                "正在生成 I-MR 控制图…",
                                                className="loading-message",
                                            ),
                                            children=html.Div(
                                                dcc.Graph(
                                                    id="control-chart-graph",
                                                    className="control-chart-graph",
                                                    figure=_empty_control_chart_figure(),
                                                    config={
                                                        "displaylogo": False,
                                                        "scrollZoom": False,
                                                    },
                                                    style={"height": "760px"},
                                                ),
                                                className="visualization-frame control-chart-visualization-frame",
                                            ),
                                        ),
                                    ],
                                ),
                                dcc.Tab(
                                    label="频谱分析",
                                    value="frequency-analysis-tab",
                                    className="viewer-tab",
                                    selected_className="viewer-tab-selected",
                                    children=[
                                        html.P(
                                            "FFT 用于识别等间隔工业时序数据中的周期成分。分析前自动去除均值并应用汉宁窗。FFT 要求连续且等间隔采样；本工具不会自动插值或重采样数据。",
                                            className="section-help",
                                        ),
                                        html.P(
                                            [
                                                "当前选择变量：",
                                                html.Span(
                                                    "未选择变量",
                                                    id="frequency-selected-columns",
                                                ),
                                            ],
                                            className="section-help",
                                        ),
                                        html.Div(
                                            id="frequency-status",
                                            className="status-message",
                                            role="status",
                                            children="尚未生成频谱",
                                            **{"aria-live": "polite"},
                                        ),
                                        dcc.Loading(
                                            id="frequency-loading",
                                            type="dot",
                                            color="#176b87",
                                            custom_spinner=html.Div(
                                                "正在生成频谱…",
                                                className="loading-message",
                                            ),
                                            children=dcc.Graph(
                                                id="frequency-graph",
                                                className="frequency-graph",
                                                figure=_empty_frequency_figure(),
                                                config={
                                                    "displaylogo": False,
                                                    "scrollZoom": False,
                                                },
                                                style={"height": "600px"},
                                            ),
                                        ),
                                        html.Div(
                                            id="frequency-summary",
                                            className="frequency-summary",
                                            children=_empty_frequency_summary(),
                                        ),
                                    ],
                                ),
                            ],
                        ),
                        html.Section(
                            [
                                html.Div(
                                    [
                                        html.H2("运行日志", className="section-subtitle"),
                                        html.P(
                                            "查询、上传和图表生成状态会显示在这里。",
                                            className="section-help",
                                        ),
                                    ],
                                    className="section-heading",
                                ),
                                html.Div(
                                    [
                                        html.Span("数据状态", className="status-label"),
                                        dcc.Loading(
                                            id="data-status-loading",
                                            type="dot",
                                            color="#176b87",
                                            custom_spinner=html.Div(
                                                "正在读取数据…",
                                                className="loading-message",
                                            ),
                                            children=html.Div(
                                                id="load-status",
                                                className="status-message",
                                                role="status",
                                                children="尚未加载数据",
                                                **{"aria-live": "polite"},
                                            ),
                                        ),
                                    ],
                                    className="status-row",
                                ),
                                html.Div(
                                    [
                                        html.Span("操作状态", className="status-label"),
                                        html.Div(
                                            id="query-status",
                                            className="status-message status-message-secondary",
                                            role="status",
                                            children="等待趋势或散点操作",
                                            **{"aria-live": "polite"},
                                        ),
                                    ],
                                    className="status-row",
                                ),
                            ],
                            className="log-section",
                        ),
                    ],
                    className="results-panel",
                ),
            ],
            className="app-layout",
        ),
    ],
    className="page-shell",
)


def register_callbacks(app) -> None:
    app.callback(
        Output("pi-query-controls", "style"),
        Output("file-upload-controls", "style"),
        Input("data-source", "value"),
    )(update_source_controls)

    app.clientside_callback(
        _UPLOAD_CLIENTSIDE_FUNCTION,
        Output("upload-result", "data"),
        Output("upload-status", "children"),
        Input("file-upload-button", "n_clicks"),
        prevent_initial_call=True,
    )

    app.callback(
        Output("viewer-state", "data"),
        Output("variable-selector", "value"),
        Input("query-button", "n_clicks"),
        Input("upload-result", "data"),
        Input("clear-data-button", "n_clicks"),
        State("data-source", "value"),
        State("tag-input", "value"),
        State("start-time", "value"),
        State("end-time", "value"),
        State("interval", "value"),
        prevent_initial_call=True,
    )(update_data_state)

    app.callback(
        Output("variable-selector", "options"),
        Input("viewer-state", "data"),
        Input("variable-selector", "value"),
        prevent_initial_call=True,
    )(update_variable_options)

    app.callback(
        Output("trend-start-time", "value"),
        Output("trend-end-time", "value"),
        Input("viewer-state", "data"),
        prevent_initial_call=True,
    )(update_trend_time_controls)

    app.callback(
        Output("show-trend-button", "disabled"),
        Input("viewer-state", "data"),
        Input("variable-selector", "value"),
        prevent_initial_call=True,
    )(update_show_trend_state)

    app.callback(
        Output("trend-graph", "figure"),
        Output("statistics-cards", "children"),
        Output("query-status", "children"),
        Input("viewer-state", "data"),
        Input("show-trend-button", "n_clicks"),
        State("variable-selector", "value"),
        State("trend-axis-mode", "value"),
        State("trend-start-time", "value"),
        State("trend-end-time", "value"),
        State("trend-max-points", "value"),
        prevent_initial_call=True,
    )(render_trend_view)

    app.callback(
        Output("scatter-x-1", "options"),
        Output("scatter-x-2", "options"),
        Output("scatter-x-3", "options"),
        Output("scatter-y-1", "options"),
        Output("scatter-y-2", "options"),
        Output("scatter-y-3", "options"),
        Input("viewer-state", "data"),
        prevent_initial_call=True,
    )(update_scatter_variable_options)

    app.callback(
        Output("show-scatter-button", "disabled"),
        Input("viewer-state", "data"),
        prevent_initial_call=True,
    )(update_show_scatter_state)

    app.callback(
        Output("scatter-graph", "style"),
        Input("viewer-tabs", "value"),
        Input("scatter-x-1", "value"),
        Input("scatter-x-2", "value"),
        Input("scatter-x-3", "value"),
        Input("scatter-y-1", "value"),
        Input("scatter-y-2", "value"),
        Input("scatter-y-3", "value"),
    )(update_scatter_graph_style)

    app.callback(
        Output("scatter-graph", "figure"),
        Output("scatter-status", "children"),
        Input("viewer-state", "data"),
        Input("show-scatter-button", "n_clicks"),
        State("scatter-x-1", "value"),
        State("scatter-x-2", "value"),
        State("scatter-x-3", "value"),
        State("scatter-y-1", "value"),
        State("scatter-y-2", "value"),
        State("scatter-y-3", "value"),
        prevent_initial_call=True,
    )(render_scatter_view)

    app.callback(
        Output("boxplot-graph", "figure"),
        Output("boxplot-selected-columns", "children"),
        Output("boxplot-status", "children"),
        Output("boxplot-visualization-frame", "style"),
        Input("viewer-state", "data"),
        Input("variable-selector", "value"),
        Input("boxplot-axis-mode", "value"),
        Input("viewer-tabs", "value"),
        prevent_initial_call=True,
    )(render_boxplot_view)

    app.callback(
        Output("probability-plot-graph", "figure"),
        Output("probability-plot-selected-columns", "children"),
        Output("probability-plot-status", "children"),
        Input("viewer-state", "data"),
        Input("variable-selector", "value"),
        Input("viewer-tabs", "value"),
        prevent_initial_call=True,
    )(render_probability_plot_view)

    app.callback(
        Output("capability-graph", "figure"),
        Output("capability-summary", "children"),
        Output("capability-selected-columns", "children"),
        Output("capability-status", "children"),
        Input("viewer-state", "data"),
        Input("variable-selector", "value"),
        Input("capability-lsl", "value"),
        Input("capability-usl", "value"),
        Input("viewer-tabs", "value"),
        prevent_initial_call=True,
    )(render_capability_view)

    app.callback(
        Output("control-chart-graph", "figure"),
        Output("control-chart-selected-columns", "children"),
        Output("control-chart-status", "children"),
        Input("viewer-state", "data"),
        Input("variable-selector", "value"),
        Input("control-chart-tests", "value"),
        Input("viewer-tabs", "value"),
        prevent_initial_call=True,
    )(render_control_chart_view)

    app.callback(
        Output("frequency-graph", "figure"),
        Output("frequency-summary", "children"),
        Output("frequency-selected-columns", "children"),
        Output("frequency-status", "children"),
        Input("viewer-state", "data"),
        Input("variable-selector", "value"),
        Input("viewer-tabs", "value"),
        prevent_initial_call=True,
    )(render_frequency_view)

    app.callback(
        Output("load-status", "children"),
        Input("viewer-state", "data"),
    )(update_load_status)

    app.callback(
        Output("trend-empty-state", "style"),
        Input("trend-graph", "figure"),
    )(update_trend_empty_state)

    app.callback(
        Output("scatter-empty-state", "style"),
        Input("scatter-graph", "figure"),
    )(update_scatter_empty_state)

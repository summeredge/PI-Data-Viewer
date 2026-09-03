"""Dash page for querying and displaying PI historical data."""

from __future__ import annotations

import math

import pandas as pd
from dash import Input, Output, State, callback_context, dcc, html
import plotly.graph_objects as go

from backend.dataframe_store import get_dataframe, store_dataframe
from backend.pi_reader import INTERVAL_OPTIONS, MAX_TAGS, normalize_tags, read_pi_data
from backend.statistics import calculate_series_summary, calculate_statistics
from charts.scatter import (
    DEFAULT_MAX_SCATTER_POINTS,
    MAX_SCATTER_VARIABLES,
    create_scatter_figure,
    prepare_scatter_frame,
)
from charts.trend import create_distribution_figure, create_trend_figure


_PI_SOURCE = "pi"
_FILE_SOURCE = "file"
_MAX_SELECTED_COLUMNS = MAX_TAGS
_DEFAULT_MAX_PLOT_POINTS = 45_000
_MIN_PLOT_POINTS = 100
_MAX_PLOT_POINTS = 135_000
_MAX_TOTAL_PLOT_POINTS = 300_000
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
    "border": "1px solid #d9d9d9",
    "borderRadius": "10px",
    "backgroundColor": "#fff",
    "padding": "12px",
}
_PI_QUERY_STYLE = {
    "display": "flex",
    "flexDirection": "column",
    "gap": "0.5rem",
}
_FILE_UPLOAD_STYLE = {
    "display": "none",
    "border": "1px dashed #999",
    "borderRadius": "4px",
    "padding": "1rem",
    "textAlign": "center",
}
_TREND_CONTROL_STYLE = {"width": "100%", "height": "38px"}
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
        raise ValueError("请输入至少一个Tag")
    return normalize_tags(value.replace(",", "\n").splitlines())


def _empty_figure():
    return create_trend_figure(pd.DataFrame(index=pd.DatetimeIndex([], name="Timestamp")))


def _empty_scatter_figure():
    figure = go.Figure()
    figure.update_layout(template="plotly_white")
    return figure


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


def _resolve_max_plot_points(value, series_count: int) -> int:
    if value in (None, ""):
        requested = _DEFAULT_MAX_PLOT_POINTS
    else:
        try:
            requested = int(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("最大绘图点数必须是整数") from exc
    requested = min(_MAX_PLOT_POINTS, max(_MIN_PLOT_POINTS, requested))
    per_series_cap = max(
        _MIN_PLOT_POINTS,
        _MAX_TOTAL_PLOT_POINTS // max(1, int(series_count)),
    )
    return min(requested, per_series_cap)


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
        positions = [
            int(index * (len(display) - 1) / (effective_max_points - 1))
            for index in range(effective_max_points)
        ]
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
    statistics = calculate_statistics(full_frame.loc[:, selected])
    return (
        create_trend_figure(display_frame, selected, axis_mode),
        _statistics_records(statistics),
        _statistics_cards(full_frame, selected),
        f"趋势图已生成，原始 {len(full_frame)} 点，显示 {len(display_frame)} 点，"
        f"最大点数 {effective_max_points}。",
    )


def _render_frame(
    frame: pd.DataFrame, selected_columns: list, axis_mode: str = "shared"
) -> tuple:
    if not selected_columns:
        return _empty_figure(), [], []
    selected_frame = frame.loc[:, selected_columns]
    statistics = calculate_statistics(selected_frame)
    return (
        create_trend_figure(frame, selected_columns, axis_mode),
        _statistics_records(statistics),
        _statistics_cards(frame, selected_columns),
    )


def _statistics_records(statistics: pd.DataFrame) -> list[dict]:
    records = []
    for tag, row in statistics.iterrows():
        record = {"Tag": str(tag)}
        for column, value in row.items():
            if pd.isna(value):
                record[column] = None
            elif hasattr(value, "item"):
                record[column] = value.item()
            else:
                record[column] = value
        records.append(record)
    return records


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


def update_viewer(
    n_clicks,
    tag_value,
    start_time,
    end_time,
    source=_PI_SOURCE,
    upload_result=None,
    selected_columns=None,
    interval="1m",
):
    status, _, selected, ready = _load_viewer(
        n_clicks,
        tag_value,
        start_time,
        end_time,
        source,
        upload_result,
        selected_columns,
        interval,
    )
    current = get_dataframe()
    if not ready or current is None:
        return _empty_figure(), [], status
    figure, records, _ = _render_frame(current, selected)
    return figure, records, status


def _viewer_state(options, status, ready):
    return {
        "options": options,
        "status": status,
        "ready": ready,
        "revision": _next_revision(),
    }


def _render_selected_view(selected_columns, viewer_state=None):
    state = viewer_state if isinstance(viewer_state, dict) else {}
    current = get_dataframe()
    if current is None or current.empty or (
        viewer_state is not None and not state.get("ready")
    ):
        return _empty_figure(), [], [], state.get("status", "")

    _, selected, status = _variable_selection_state(current, selected_columns)
    if not selected:
        return _empty_figure(), [], [], "请至少选择一个变量"
    figure, records, cards = _render_frame(current, selected)
    return figure, records, cards, status or state.get("status", "")


def update_selected_view(selected_columns, viewer_state=None):
    figure, records, _, status = _render_selected_view(selected_columns, viewer_state)
    return figure, records, status


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
        return _viewer_state([], "请切换到 PI Server 模式", False), []
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
        interval=interval,
    )
    return _viewer_state(options, status, ready), selected


def render_viewer(viewer_state, selected_columns):
    state = viewer_state if isinstance(viewer_state, dict) else {}
    figure, _, cards, status = _render_selected_view(selected_columns, viewer_state)
    if selected_columns and len(selected_columns) > _MAX_SELECTED_COLUMNS:
        status = f"最多选择{_MAX_SELECTED_COLUMNS}个变量，已保留前{_MAX_SELECTED_COLUMNS}个变量"
    elif not selected_columns and state.get("ready"):
        status = "请至少选择一个变量"
    return figure, cards, status


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
        figure, _, cards, status = _render_trend_frame(
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
    x_selected, y_selected, _, display = prepare_scatter_frame(
        frame, x_columns, y_columns, max_points
    )
    return (
        create_scatter_figure(
            display, x_selected, y_selected, max_points=len(display)
        ),
        f"实际绘图点数 {len(display)} / {len(frame)}；"
        f"X数量 {len(x_selected)} × Y数量 {len(y_selected)}",
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


def update_source_controls(source):
    if source == _FILE_SOURCE:
        return {**_PI_QUERY_STYLE, "display": "none"}, {
            **_FILE_UPLOAD_STYLE,
            "display": "block",
        }
    return _PI_QUERY_STYLE, _FILE_UPLOAD_STYLE


layout = html.Div(
    [
        dcc.Store(id="viewer-state"),
        html.H1("PI Data Viewer"),
        html.Div(
            [
                html.Aside(
                    [
                        html.H2("查询参数"),
                        html.Label("数据来源"),
                        dcc.RadioItems(
                            id="data-source",
                            options=[
                                {"label": "PI Server", "value": _PI_SOURCE},
                                {"label": "本地文件", "value": _FILE_SOURCE},
                            ],
                            value=_PI_SOURCE,
                            inline=True,
                        ),
                        html.Div(
                            [
                                html.Label(f"PI Tag（每行一个，最多{MAX_TAGS}个）"),
                                dcc.Textarea(
                                    id="tag-input",
                                    placeholder="TAG001.PV\nTAG002.PV",
                                    style={"width": "100%", "height": "120px"},
                                ),
                                html.Label("开始时间"),
                                dcc.Input(
                                    id="start-time",
                                    type="text",
                                    placeholder="YYYY-MM-DD HH:MM:SS",
                                    style={"width": "100%"},
                                ),
                                html.Label("结束时间"),
                                dcc.Input(
                                    id="end-time",
                                    type="text",
                                    placeholder="YYYY-MM-DD HH:MM:SS",
                                    style={"width": "100%"},
                                ),
                                html.Label("Interval"),
                                dcc.Dropdown(
                                    id="interval",
                                    options=[
                                        {"label": value, "value": value}
                                        for value in INTERVAL_OPTIONS
                                    ],
                                    value=INTERVAL_OPTIONS[0],
                                    clearable=False,
                                ),
                                html.Button("查询", id="query-button", n_clicks=0),
                            ],
                            id="pi-query-controls",
                            style=_PI_QUERY_STYLE,
                        ),
                        html.Div(
                            [
                                dcc.Store(id="upload-result"),
                                html.Label("选择 CSV / Excel 文件"),
                                html.Div(
                                    id="file-input-container",
                                    children="正在准备文件控件…",
                                ),
                                html.Button(
                                    "上传并加载",
                                    id="file-upload-button",
                                    n_clicks=0,
                                ),
                                html.Div(
                                    id="upload-status",
                                    role="status",
                                    **{"aria-live": "polite"},
                                ),
                            ],
                            id="file-upload-controls",
                            style=_FILE_UPLOAD_STYLE,
                        ),
                        html.H3("当前变量"),
                        dcc.Checklist(
                            id="variable-selector",
                            options=[],
                            value=[],
                            labelStyle={"display": "block"},
                            inputStyle={"marginRight": "0.4rem"},
                        ),
                        html.Button(
                            "清空选择",
                            id="clear-data-button",
                            n_clicks=0,
                            style={"width": "100px"},
                        ),
                        html.Div(id="query-status", role="status", **{"aria-live": "polite"}),
                    ],
                    style={
                        "borderRight": "1px solid #d9d9d9",
                        "display": "flex",
                        "flexDirection": "column",
                        "gap": "0.5rem",
                        "padding": "1rem",
                        "width": "240px",
                    },
                ),
                html.Main(
                    [
                        dcc.Tabs(
                            id="viewer-tabs",
                            value="trend-tab",
                            children=[
                                dcc.Tab(
                                    label="Trend",
                                    value="trend-tab",
                                    children=[
                                        html.H2("趋势图"),
                                        html.Div(
                                            [
                                                html.Label(
                                                    [
                                                        "开始时间",
                                                        dcc.Input(
                                                            id="trend-start-time",
                                                            type="datetime-local",
                                                            step=1,
                                                            style=_TREND_CONTROL_STYLE,
                                                        ),
                                                    ],
                                                    style={
                                                        "display": "grid",
                                                        "gap": "0.25rem",
                                                    },
                                                ),
                                                html.Label(
                                                    [
                                                        "结束时间",
                                                        dcc.Input(
                                                            id="trend-end-time",
                                                            type="datetime-local",
                                                            step=1,
                                                            style=_TREND_CONTROL_STYLE,
                                                        ),
                                                    ],
                                                    style={
                                                        "display": "grid",
                                                        "gap": "0.25rem",
                                                    },
                                                ),
                                                html.Label(
                                                    [
                                                        "最大绘图点数",
                                                        dcc.Input(
                                                            id="trend-max-points",
                                                            type="number",
                                                            min=_MIN_PLOT_POINTS,
                                                            max=_MAX_PLOT_POINTS,
                                                            step=1,
                                                            value=_DEFAULT_MAX_PLOT_POINTS,
                                                            style=_TREND_CONTROL_STYLE,
                                                        ),
                                                    ],
                                                    style={
                                                        "display": "grid",
                                                        "gap": "0.25rem",
                                                    },
                                                ),
                                                html.Label(
                                                    [
                                                        "Y 轴",
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
                                                            value="shared",
                                                            clearable=False,
                                                            style=_TREND_CONTROL_STYLE,
                                                        ),
                                                    ],
                                                    style={
                                                        "display": "grid",
                                                        "gap": "0.25rem",
                                                    },
                                                ),
                                                html.Button(
                                                    "显示趋势",
                                                    id="show-trend-button",
                                                    n_clicks=0,
                                                    disabled=True,
                                                    style=_TREND_CONTROL_STYLE,
                                                ),
                                            ],
                                            style={
                                                "display": "grid",
                                                "gridTemplateColumns": "repeat(5, minmax(0, 1fr))",
                                                "gap": "0.5rem",
                                                "alignItems": "end",
                                            },
                                        ),
                                        dcc.Graph(
                                            id="trend-graph",
                                            config={"displaylogo": False, "scrollZoom": True},
                                            style={"height": "600px"},
                                        ),
                                    ],
                                ),
                                dcc.Tab(
                                    label="XY Scatter",
                                    value="scatter-tab",
                                    children=[
                                        html.H2("XY 散点矩阵"),
                                        html.Div(
                                            [
                                                html.Div(
                                                    [
                                                        html.Label(f"X变量{index}"),
                                                        dcc.Dropdown(
                                                            id=f"scatter-x-{index}",
                                                            options=[],
                                                            placeholder="请选择变量",
                                                        ),
                                                    ],
                                                    style={
                                                        "display": "grid",
                                                        "gap": "0.25rem",
                                                    },
                                                )
                                                for index in range(1, MAX_SCATTER_VARIABLES + 1)
                                            ],
                                            style={
                                                "display": "grid",
                                                "gridTemplateColumns": "repeat(3, minmax(0, 1fr))",
                                                "gap": "0.5rem",
                                            },
                                        ),
                                        html.Div(
                                            [
                                                html.Div(
                                                    [
                                                        html.Label(f"Y变量{index}"),
                                                        dcc.Dropdown(
                                                            id=f"scatter-y-{index}",
                                                            options=[],
                                                            placeholder="请选择变量",
                                                        ),
                                                    ],
                                                    style={
                                                        "display": "grid",
                                                        "gap": "0.25rem",
                                                    },
                                                )
                                                for index in range(1, MAX_SCATTER_VARIABLES + 1)
                                            ],
                                            style={
                                                "display": "grid",
                                                "gridTemplateColumns": "repeat(3, minmax(0, 1fr))",
                                                "gap": "0.5rem",
                                            },
                                        ),
                                        html.Button(
                                            "显示散点矩阵",
                                            id="show-scatter-button",
                                            n_clicks=0,
                                            disabled=True,
                                            style=_TREND_CONTROL_STYLE | {"width": "180px"},
                                        ),
                                        html.Div(
                                            id="scatter-status",
                                            role="status",
                                            **{"aria-live": "polite"},
                                        ),
                                        dcc.Graph(
                                            id="scatter-graph",
                                            config={"displaylogo": False, "scrollZoom": False},
                                            style={"height": "780px"},
                                        ),
                                    ],
                                ),
                                dcc.Tab(
                                    label="Statistics",
                                    value="statistics-tab",
                                    children=[
                                        html.H2("基础统计"),
                                        html.Div(
                                            id="statistics-cards",
                                            className="statistics-cards",
                                            children=[],
                                            style=_STATISTICS_GRID_STYLE,
                                        ),
                                    ],
                                ),
                            ],
                        ),
                    ],
                    style={"flex": "1", "padding": "1rem"},
                ),
            ],
            style={"display": "flex", "minHeight": "400px"},
        ),
    ],
    style={"fontFamily": "Arial, sans-serif", "margin": "2rem"},
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

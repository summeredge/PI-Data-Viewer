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
    calculate_scatter_dimensions,
    create_scatter_figure,
    prepare_scatter_frame,
)
from charts.boxplot import create_boxplot_figure
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


def _empty_boxplot_figure():
    return create_boxplot_figure(pd.DataFrame(), [])


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
        _statistics_records(statistics),
        _statistics_cards(full_frame, selected),
        f"趋势图已生成，原始 {len(full_frame)} 点，显示 {len(display_frame)} 点，"
        f"{max_points_status}。",
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
        selected_columns=[],
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


def render_boxplot_view(
    viewer_state,
    selected_columns=None,
    axis_mode="independent",
):
    state = viewer_state if isinstance(viewer_state, dict) else {}
    if not state.get("ready"):
        return _empty_boxplot_figure(), "未选择变量", state.get("status") or "尚未加载数据"

    current = get_dataframe()
    if current is None:
        return _empty_boxplot_figure(), "未选择变量", "尚未加载数据"

    selected = _selected_columns(current, selected_columns)
    if not selected:
        return create_boxplot_figure(current, []), "未选择变量", "请至少选择一个变量"

    try:
        figure = create_boxplot_figure(current, selected, axis_mode)
    except (TypeError, ValueError) as exc:
        return _empty_boxplot_figure(), ", ".join(map(str, selected)), str(exc)
    if current.empty:
        return figure, ", ".join(map(str, selected)), "暂无可用数据"
    status = "" if figure.data else "所选变量无有效数值数据"
    return figure, ", ".join(map(str, selected)), status


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
                html.Div("HISTORICAL DATA VIEWER", className="eyebrow"),
                html.H1("PI Data Viewer"),
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
                        html.H2("Tag Explorer", className="panel-title"),
                        html.Label("数据来源", className="field-label-text"),
                        dcc.RadioItems(
                            id="data-source",
                            options=[
                                {"label": "PI Server", "value": _PI_SOURCE},
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
                                            f"PI Tag（每行一个，最多{MAX_TAGS}个）",
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
                                        {"label": value, "value": value}
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
                                    label="Trend",
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
                                                "alignItems": "end",
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
                                    label="XY Scatter",
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
                                    label="Box Plot",
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
                                html.Div(
                                    id="query-status",
                                    className="status-message status-message-secondary",
                                    role="status",
                                    children="等待趋势或散点操作",
                                    **{"aria-live": "polite"},
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
        Input("viewer-state", "data"),
        Input("variable-selector", "value"),
        Input("boxplot-axis-mode", "value"),
        prevent_initial_call=True,
    )(render_boxplot_view)

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

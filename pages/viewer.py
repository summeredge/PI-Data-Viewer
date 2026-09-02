"""Dash page for querying and displaying PI historical data."""

from __future__ import annotations

import math

import pandas as pd
from dash import Input, Output, State, callback_context, dcc, html

from backend.dataframe_store import clear_dataframe, get_dataframe, store_dataframe
from backend.file_reader import read_local_file
from backend.pi_reader import INTERVAL_OPTIONS, MAX_TAGS, normalize_tags, read_pi_data
from backend.statistics import calculate_series_summary, calculate_statistics
from charts.trend import create_distribution_figure, create_trend_figure


_PI_SOURCE = "pi"
_FILE_SOURCE = "file"
_MAX_SELECTED_COLUMNS = MAX_TAGS
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


def parse_tags(value: str) -> list[str]:
    if not isinstance(value, str):
        raise ValueError("请输入至少一个Tag")
    return normalize_tags(value.replace(",", "\n").splitlines())


def _empty_figure():
    return create_trend_figure(pd.DataFrame(index=pd.DatetimeIndex([], name="Timestamp")))


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


def _render_frame(frame: pd.DataFrame, selected_columns: list) -> tuple:
    if not selected_columns:
        return _empty_figure(), [], []
    selected_frame = frame.loc[:, selected_columns]
    statistics = calculate_statistics(selected_frame)
    return (
        create_trend_figure(frame, selected_columns),
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
    upload_contents=None,
    upload_filename=None,
    selected_columns=None,
    interval="1m",
):
    if source == _FILE_SOURCE:
        if not upload_contents:
            return "请上传 CSV 或 Excel 文件", [], [], False
        try:
            frame = read_local_file(upload_contents, upload_filename)
        except Exception as exc:
            message = str(exc) or exc.__class__.__name__
            return f"文件读取失败：{message}", [], [], False
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
    upload_contents=None,
    upload_filename=None,
    selected_columns=None,
    interval="1m",
):
    status, _, selected, ready = _load_viewer(
        n_clicks,
        tag_value,
        start_time,
        end_time,
        source,
        upload_contents,
        upload_filename,
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


def update_data_state(
    n_clicks,
    source,
    upload_contents,
    clear_clicks,
    tag_value,
    start_time,
    end_time,
    upload_filename,
    interval="1m",
):
    if _triggered_id() == "clear-data-button":
        clear_dataframe()
        return _viewer_state([], "数据已清空", False), []

    status, options, selected, ready = _load_viewer(
        n_clicks,
        tag_value,
        start_time,
        end_time,
        source,
        upload_contents,
        upload_filename,
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
                        dcc.Upload(
                            id="file-upload",
                            children=html.Div("拖拽或点击上传 CSV / Excel 文件"),
                            accept=".csv,.xlsx",
                            multiple=False,
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
                        html.Button("清空数据", id="clear-data-button", n_clicks=0),
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
                        html.H2("趋势图"),
                        dcc.Graph(
                            id="trend-graph",
                            config={"displaylogo": False, "scrollZoom": True},
                            style={"height": "600px"},
                        ),
                        html.H2("基础统计"),
                        html.Div(
                            id="statistics-cards",
                            className="statistics-cards",
                            children=[],
                            style=_STATISTICS_GRID_STYLE,
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
        Output("file-upload", "style"),
        Input("data-source", "value"),
    )(update_source_controls)

    app.callback(
        Output("viewer-state", "data"),
        Output("variable-selector", "value"),
        Input("query-button", "n_clicks"),
        Input("data-source", "value"),
        Input("file-upload", "contents"),
        Input("clear-data-button", "n_clicks"),
        State("tag-input", "value"),
        State("start-time", "value"),
        State("end-time", "value"),
        State("file-upload", "filename"),
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
        Output("trend-graph", "figure"),
        Output("statistics-cards", "children"),
        Output("query-status", "children"),
        Input("viewer-state", "data"),
        Input("variable-selector", "value"),
        prevent_initial_call=True,
    )(render_viewer)

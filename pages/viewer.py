"""Dash page for querying and displaying PI historical data."""

from __future__ import annotations

import pandas as pd
from dash import Input, Output, State, dash_table, dcc, html

from backend.dataframe_store import get_dataframe, store_dataframe
from backend.file_reader import read_local_file
from backend.pi_reader import MAX_TAGS, normalize_tags, read_pi_data
from backend.statistics import calculate_statistics
from charts.trend import create_trend_figure


_STAT_COLUMNS = ("count", "mean", "std", "min", "max")
_PI_SOURCE = "pi"
_FILE_SOURCE = "file"
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


def update_viewer(
    n_clicks,
    tag_value,
    start_time,
    end_time,
    source=_PI_SOURCE,
    upload_contents=None,
    upload_filename=None,
):
    if source == _FILE_SOURCE:
        if not upload_contents:
            return _empty_figure(), [], "请上传 CSV 或 Excel 文件"
        try:
            frame = read_local_file(upload_contents, upload_filename)
        except Exception as exc:
            message = str(exc) or exc.__class__.__name__
            return _empty_figure(), [], f"文件读取失败：{message}"
    else:
        if not n_clicks:
            return _empty_figure(), [], ""

        try:
            tags = parse_tags(tag_value)
        except ValueError as exc:
            return _empty_figure(), [], str(exc)

        try:
            frame = read_pi_data(tags, start_time, end_time)
        except Exception as exc:
            message = str(exc) or exc.__class__.__name__
            return _empty_figure(), [], f"数据读取失败：{message}"

    store_dataframe(frame)
    current = get_dataframe()
    if current is None or current.empty:
        return _empty_figure(), [], "查询时间范围内无数据"

    return (
        create_trend_figure(current),
        _statistics_records(calculate_statistics(current)),
        "",
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
                        dash_table.DataTable(
                            id="statistics-table",
                            columns=[
                                {"name": "Tag", "id": "Tag"},
                                *[{"name": column, "id": column} for column in _STAT_COLUMNS],
                            ],
                            data=[],
                            page_size=20,
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
        Output("trend-graph", "figure"),
        Output("statistics-table", "data"),
        Output("query-status", "children"),
        Input("query-button", "n_clicks"),
        Input("data-source", "value"),
        Input("file-upload", "contents"),
        State("tag-input", "value"),
        State("start-time", "value"),
        State("end-time", "value"),
        State("file-upload", "filename"),
        prevent_initial_call=True,
    )(lambda n_clicks, source, upload_contents, tag_value, start_time, end_time, upload_filename: update_viewer(
        n_clicks,
        tag_value,
        start_time,
        end_time,
        source,
        upload_contents,
        upload_filename,
    ))

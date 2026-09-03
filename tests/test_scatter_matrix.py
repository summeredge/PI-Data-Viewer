import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

from backend.dataframe_store import store_dataframe
from charts.scatter import (
    DEFAULT_MAX_SCATTER_POINTS,
    MAX_SCATTER_POINTS,
    create_scatter_figure,
    prepare_scatter_frame,
)
from pages import viewer


def _components(component):
    yield component
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        for child in children:
            yield from _components(child)
    elif children is not None:
        yield from _components(children)


def test_scatter_layout_has_controls_button_and_graph():
    ids = {component.id for component in _components(viewer.layout) if hasattr(component, "id")}

    assert {f"scatter-x-{index}" for index in range(1, 4)} <= ids
    assert {f"scatter-y-{index}" for index in range(1, 4)} <= ids
    assert {"show-scatter-button", "scatter-graph"} <= ids


def test_scatter_is_in_its_own_tab_and_not_in_trend_tab():
    tabs = viewer.layout.children[2].children[1].children[0]

    assert [tab.label for tab in tabs.children] == ["Trend", "XY Scatter"]
    trend_ids = {
        component.id
        for component in _components(tabs.children[0])
        if hasattr(component, "id")
    }
    scatter_ids = {
        component.id
        for component in _components(tabs.children[1])
        if hasattr(component, "id")
    }
    assert "trend-graph" in trend_ids
    assert "scatter-graph" not in trend_ids
    assert "statistics-cards" in trend_ids
    assert "scatter-graph" in scatter_ids


def test_scatter_graph_disables_scroll_zoom():
    graph = next(
        component
        for component in _components(viewer.layout)
        if getattr(component, "id", None) == "scatter-graph"
    )

    assert graph.config["scrollZoom"] is False


def test_create_scatter_figure_maps_all_xy_pairs_and_hover_data():
    index = pd.date_range("2024-01-01", periods=2, freq="min")
    frame = pd.DataFrame(
        {"X1": [1.0, 2.0], "X2": [10.0, 20.0], "Y1": [100.0, 200.0]},
        index=index,
    )

    figure = create_scatter_figure(frame, ["X1", "X2"], ["Y1"])

    assert isinstance(figure, go.Figure)
    assert len(figure.data) == 2
    assert list(figure.data[0].x) == [1.0, 2.0]
    assert list(figure.data[0].y) == [100.0, 200.0]
    assert list(figure.data[1].x) == [10.0, 20.0]
    assert list(figure.data[1].y) == [100.0, 200.0]
    assert "时间" in figure.data[0].hovertemplate
    assert list(figure.data[0].customdata) == [str(value) for value in index]


def test_create_scatter_figure_supports_three_by_three_matrix():
    frame = pd.DataFrame(
        {column: [1.0, 2.0] for column in ["X1", "X2", "X3", "Y1", "Y2", "Y3"]},
        index=pd.date_range("2024-01-01", periods=2, freq="min"),
    )

    figure = create_scatter_figure(
        frame,
        ["X1", "X2", "X3"],
        ["Y1", "Y2", "Y3"],
    )

    assert len(figure.data) == 9


def test_scatter_prepare_filters_invalid_rows_and_limits_points():
    frame = pd.DataFrame(
        {
            "X1": [1.0, np.nan, 3.0, np.inf],
            "Y1": [10.0, 20.0, 30.0, 40.0],
        },
        index=pd.date_range("2024-01-01", periods=4, freq="min"),
    )

    x_columns, y_columns, valid, display = prepare_scatter_frame(
        frame, ["X1"], ["Y1"], max_points=1
    )

    assert x_columns == ["X1"]
    assert y_columns == ["Y1"]
    assert len(valid) == 2
    assert len(display) == 1
    assert display.index[0] == frame.index[0]


@pytest.mark.parametrize(
    ("x_columns", "y_columns", "message"),
    [
        ([], ["Y1"], "请至少选择一个X变量"),
        (["X1"], [], "请至少选择一个Y变量"),
        (["X1", "X2", "X3", "X4"], ["Y1"], "最多选择3个"),
    ],
)
def test_scatter_selection_validation(x_columns, y_columns, message):
    frame = pd.DataFrame({column: [1.0] for column in ["X1", "X2", "X3", "X4", "Y1"]})

    with pytest.raises(ValueError, match=message):
        create_scatter_figure(frame, x_columns, y_columns)


def test_scatter_rejects_empty_numeric_data():
    frame = pd.DataFrame({"X1": ["bad"], "Y1": [None]})

    with pytest.raises(ValueError, match="无有效数据"):
        create_scatter_figure(frame, ["X1"], ["Y1"])


def test_render_scatter_view_uses_current_dataframe_and_reports_counts(monkeypatch):
    frame = pd.DataFrame(
        {
            "X1": [1.0, 2.0],
            "X2": [10.0, 20.0],
            "Y1": [100.0, 200.0],
            "Y2": [1000.0, 2000.0],
        },
        index=pd.date_range("2024-01-01", periods=2, freq="min"),
    )
    store_dataframe(frame)
    monkeypatch.setattr(viewer, "_triggered_id", lambda: "show-scatter-button")

    figure, status = viewer.render_scatter_view(
        {"ready": True}, 1, "X1", "X2", None, "Y1", "Y2", None
    )

    assert len(figure.data) == 4
    assert status == "实际绘图点数 2 / 2；X数量 2 × Y数量 2"


def test_render_scatter_view_reports_empty_selection_and_data(monkeypatch):
    monkeypatch.setattr(viewer, "_triggered_id", lambda: "show-scatter-button")
    store_dataframe(pd.DataFrame({"X1": [np.nan], "Y1": [np.inf]}))

    _, selection_status = viewer.render_scatter_view({"ready": True}, 1)
    _, data_status = viewer.render_scatter_view(
        {"ready": True}, 1, "X1", None, None, "Y1", None, None
    )

    assert selection_status == "请至少选择一个X变量"
    assert data_status == "无有效数据，无法生成散点矩阵"


def test_scatter_default_limit_reports_display_and_raw_points():
    frame = pd.DataFrame(
        {"X1": np.arange(50_000, dtype=float), "Y1": np.arange(50_000, dtype=float)},
        index=pd.date_range("2024-01-01", periods=50_000, freq="min"),
    )

    figure, status = viewer._render_scatter_frame(frame, ["X1"], ["Y1"])

    assert len(figure.data[0].x) == DEFAULT_MAX_SCATTER_POINTS == 5_000
    assert status.startswith("实际绘图点数 5000 / 50000")


def test_scatter_maximum_limit_caps_large_input():
    frame = pd.DataFrame(
        {"X1": np.arange(200_000, dtype=float), "Y1": np.arange(200_000, dtype=float)},
    )

    figure = create_scatter_figure(
        frame, ["X1"], ["Y1"], max_points=200_000
    )

    assert MAX_SCATTER_POINTS == 10_000
    assert len(figure.data[0].x) == MAX_SCATTER_POINTS
    assert figure.data[0].type == "scattergl"

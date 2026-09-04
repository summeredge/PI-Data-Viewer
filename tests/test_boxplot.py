import numpy as np
import pandas as pd
import plotly.graph_objects as go

from backend.dataframe_store import clear_dataframe, store_dataframe
from charts.boxplot import create_boxplot_figure
from pages import viewer


def _components(component):
    yield component
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        for child in children:
            yield from _components(child)
    elif children is not None:
        yield from _components(children)


def setup_function():
    clear_dataframe()


def teardown_function():
    clear_dataframe()


def test_boxplot_is_a_separate_tab_and_preserves_existing_tab_contents():
    tabs = viewer.layout.children[2].children[1].children[0]

    assert [tab.label for tab in tabs.children] == ["Trend", "XY Scatter", "Box Plot"]
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
    boxplot_ids = {
        component.id
        for component in _components(tabs.children[2])
        if hasattr(component, "id")
    }

    assert {"trend-graph", "statistics-cards"} <= trend_ids
    assert "scatter-graph" not in trend_ids
    assert "scatter-graph" in scatter_ids
    assert {"boxplot-graph", "boxplot-selected-columns"} <= boxplot_ids

    mode = next(
        component
        for component in _components(tabs.children[2])
        if getattr(component, "id", None) == "boxplot-axis-mode"
    )
    assert mode.value == "independent"
    assert [option["value"] for option in mode.options] == [
        "independent",
        "shared",
    ]


def test_create_boxplot_figure_returns_one_box_per_selected_numeric_column():
    frame = pd.DataFrame(
        {
            "PV1": [1.0, 2.0, 3.0, np.nan, "bad", np.inf],
            "PV2": [10, 20, 30, 40, None, -np.inf],
            "PV3": [100, 200, 300, 400, 500, 600],
            "UNSELECTED": [1, 2, 3, 4, 5, 6],
        }
    )

    figure = create_boxplot_figure(frame, ["PV1", "PV2", "PV3"])

    assert isinstance(figure, go.Figure)
    assert len(figure.data) == 3
    assert [trace.type for trace in figure.data] == ["box"] * 3
    assert [trace.name for trace in figure.data] == ["PV1", "PV2", "PV3"]
    assert all(trace.boxpoints == "outliers" for trace in figure.data)
    assert list(figure.data[0].y) == [1.0, 2.0, 3.0]


def test_boxplot_axis_modes_control_subplot_y_axes_and_keep_tag_labels_readable():
    frame = pd.DataFrame(
        {column: [1.0, 2.0, 3.0] for column in ["PV1", "PV2", "PV3"]}
    )

    independent = create_boxplot_figure(
        frame, ["PV1", "PV2", "PV3"], "independent"
    )
    shared = create_boxplot_figure(frame, ["PV1", "PV2", "PV3"], "shared")

    assert len(independent.data) == 3
    assert independent.layout.yaxis.matches is None
    assert independent.layout.yaxis2.matches is None
    assert independent.layout.yaxis3.matches is None
    assert independent.layout.xaxis.tickangle == -30
    assert independent.layout.xaxis.automargin is True
    assert independent.layout.margin.b == 110
    assert shared.layout.yaxis2.matches == "y"
    assert shared.layout.yaxis3.matches == "y"


def test_boxplot_figure_reports_missing_selection_and_empty_numeric_data():
    frame = pd.DataFrame({"PV1": ["bad", None, np.nan]})

    no_selection = create_boxplot_figure(frame, [])
    no_data = create_boxplot_figure(frame, ["PV1"])

    assert len(no_selection.data) == 0
    assert "选择一个变量" in no_selection.layout.annotations[0].text
    assert len(no_data.data) == 0
    assert "无有效数值数据" in no_data.layout.annotations[0].text


def test_render_boxplot_view_uses_shared_frame_and_selected_columns():
    frame = pd.DataFrame({"PV1": [1, 2], "PV2": [10, 20], "PV3": [100, 200]})
    store_dataframe(frame)

    figure, selected_text, status = viewer.render_boxplot_view(
        {"ready": True}, ["PV1", "PV3"], "shared"
    )

    assert [trace.name for trace in figure.data] == ["PV1", "PV3"]
    assert selected_text == "PV1, PV3"
    assert status == ""
    assert viewer.get_dataframe() is frame


def test_render_boxplot_view_prompts_for_selection_or_data():
    store_dataframe(pd.DataFrame({"PV1": [1, 2]}))
    _, selected_text, selection_status = viewer.render_boxplot_view(
        {"ready": True}, []
    )
    assert selected_text == "未选择变量"
    assert selection_status == "请至少选择一个变量"

    store_dataframe(pd.DataFrame({"PV1": ["bad", None]}))
    _, _, data_status = viewer.render_boxplot_view({"ready": True}, ["PV1"])
    assert data_status == "所选变量无有效数值数据"

    empty_frame = pd.DataFrame(columns=["PV1"])
    store_dataframe(empty_frame)
    figure, selected_text, empty_status = viewer.render_boxplot_view(
        {"ready": True}, ["PV1"]
    )
    assert len(figure.data) == 0
    assert selected_text == "PV1"
    assert empty_status == "暂无可用数据"

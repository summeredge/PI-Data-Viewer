import numpy as np
import pandas as pd
import plotly.graph_objects as go
from scipy import stats

from backend.dataframe_store import clear_dataframe, store_dataframe
from charts.probability import (
    CONSTANT_DATA_MESSAGE,
    INSUFFICIENT_DATA_MESSAGE,
    NO_SELECTION_MESSAGE,
    NO_VALID_DATA_MESSAGE,
    SINGLE_VARIABLE_MESSAGE,
    create_probability_plot_figure,
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


def setup_function():
    clear_dataframe()


def teardown_function():
    clear_dataframe()


def test_probability_plot_tab_reuses_the_shared_variable_selector():
    tabs = viewer.layout.children[2].children[1].children[0]

    assert [tab.label for tab in tabs.children] == [
        "Trend",
        "XY Scatter",
        "Box Plot",
        "Probability Plot",
        "Capability Analysis",
        "Control Chart",
    ]
    probability_tab = tabs.children[3]
    component_ids = {
        component.id
        for component in _components(probability_tab)
        if hasattr(component, "id")
    }
    assert {
        "probability-plot-graph",
        "probability-plot-selected-columns",
        "probability-plot-status",
    } <= component_ids
    assert "variable-selector" not in component_ids


def test_probability_plot_uses_scipy_quantiles_and_swapped_fit_line():
    frame = pd.DataFrame({"PV1": [1.0, 2.0, 3.0, 4.0, 5.0]})
    figure = create_probability_plot_figure(frame, ["PV1"])

    assert isinstance(figure, go.Figure)
    assert [trace.type for trace in figure.data] == ["scattergl", "scatter"]
    points, fit = figure.data
    (expected_quantiles, expected_values), (slope, intercept, _) = stats.probplot(
        frame["PV1"].to_numpy(), dist="norm"
    )
    np.testing.assert_allclose(points.x, expected_values)
    np.testing.assert_allclose(points.y, expected_quantiles)
    np.testing.assert_allclose(fit.y, (np.asarray(fit.x) - intercept) / slope)
    assert list(points.x) == sorted(points.x)
    assert figure.layout.yaxis.title.text == "Cumulative Probability (%)"
    assert "50%" in figure.layout.yaxis.ticktext
    assert "Value" in points.hovertemplate
    assert "Cumulative Probability (%)" in points.hovertemplate


def test_probability_plot_filters_non_numeric_values_without_mutating_frame():
    frame = pd.DataFrame({"PV1": ["bad", 2.0, np.nan, np.inf, -np.inf, 1.0, 3.0]})
    original = frame.copy(deep=True)

    figure = create_probability_plot_figure(frame, ["PV1"])

    points = figure.data[0]
    assert list(points.x) == [1.0, 2.0, 3.0]
    pd.testing.assert_frame_equal(frame, original)


def test_probability_plot_reports_invalid_selection_and_data():
    frame = pd.DataFrame({"PV1": [1.0, 2.0, 3.0], "PV2": [4.0, 5.0, 6.0]})

    cases = (
        ([], NO_SELECTION_MESSAGE),
        (["PV1", "PV2"], SINGLE_VARIABLE_MESSAGE),
        (["PV1"], ""),
    )
    for selected, message in cases[:2]:
        figure = create_probability_plot_figure(frame, selected)
        assert len(figure.data) == 0
        assert figure.layout.annotations[0].text == message

    assert (
        create_probability_plot_figure(pd.DataFrame({"PV1": ["bad", None]}), ["PV1"])
        .layout.annotations[0]
        .text
        == NO_VALID_DATA_MESSAGE
    )
    assert (
        create_probability_plot_figure(pd.DataFrame({"PV1": [1.0, 2.0]}), ["PV1"])
        .layout.annotations[0]
        .text
        == INSUFFICIENT_DATA_MESSAGE
    )
    assert (
        create_probability_plot_figure(pd.DataFrame({"PV1": [2.0, 2.0, 2.0]}), ["PV1"])
        .layout.annotations[0]
        .text
        == CONSTANT_DATA_MESSAGE
    )


def test_render_probability_plot_view_reads_the_shared_dataframe():
    frame = pd.DataFrame({"PV1": [1.0, 2.0, 3.0], "PV2": [4.0, 5.0, 6.0]})
    store_dataframe(frame)

    _, selected, status = viewer.render_probability_plot_view({"ready": True})
    assert selected == "未选择变量"
    assert status == "请至少选择一个变量"

    figure, selected, status = viewer.render_probability_plot_view(
        {"ready": True}, ["PV1"]
    )
    assert len(figure.data) == 2
    assert selected == "PV1"
    assert status == ""
    assert viewer.get_dataframe() is frame

    _, selected, status = viewer.render_probability_plot_view(
        {"ready": True}, ["PV1", "PV2"]
    )
    assert selected == "PV1, PV2"
    assert status == SINGLE_VARIABLE_MESSAGE


def test_probability_plot_callback_uses_shared_state_and_selector():
    from app import app

    callback = next(
        entry
        for entry in app.callback_map.values()
        if entry.get("callback")
        and entry["callback"].__name__ == "render_probability_plot_view"
    )

    assert [item["id"] for item in callback["inputs"]] == [
        "viewer-state",
        "variable-selector",
    ]

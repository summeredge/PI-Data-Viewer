import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

from backend.dataframe_store import clear_dataframe, store_dataframe
from backend.spc import calculate_imr, detect_special_causes
from charts.control_chart import (
    SINGLE_VARIABLE_MESSAGE,
    create_control_chart,
)
from pages import viewer


def setup_function():
    clear_dataframe()


def teardown_function():
    clear_dataframe()


def test_control_chart_tab_uses_the_shared_variable_selector():
    tabs = viewer.layout.children[2].children[1].children[0]

    assert [tab.label for tab in tabs.children] == [
        "Trend",
        "XY Scatter",
        "Box Plot",
        "Control Chart",
    ]
    control_tab = tabs.children[3]
    component_ids = {
        component.id
        for component in _components(control_tab)
        if hasattr(component, "id")
    }
    assert {
        "control-chart-graph",
        "control-chart-selected-columns",
        "control-chart-status",
        "control-chart-tests",
    } <= component_ids
    assert "variable-selector" not in component_ids
    test_selector = next(
        component
        for component in _components(control_tab)
        if getattr(component, "id", None) == "control-chart-tests"
    )
    assert test_selector.value == [1]
    assert [option["value"] for option in test_selector.options] == list(range(1, 9))


def test_calculate_imr_uses_moving_range_limits():
    series = pd.Series(
        [10, 11, 10, 12, 11],
        index=pd.date_range("2024-01-01", periods=5, freq="min"),
    )

    result = calculate_imr(series)
    expected_mr_bar = 5 / 4
    expected_sigma = expected_mr_bar / 1.128

    assert pd.isna(result["moving_range"].iloc[0])
    assert list(result["moving_range"].iloc[1:]) == [1.0, 1.0, 2.0, 1.0]
    assert result["individual_cl"] == pytest.approx(10.8)
    assert result["mr_cl"] == pytest.approx(expected_mr_bar)
    assert result["sigma"] == pytest.approx(expected_sigma)
    assert result["individual_ucl"] == pytest.approx(10.8 + 3 * expected_sigma)
    assert result["individual_lcl"] == pytest.approx(10.8 - 3 * expected_sigma)
    assert result["mr_ucl"] == pytest.approx(3.267 * expected_mr_bar)
    assert result["mr_lcl"] == 0
    assert result["selected_tests"] == (1,)


@pytest.mark.parametrize(
    ("test_number", "values"),
    [
        (1, [0, 0, 3.1]),
        (2, [1.0] * 9),
        (3, [1, 2, 3, 4, 5, 6]),
        (4, [0, 1] * 7),
        (5, [2.1, 0, 2.2]),
        (6, [1.1, 1.2, 0, 1.3, 1.4]),
        (7, [0.5] * 15),
        (8, [1.1, -1.1] * 4),
    ],
)
def test_minitab_special_cause_tests_flag_the_completing_point(
    test_number, values
):
    signals = detect_special_causes(
        pd.Series(values, dtype=float), 0, 1, tests=[test_number]
    )[test_number]

    assert signals.iloc[-1]
    assert signals.sum() == 1


def test_special_cause_runs_do_not_bridge_missing_values():
    signals = detect_special_causes(
        pd.Series([1.0] * 8 + [np.nan] + [1.0] * 8),
        0,
        1,
        tests=[2],
    )

    assert not signals[2].any()


def test_moving_range_chart_supports_only_minitab_tests_one_to_four():
    result = calculate_imr(
        pd.Series([0, 1] * 10, dtype=float), tests=range(1, 9)
    )

    assert set(result["individual_tests"]) == set(range(1, 9))
    assert set(result["moving_range_tests"]) == {1, 2, 3, 4}


def test_create_control_chart_contains_individual_and_moving_range_traces():
    index = pd.date_range("2024-01-01", periods=5, freq="min")
    frame = pd.DataFrame({"TAG001.PV": [10, 11, 10, 12, 11]}, index=index)

    figure = create_control_chart(frame, ["TAG001.PV"])

    assert isinstance(figure, go.Figure)
    assert [annotation.text for annotation in figure.layout.annotations] == [
        "Individual Chart",
        "Moving Range Chart",
    ]
    assert {trace.name for trace in figure.data} >= {
        "TAG001.PV",
        "CL",
        "UCL",
        "LCL",
        "Moving Range",
        "MR CL",
        "MR UCL",
        "MR LCL",
    }
    assert figure.layout.yaxis.title.text == "Value"
    assert figure.layout.yaxis2.title.text == "Moving Range"
    assert "%{x|%Y-%m-%d %H:%M:%S}" in figure.data[0].hovertemplate


def test_create_control_chart_marks_individual_and_mr_outliers_red():
    index = pd.date_range("2024-01-01", periods=5, freq="min")
    frame = pd.DataFrame({"TAG001.PV": [10, 11, 10, 12, 100]}, index=index)

    figure = create_control_chart(frame, ["TAG001.PV"])
    individual_outliers = next(trace for trace in figure.data if trace.name == "异常点")
    mr_outliers = next(trace for trace in figure.data if trace.name == "MR异常点")

    assert individual_outliers.marker.color == "#b42318"
    assert any(value == 100 for value in individual_outliers.y if np.isfinite(value))
    assert mr_outliers.marker.color == "#b42318"
    assert any(value == 88 for value in mr_outliers.y if np.isfinite(value))


def test_control_chart_labels_selected_minitab_test_signals():
    frame = pd.DataFrame(
        {"A": [0.0] * 10 + [10.0] * 9},
        index=pd.date_range("2024-01-01", periods=19, freq="min"),
    )

    figure = create_control_chart(frame, ["A"], tests=[2])
    signals = next(trace for trace in figure.data if trace.name == "异常点")

    assert signals.text[-1] == "2"
    assert signals.customdata[-1] == "Test 2"
    assert "%{customdata}" in signals.hovertemplate


def test_control_chart_allows_disabling_special_cause_tests():
    frame = pd.DataFrame(
        {"A": [0.0, 10.0]},
        index=pd.date_range("2024-01-01", periods=2, freq="min"),
    )

    figure = create_control_chart(frame, ["A"], tests=[])

    assert "异常点" not in {trace.name for trace in figure.data}
    assert "MR异常点" not in {trace.name for trace in figure.data}


def test_control_chart_callback_reads_the_test_selector():
    from app import app

    callback = next(
        entry
        for entry in app.callback_map.values()
        if entry.get("callback")
        and entry["callback"].__name__ == "render_control_chart_view"
    )

    assert [item["id"] for item in callback["inputs"]] == [
        "viewer-state",
        "variable-selector",
        "control-chart-tests",
    ]


def test_control_chart_requires_exactly_one_selected_variable():
    frame = pd.DataFrame(
        {"A": [1.0, 2.0], "B": [10.0, 20.0]},
        index=pd.date_range("2024-01-01", periods=2, freq="min"),
    )
    store_dataframe(frame)

    figure, selected, status = viewer.render_control_chart_view(
        {"ready": True}, ["A", "B"]
    )

    assert selected == "A, B"
    assert status == SINGLE_VARIABLE_MESSAGE
    assert any(
        annotation.text == SINGLE_VARIABLE_MESSAGE
        for annotation in figure.layout.annotations
    )


def test_control_chart_renders_from_the_shared_dataframe():
    frame = pd.DataFrame(
        {"A": [10.0, 11.0, 10.0], "B": [20.0, 21.0, 20.0]},
        index=pd.date_range("2024-01-01", periods=3, freq="min"),
    )
    store_dataframe(frame)

    figure, selected, status = viewer.render_control_chart_view(
        {"ready": True}, ["B"]
    )

    assert selected == "B"
    assert status == ""
    assert [trace.name for trace in figure.data if trace.name == "B"] == ["B"]
    assert viewer.get_dataframe() is frame


def test_control_chart_samples_display_points_after_full_calculation():
    frame = pd.DataFrame(
        {"A": np.arange(150, dtype=float)},
        index=pd.date_range("2024-01-01", periods=150, freq="min"),
    )

    figure = create_control_chart(frame, ["A"], max_points=100)
    value_trace = next(trace for trace in figure.data if trace.name == "A")
    moving_range_trace = next(
        trace for trace in figure.data if trace.name == "Moving Range"
    )

    assert len(value_trace.x) <= 100
    assert len(moving_range_trace.x) <= 100


def _components(component):
    yield component
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        for child in children:
            yield from _components(child)
    elif children is not None:
        yield from _components(children)

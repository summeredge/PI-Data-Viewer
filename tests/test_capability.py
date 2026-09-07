import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest
from scipy.stats import norm

from backend.capability import calculate_normal_capability
from backend.dataframe_store import clear_dataframe, store_dataframe
from backend.spc import calculate_imr
from charts.capability import (
    SINGLE_VARIABLE_MESSAGE,
    create_capability_figure,
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


def _text(component) -> str:
    values = []
    for item in _components(component):
        if isinstance(item, str):
            values.append(item)
    return " ".join(values)


def setup_function():
    clear_dataframe()


def teardown_function():
    clear_dataframe()


def test_capability_tab_has_required_controls_and_shared_selector_contract():
    tabs = viewer.layout.children[2].children[1].children[0]

    assert [tab.label for tab in tabs.children] == [
        "Trend",
        "XY Scatter",
        "Box Plot",
        "Probability Plot",
        "Capability Analysis",
        "Control Chart",
    ]
    capability_tab = tabs.children[4]
    component_ids = {
        component.id
        for component in _components(capability_tab)
        if hasattr(component, "id")
    }
    assert {
        "capability-lsl",
        "capability-usl",
        "capability-graph",
        "capability-summary",
        "capability-selected-columns",
        "capability-status",
    } <= component_ids
    assert "variable-selector" not in component_ids
    assert "稳定状态" in _text(capability_tab)


def test_calculate_normal_capability_uses_distinct_within_and_overall_sigma():
    series = pd.Series(
        [10, 11, 10, 12, 11],
        index=pd.date_range("2024-01-01", periods=5, freq="min"),
    )

    result = calculate_normal_capability(series, lsl=8, usl=14)

    assert result["sample_size"] == 5
    assert result["mean"] == pytest.approx(10.8)
    assert result["within_sigma"] == pytest.approx(1.25 / 1.128)
    assert result["overall_sigma"] == pytest.approx(0.8366600265)
    assert result["cp"] == pytest.approx(0.9024, rel=1e-3)
    assert result["cpk"] == pytest.approx(0.84224, rel=1e-3)
    assert result["pp"] == pytest.approx(1.1952286093)
    assert result["ppk"] == pytest.approx(1.1155467020)
    assert result["cpl"] < result["cpu"]
    assert result["ppl"] < result["ppu"]


@pytest.mark.parametrize(
    ("lsl", "usl", "primary", "secondary"),
    [
        (None, 10, "cpu", "ppu"),
        (12, None, "cpl", "ppl"),
    ],
)
def test_single_specification_uses_only_the_available_side(
    lsl, usl, primary, secondary
):
    result = calculate_normal_capability(pd.Series([10, 11, 10, 12, 11]), lsl, usl)

    assert result["cp"] is None
    assert result["pp"] is None
    assert result["cpl"] is None if lsl is None else result["cpu"] is None
    assert result["ppl"] is None if lsl is None else result["ppu"] is None
    assert result["cpk"] == result[primary]
    assert result["ppk"] == result[secondary]
    assert result["cpk"] < 0
    assert result["ppk"] < 0


@pytest.mark.parametrize(
    ("lsl", "usl"),
    [
        (None, None),
        (10, 10),
        (11, 10),
        (np.nan, 10),
        (10, np.inf),
        ("bad", 10),
    ],
)
def test_invalid_specifications_raise_clear_errors(lsl, usl):
    with pytest.raises(ValueError):
        calculate_normal_capability(pd.Series([1.0, 2.0, 3.0]), lsl, usl)


def test_missing_rows_do_not_create_a_cross_gap_moving_range():
    series = pd.Series([10, 11, np.nan, 20, 21])
    expected = calculate_imr(series, tests=[])

    result = calculate_normal_capability(series, lsl=8, usl=25)

    assert result["within_sigma"] == expected["sigma"]
    assert list(expected["moving_range"].dropna()) == [1.0, 1.0]
    assert result["values"].isna().tolist() == [False, False, True, False, False]


@pytest.mark.parametrize(
    "series",
    [
        pd.Series(["bad", np.nan, np.inf]),
        pd.Series([1.0, 2.0]),
        pd.Series([5.0, 5.0, 5.0]),
    ],
)
def test_invalid_data_is_rejected_without_nan_or_infinite_indices(series):
    with pytest.raises(ValueError):
        calculate_normal_capability(series, lsl=0, usl=10)


def test_capability_does_not_mutate_the_input_series():
    series = pd.Series([10, "bad", 11, 12, np.inf, 13])
    original = series.copy(deep=True)

    calculate_normal_capability(series, lsl=8, usl=14)

    pd.testing.assert_series_equal(series, original)


def test_capability_figure_has_density_histogram_distinct_curves_and_spec_lines():
    frame = pd.DataFrame({"PV1": [10, 11, 10, 12, 11]})
    result = calculate_normal_capability(frame["PV1"], lsl=8, usl=14)

    figure = create_capability_figure(frame, ["PV1"], result)

    assert isinstance(figure, go.Figure)
    assert [trace.type for trace in figure.data] == [
        "histogram",
        "scatter",
        "scatter",
        "scatter",
        "scatter",
    ]
    assert figure.data[0].histnorm == "probability density"
    assert {trace.name for trace in figure.data} == {
        "Histogram",
        "Within Normal Curve",
        "Overall Normal Curve",
        "LSL",
        "USL",
    }
    within = figure.data[1]
    overall = figure.data[2]
    np.testing.assert_allclose(
        within.y,
        norm.pdf(within.x, result["mean"], result["within_sigma"]),
    )
    np.testing.assert_allclose(
        overall.y,
        norm.pdf(overall.x, result["mean"], result["overall_sigma"]),
    )
    assert not np.allclose(within.y, overall.y)
    assert figure.layout.xaxis.range[0] < 8
    assert figure.layout.xaxis.range[1] > 14


def test_capability_figure_only_draws_present_single_specification_line():
    frame = pd.DataFrame({"PV1": [10, 11, 10, 12, 11]})
    result = calculate_normal_capability(frame["PV1"], usl=14)

    figure = create_capability_figure(frame, ["PV1"], result)

    assert {trace.name for trace in figure.data} == {
        "Histogram",
        "Within Normal Curve",
        "Overall Normal Curve",
        "USL",
    }


def test_render_capability_view_uses_shared_dataframe_and_returns_summary():
    frame = pd.DataFrame(
        {"PV1": [10, 11, 10, 12, 11], "PV2": [20, 21, 20, 22, 21]},
        index=pd.date_range("2024-01-01", periods=5, freq="min"),
    )
    store_dataframe(frame)

    figure, summary, selected, status = viewer.render_capability_view(
        {"ready": True}, ["PV1"], 8, 14
    )

    assert viewer.get_dataframe() is frame
    assert selected == "PV1"
    assert status == ""
    assert [trace.name for trace in figure.data[:3]] == [
        "Histogram",
        "Within Normal Curve",
        "Overall Normal Curve",
    ]
    summary_text = _text(summary)
    assert "Process Data" in summary_text
    assert "StDev (Within)" in summary_text
    assert "Potential Capability" in summary_text
    assert "Overall Capability" in summary_text


def test_render_capability_view_reports_selection_and_data_errors():
    store_dataframe(pd.DataFrame({"PV1": [1.0, 2.0, 3.0], "PV2": [4.0, 5.0, 6.0]}))

    _, _, selected, status = viewer.render_capability_view({"ready": True}, [])
    assert selected == "未选择变量"
    assert status == "请至少选择一个变量"

    _, _, selected, status = viewer.render_capability_view(
        {"ready": True}, ["PV1", "PV2"]
    )
    assert selected == "PV1, PV2"
    assert status == SINGLE_VARIABLE_MESSAGE

    _, _, _, status = viewer.render_capability_view(
        {"ready": True}, ["PV1"], None, None
    )
    assert status == "LSL 和 USL 不能同时为空"

    store_dataframe(pd.DataFrame({"PV1": ["bad", np.nan, np.inf]}))
    _, _, _, status = viewer.render_capability_view({"ready": True}, ["PV1"], 0, 10)
    assert "有效数值" in status


def test_capability_callback_uses_shared_selector_and_specification_inputs():
    from app import app

    callback = next(
        entry
        for entry in app.callback_map.values()
        if entry.get("callback")
        and entry["callback"].__name__ == "render_capability_view"
    )

    assert [item["id"] for item in callback["inputs"]] == [
        "viewer-state",
        "variable-selector",
        "capability-lsl",
        "capability-usl",
    ]

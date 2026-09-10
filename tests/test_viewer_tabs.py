import pytest
from dash.exceptions import PreventUpdate

from pages import viewer


@pytest.mark.parametrize(
    ("renderer", "args", "tab"),
    [
        (viewer.render_boxplot_view, ({"ready": True}, []), "boxplot-tab"),
        (
            viewer.render_probability_plot_view,
            ({"ready": True}, []),
            "probability-plot-tab",
        ),
        (
            viewer.render_capability_view,
            ({"ready": True}, [], None, None),
            "capability-tab",
        ),
        (
            viewer.render_control_chart_view,
            ({"ready": True}, [], None),
            "control-chart-tab",
        ),
        (
            viewer.render_frequency_view,
            ({"ready": True}, []),
            "frequency-analysis-tab",
        ),
    ],
)
def test_inactive_chart_tabs_skip_rendering(renderer, args, tab):
    with pytest.raises(PreventUpdate):
        renderer(*args, tab_value="trend-tab")


@pytest.mark.parametrize(
    ("renderer", "args", "selected_index", "status_index", "summary_index"),
    [
        (viewer.render_boxplot_view, ({"ready": True}, ["OLD"], "independent"), 1, 2, None),
        (
            viewer.render_probability_plot_view,
            ({"ready": True}, ["OLD"]),
            1,
            2,
            None,
        ),
        (
            viewer.render_capability_view,
            ({"ready": True}, ["OLD"], None, None),
            2,
            3,
            1,
        ),
        (
            viewer.render_control_chart_view,
            ({"ready": True}, ["OLD"], None),
            1,
            2,
            None,
        ),
        (
            viewer.render_frequency_view,
            ({"ready": True}, ["OLD"]),
            2,
            3,
            1,
        ),
    ],
)
def test_viewer_state_clears_inactive_analysis_tabs(
    monkeypatch, renderer, args, selected_index, status_index, summary_index
):
    monkeypatch.setattr(viewer, "_triggered_id", lambda: "viewer-state")

    result = renderer(
        {"ready": True, "status": "请至少选择一个变量"},
        *args[1:],
        tab_value="trend-tab",
    )

    assert len(result[0].data) == 0
    assert result[selected_index] == "未选择变量"
    assert result[status_index] == "请至少选择一个变量"
    if summary_index is not None:
        assert result[summary_index].children is None


def test_triggered_id_is_safe_outside_dash_callback():
    assert viewer._triggered_id() is None

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


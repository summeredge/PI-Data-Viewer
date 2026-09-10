import numpy as np
import pandas as pd

from backend.dataframe_store import clear_dataframe, get_dataframe, store_dataframe
from pages import viewer


def setup_function():
    clear_dataframe()


def teardown_function():
    clear_dataframe()


def _frames():
    index = pd.date_range("2026-01-01", periods=16, freq="min")
    points = np.arange(16, dtype=float)
    return (
        pd.DataFrame({"PI_A": points, "PI_B": points + 1}, index=index),
        pd.DataFrame({"FILE_A": points + 100, "FILE_B": points + 101}, index=index),
    )


def _render_existing_views(monkeypatch, first_column, second_column):
    state = {"ready": True, "status": ""}
    monkeypatch.setattr(viewer, "_triggered_id", lambda: "show-results")
    return [
        viewer.render_trend_view(state, 1, [first_column, second_column]),
        viewer.render_scatter_view(
            state, 1, first_column, None, None, second_column, None, None
        ),
        viewer.render_boxplot_view(
            state, [first_column, second_column], "independent", "boxplot-tab"
        ),
        viewer.render_probability_plot_view(state, [first_column], "probability-plot-tab"),
        viewer.render_capability_view(state, [first_column], 0, 200, "capability-tab"),
        viewer.render_control_chart_view(state, [first_column], None, "control-chart-tab"),
        viewer.render_frequency_view(state, [first_column], "frequency-analysis-tab"),
    ]


def _render_invalidated_views(monkeypatch, state):
    monkeypatch.setattr(viewer, "_triggered_id", lambda: "viewer-state")
    return [
        viewer.render_trend_view(state, 1, ["PI_A", "PI_B"]),
        viewer.render_scatter_view(state, 1, "PI_A", None, None, "PI_B", None, None),
        viewer.render_boxplot_view(state, ["PI_A"], "independent", "trend-tab"),
        viewer.render_probability_plot_view(state, ["PI_A"], "trend-tab"),
        viewer.render_capability_view(state, ["PI_A"], 0, 20, "trend-tab"),
        viewer.render_control_chart_view(state, ["PI_A"], None, "trend-tab"),
        viewer.render_frequency_view(state, ["PI_A"], "trend-tab"),
    ]


def _assert_views_are_invalidated(results):
    assert all(len(result[0].data) == 0 for result in results)
    assert results[0][1] == []
    assert results[1][1] == ""
    assert results[2][1] == "未选择变量"
    assert results[3][1] == "未选择变量"
    assert results[4][1].children is None
    assert results[5][1] == "未选择变量"
    assert results[6][1].children is None


def test_pi_to_file_replaces_shared_frame_and_invalidates_all_views(monkeypatch):
    pi_frame, file_frame = _frames()
    store_dataframe(pi_frame)
    old_results = _render_existing_views(monkeypatch, "PI_A", "PI_B")
    assert all(result[0].data for result in old_results)

    store_dataframe(file_frame)
    monkeypatch.setattr(viewer, "_triggered_id", lambda: "upload-result")
    state, selected = viewer.update_data_state(
        1,
        {"ok": True},
        0,
        "file",
        "PI_A",
        "2026-01-01",
        "2026-01-01 00:15",
    )

    assert selected == []
    assert [option["value"] for option in state["options"]] == ["FILE_A", "FILE_B"]
    assert get_dataframe() is file_frame
    assert "revision" in state
    assert "data_revision" not in state
    _assert_views_are_invalidated(_render_invalidated_views(monkeypatch, state))


def test_file_to_pi_replaces_shared_frame_and_invalidates_all_views(monkeypatch):
    pi_frame, file_frame = _frames()
    store_dataframe(file_frame)
    old_results = _render_existing_views(monkeypatch, "FILE_A", "FILE_B")
    assert all(result[0].data for result in old_results)

    monkeypatch.setattr(viewer, "read_pi_data", lambda *args: pi_frame)
    monkeypatch.setattr(viewer, "_triggered_id", lambda: "query-button")
    state, selected = viewer.update_data_state(
        1,
        None,
        0,
        "pi",
        "PI_A",
        "2026-01-01",
        "2026-01-01 00:15",
    )

    assert selected == []
    assert [option["value"] for option in state["options"]] == ["PI_A", "PI_B"]
    assert get_dataframe() is pi_frame
    assert "revision" in state
    assert "data_revision" not in state
    _assert_views_are_invalidated(_render_invalidated_views(monkeypatch, state))

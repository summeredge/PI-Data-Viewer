import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

from backend.dataframe_store import clear_dataframe, store_dataframe
from backend.spc import (
    bound_stages,
    calculate_imr,
    calculate_staged_imr,
    detect_special_causes,
)
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
        "趋势图",
        "散点矩阵",
        "箱线图",
        "控制图",
        "概率图",
        "能力分析",
        "频谱分析",
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
        "单值图",
        "移动极差图",
    ]
    assert {trace.name for trace in figure.data} >= {
        "TAG001.PV",
        "中心线（CL）",
        "上控制限（UCL）",
        "下控制限（LCL）",
        "移动极差",
        "移动极差中心线（MR CL）",
        "移动极差上控制限（MR UCL）",
        "移动极差下控制限（MR LCL）",
    }
    assert figure.layout.yaxis.title.text == "数值"
    assert figure.layout.yaxis2.title.text == "移动极差"
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
    assert signals.customdata[-1] == "检验 2"
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
        "viewer-tabs",
        "control-chart-applied-stages",
        "control-chart-stage-labels",
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
        trace for trace in figure.data if trace.name == "移动极差"
    )

    assert len(value_trace.x) <= 100
    assert len(moving_range_trace.x) <= 100


def test_bound_stages_sorts_and_deduplicates_boundaries():
    index = pd.date_range("2024-01-01", periods=10, freq="min")

    stamps = bound_stages(
        index,
        ["2024-01-01 00:06:00", "2024-01-01T00:03:00", "2024-01-01 00:06:00"],
    )

    assert [stamp.strftime("%H:%M") for stamp in stamps] == ["00:03", "00:06"]


@pytest.mark.parametrize(
    "boundary",
    ["2024-01-01 00:00:00", "2024-01-01 00:09:00", "2023-12-31 23:00:00"],
)
def test_bound_stages_rejects_boundaries_outside_the_data_range(boundary):
    index = pd.date_range("2024-01-01", periods=10, freq="min")

    with pytest.raises(ValueError, match="分界时间"):
        bound_stages(index, [boundary])


def test_calculate_staged_imr_restarts_mr_and_limits_per_stage():
    index = pd.date_range("2024-01-01", periods=10, freq="min")
    series = pd.Series(np.arange(10, dtype=float), index=index)

    stages = calculate_staged_imr(series, ["2024-01-01 00:05:00"])

    assert [len(stage["values"]) for stage in stages] == [5, 5]
    assert pd.isna(stages[1]["moving_range"].iloc[0])
    assert stages[0]["individual_cl"] == pytest.approx(2.0)
    assert stages[1]["individual_cl"] == pytest.approx(7.0)
    assert list(stages[1]["moving_range"].dropna()) == [1.0] * 4


def test_calculate_staged_imr_resets_runs_at_the_stage_boundary():
    index = pd.date_range("2024-01-01", periods=18, freq="min")
    # 两侧各 9 点位于中心线同一侧：单段命中检验 2，分阶段后各段都不足 9 点。
    series = pd.Series([0.0] * 9 + [10.0] * 9, index=index)

    whole = calculate_imr(series, tests=[2])
    stages = calculate_staged_imr(series, ["2024-01-01 00:09:00"], tests=[2])

    assert whole["individual_signals"].any()
    assert not any(stage["individual_signals"].any() for stage in stages)


def test_calculate_staged_imr_rejects_a_stage_without_a_moving_range():
    index = pd.date_range("2024-01-01", periods=3, freq="min")
    series = pd.Series(np.arange(3, dtype=float), index=index)

    # 第二阶段只有 1 个样本，算不出 MR，应该直接报错而不是输出误导性控制限。
    with pytest.raises(ValueError, match="请调整分界时间"):
        calculate_staged_imr(series, ["2024-01-01 00:01:30"])


def test_staged_control_chart_draws_boundaries_and_per_stage_limits():
    index = pd.date_range("2024-01-01", periods=12, freq="min")
    frame = pd.DataFrame({"A": np.arange(12, dtype=float)}, index=index)

    figure = create_control_chart(
        frame, ["A"], boundaries=["2024-01-01 00:04:00", "2024-01-01 00:08:00"]
    )
    center = next(trace for trace in figure.data if trace.name == "中心线（CL）")

    assert [
        annotation.text
        for annotation in figure.layout.annotations
        if annotation.text.startswith("阶段")
    ] == ["阶段 1", "阶段 2", "阶段 3"]
    assert [value for value in center.y if value is not None] == [
        1.5,
        1.5,
        5.5,
        5.5,
        9.5,
        9.5,
    ]
    assert list(center.x).count(None) == 3
    assert len(figure.layout.shapes) == 4  # 2 个分界 × 单值图 / 移动极差图


def test_staged_control_chart_hidden_labels_keep_the_same_limits():
    index = pd.date_range("2024-01-01", periods=12, freq="min")
    frame = pd.DataFrame({"A": np.arange(12, dtype=float)}, index=index)

    hidden = create_control_chart(
        frame, ["A"], boundaries=["2024-01-01 00:04:00"], limit_labels=False
    )
    shown = create_control_chart(
        frame, ["A"], boundaries=["2024-01-01 00:04:00"], limit_labels=True
    )

    assert "中心线（CL）标签" not in {trace.name for trace in hidden.data}
    shown_label = next(
        trace for trace in shown.data if trace.name == "中心线（CL）标签"
    )
    hidden_center = next(
        trace for trace in hidden.data if trace.name == "中心线（CL）"
    )
    assert list(shown_label.y) == [1.5, 7.5]
    assert list(hidden_center.y) == [1.5, 1.5, None, 7.5, 7.5, None]


def test_stage_pending_list_sorts_deduplicates_and_ignores_blank():
    pending = viewer._stage_sort(
        ["2024-01-01T00:08", "2024-01-01T00:02:00", "2024-01-01T00:08:00", ""]
    )

    assert pending == ["2024-01-01T00:02:00", "2024-01-01T00:08:00"]


def test_stage_pending_summary_counts_boundaries_and_stages():
    assert viewer._stage_summary([]) == "未启用阶段"
    assert viewer._stage_summary(["a", "b", "c"]) == "3 个分界时间（4 个阶段）"


def test_clicked_point_time_handles_plotly_formats():
    # Plotly 日期轴 clickData 给毫秒时间戳，也可能只给 pointNumber。
    assert (
        viewer._clicked_stage_time({"points": [{"x": 1704067620000.0}]})
        == "2024-01-01T00:07:00"
    )
    assert (
        viewer._clicked_stage_time({"points": [{"x": "2024-01-01 00:07:00"}]})
        == "2024-01-01T00:07:00"
    )
    assert (
        viewer._clicked_stage_time(
            {
                "points": [
                    {
                        "pointNumber": 1,
                        "data": {"x": ["2024-01-01 00:01:00", "2024-01-01 00:07:00"]},
                    }
                ]
            }
        )
        == "2024-01-01T00:07:00"
    )
    assert viewer._clicked_stage_time({"points": [{"pointNumber": 9}]}) == ""
    assert viewer._clicked_stage_time(None) == ""


def test_clicking_a_chart_point_fills_the_time_input(monkeypatch):
    monkeypatch.setattr(
        viewer, "callback_context", type("Ctx", (), {"triggered_id": "control-chart-graph"})
    )
    click = {"points": [{"x": "2024-01-01 00:07:00", "y": 3.0}]}

    pending, value, note = viewer.edit_control_chart_stages(
        1, 0, [], [], 0, click, None, ["2024-01-01T00:04:00"]
    )

    # 点图只回填输入框，列表要等“添加”才变。
    assert pending is viewer.no_update
    assert value == "2024-01-01T00:07:00"
    assert "添加" in note


def test_clicking_the_chart_opens_the_stage_panel(monkeypatch):
    monkeypatch.setattr(
        viewer,
        "callback_context",
        type(
            "Ctx",
            (),
            {
                "triggered_id": "control-chart-graph",
                "triggered": [{"prop_id": "control-chart-graph.clickData"}],
            },
        ),
    )
    click = {"points": [{"x": "2024-01-01 00:07:00"}]}

    shown, style, expanded = viewer.toggle_control_chart_stage_panel(0, click, False)

    assert shown is True
    assert style["display"] == "flex"
    assert expanded == "true"


def test_clicking_an_existing_boundary_point_is_rejected(monkeypatch):
    monkeypatch.setattr(
        viewer, "callback_context", type("Ctx", (), {"triggered_id": "control-chart-graph"})
    )
    click = {"points": [{"x": "2024-01-01 00:07:00"}]}

    pending, value, note = viewer.edit_control_chart_stages(
        1, 0, [], [], 0, click, None, ["2024-01-01T00:07:00"]
    )

    assert pending is viewer.no_update
    assert value is viewer.no_update
    assert "已是分界时间" in note


def test_recalculate_is_only_enabled_while_pending_differs_from_applied(monkeypatch):
    monkeypatch.setattr(viewer, "_triggered_id", lambda: "control-chart-stage-time")

    applied, message, disabled = viewer.recalculate_control_chart_stages(
        0, {"ready": True}, ["2024-01-01T00:04:00"], []
    )
    assert applied is viewer.no_update
    assert message == viewer._STAGE_HINT
    assert disabled is False

    same = viewer.recalculate_control_chart_stages(
        0,
        {"ready": True},
        ["2024-01-01T00:04:00"],
        ["2024-01-01T00:04:00"],
    )
    assert same == (viewer.no_update, "", True)


def test_recalculate_applies_pending_only_after_a_valid_click(monkeypatch):
    index = pd.date_range("2024-01-01", periods=12, freq="min")
    store_dataframe(pd.DataFrame({"A": np.arange(12, dtype=float)}, index=index))
    monkeypatch.setattr(viewer, "_triggered_id", lambda: "control-chart-recalculate")

    applied, _, disabled = viewer.recalculate_control_chart_stages(
        1, {"ready": True}, ["2024-01-01T00:04:00"], [], ["A"], [1]
    )
    assert applied == ["2024-01-01T00:04:00"]
    assert disabled is True

    rejected, message, disabled = viewer.recalculate_control_chart_stages(
        1, {"ready": True}, ["2024-01-01T00:11:00"], [], ["A"], [1]
    )
    assert rejected is viewer.no_update
    assert message.startswith("阶段设置无效：")
    assert disabled is False


def test_recalculate_clears_applied_stages_when_pending_is_empty(monkeypatch):
    index = pd.date_range("2024-01-01", periods=12, freq="min")
    store_dataframe(pd.DataFrame({"A": np.arange(12, dtype=float)}, index=index))
    monkeypatch.setattr(viewer, "_triggered_id", lambda: "control-chart-recalculate")

    applied, message, disabled = viewer.recalculate_control_chart_stages(
        1, {"ready": True}, [], ["2024-01-01T00:04:00"], ["A"], [1]
    )

    assert applied == []
    assert "整体" in message
    assert disabled is True


def test_viewer_state_change_resets_both_stage_states(monkeypatch):
    monkeypatch.setattr(viewer, "_triggered_id", lambda: "viewer-state")

    assert viewer.recalculate_control_chart_stages(3, {}, ["x"], ["y"]) == (
        [],
        "",
        True,
    )


def test_control_chart_view_uses_only_the_applied_boundaries(monkeypatch):
    index = pd.date_range("2024-01-01", periods=12, freq="min")
    store_dataframe(pd.DataFrame({"A": np.arange(12, dtype=float)}, index=index))
    monkeypatch.setattr(viewer, "_triggered_id", lambda: "control-chart-applied-stages")

    figure, _, status = viewer.render_control_chart_view(
        {"ready": True},
        ["A"],
        [1],
        "control-chart-tab",
        ["2024-01-01T00:04:00"],
        ["show"],
    )

    assert status == ""
    assert {
        annotation.text
        for annotation in figure.layout.annotations
        if annotation.text.startswith("阶段")
    } == {"阶段 1", "阶段 2"}


def test_toggle_stage_panel_opens_and_closes():
    shown, style, expanded = viewer.toggle_control_chart_stage_panel(1, None, False)
    assert shown is True and style["display"] == "flex" and expanded == "true"

    shown, style, expanded = viewer.toggle_control_chart_stage_panel(2, None, True)
    assert shown is False and style["display"] == "none" and expanded == "false"


def test_stage_rows_follow_the_pending_list_order():
    rows = viewer.update_control_chart_stage_panel(
        ["2024-01-01T00:08", "2024-01-01T00:02"]
    )
    values = [row.children[0].value for row in rows]

    assert values == ["2024-01-01T00:02:00", "2024-01-01T00:08:00"]


def test_stage_edit_callback_deletes_and_clears_pending_only(monkeypatch):
    monkeypatch.setattr(
        viewer,
        "callback_context",
        type("Ctx", (), {"triggered_id": {"type": "control-chart-delete-stage", "index": 0}}),
    )
    deleted = viewer.edit_control_chart_stages(
        1, 0, [1], [], 0, None, None, ["2024-01-01T00:04:00", "2024-01-01T00:08:00"]
    )
    assert deleted[:2] == (["2024-01-01T00:08:00"], viewer.no_update)

    monkeypatch.setattr(
        viewer, "callback_context", type("Ctx", (), {"triggered_id": "control-chart-clear-stages"})
    )
    cleared = viewer.edit_control_chart_stages(
        1, 0, [], [], 1, None, None, ["2024-01-01T00:04:00"]
    )
    assert cleared[0] == []


def test_stage_panel_is_collapsed_by_default():
    control_tab = viewer.layout.children[2].children[1].children[0].children[3]
    components = {
        getattr(component, "id", None): component for component in _components(control_tab)
    }
    panel = components["control-chart-stage-panel"]
    toggle = components["control-chart-stage-toggle"]

    assert panel.style["display"] == "none"
    assert toggle.to_plotly_json()["props"]["aria-expanded"] == "false"
    assert components["control-chart-recalculate"].disabled is True


def _components(component):
    yield component
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        for child in children:
            yield from _components(child)
    elif children is not None:
        yield from _components(children)

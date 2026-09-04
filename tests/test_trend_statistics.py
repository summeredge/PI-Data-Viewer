import numpy as np
import pandas as pd
import pytest

from backend.statistics import calculate_series_summary, calculate_statistics
from charts.trend import create_distribution_figure, create_trend_figure
from pages import viewer


def test_create_trend_figure_preserves_datetime_index_and_multiple_tags():
    index = pd.DatetimeIndex(
        ["2024-01-01 00:00:00", "2024-01-01 00:01:00"], name="Timestamp"
    )
    frame = pd.DataFrame({"TAG_A": [1.0, 2.0], "TAG_B": [10.0, 20.0]}, index=index)

    figure = create_trend_figure(frame)

    assert [trace.name for trace in figure.data] == ["TAG_A", "TAG_B"]
    assert all(list(trace.x) == list(index) for trace in figure.data)
    assert figure.layout.xaxis.rangeslider.visible is False
    assert figure.layout.xaxis.minallowed == index[0]
    assert figure.layout.xaxis.maxallowed == index[-1]
    assert figure.layout.yaxis.fixedrange is True
    assert figure.layout.legend.orientation == "h"
    assert figure.layout.legend.x == 0
    assert figure.layout.legend.xanchor == "left"
    assert figure.layout.legend.y == -0.18
    assert figure.layout.legend.yanchor == "top"
    assert figure.layout.margin.b == 90


def test_create_trend_figure_only_draws_selected_columns():
    frame = pd.DataFrame(
        {"A": [1.0, 2.0], "B": [10.0, 20.0], "C": [100.0, 200.0]},
        index=pd.date_range("2024-01-01", periods=2, freq="min"),
    )

    figure = create_trend_figure(frame, ["A", "C"])

    assert [trace.name for trace in figure.data] == ["A", "C"]
    assert list(frame.columns) == ["A", "B", "C"]


def test_create_trend_figure_supports_independent_y_axes():
    frame = pd.DataFrame(
        {"A": [1.0, 2.0], "B": [10.0, 20.0], "C": [100.0, 200.0]},
        index=pd.date_range("2024-01-01", periods=2, freq="min"),
    )

    figure = create_trend_figure(frame, axis_mode="independent")

    assert [trace.yaxis for trace in figure.data] == [None, "y2", "y3"]
    assert figure.layout.yaxis2.overlaying == "y"
    assert figure.layout.yaxis2.side == "right"
    assert figure.layout.yaxis3.showticklabels is False
    assert figure.layout.yaxis3.fixedrange is True


def test_calculate_statistics_contains_required_values_without_changing_frame():
    frame = pd.DataFrame(
        {"TAG_A": [1.0, 2.0, 3.0], "TAG_B": [10.0, 20.0, 30.0]},
        index=pd.date_range("2024-01-01", periods=3, freq="min"),
    )
    original = frame.copy(deep=True)

    statistics = calculate_statistics(frame)

    assert list(statistics.columns) == ["count", "mean", "std", "min", "max"]
    assert statistics.loc["TAG_A", "count"] == 3
    assert statistics.loc["TAG_A", "mean"] == 2.0
    assert statistics.loc["TAG_A", "std"] == 1.0
    assert statistics.loc["TAG_A", "min"] == 1.0
    assert statistics.loc["TAG_A", "max"] == 3.0
    pd.testing.assert_frame_equal(frame, original)


def test_calculate_series_summary_matches_dataproject_trend_stats():
    series = pd.Series([1.0, 2.0, 3.0, np.nan, np.inf, -np.inf])

    summary = calculate_series_summary(series)

    assert summary["count"] == 3
    assert summary["ratio"] == pytest.approx(0.5)
    assert summary["mean"] == 2.0
    assert summary["std"] == pytest.approx(np.sqrt(2 / 3))
    assert summary["min"] == 1.0
    assert summary["max"] == 3.0
    assert summary["range"] == 2.0
    assert summary["median"] == 2.0


def test_distribution_figure_handles_empty_constant_and_curve_cases():
    empty = create_distribution_figure([], "#176b87")
    constant = create_distribution_figure([2.0, 2.0], "#176b87")
    varied = create_distribution_figure([1.0, 2.0, 3.0, 4.0], "#176b87")

    assert len(empty.data) == 0
    assert empty.layout.annotations[0].text == "无有效数据"
    assert [trace.type for trace in constant.data] == ["bar"]
    assert [trace.type for trace in varied.data] == ["bar", "scatter"]
    assert varied.data[1].line.color == "#176b87"


def test_parse_tags_rejects_more_than_eight_tags():
    with pytest.raises(ValueError, match="Tag数量不能超过8个"):
        viewer.parse_tags("\n".join(f"TAG_{index}" for index in range(9)))


def test_update_viewer_stores_read_data_and_builds_statistics(monkeypatch):
    frame = pd.DataFrame(
        {"TAG_A": [1.0, 2.0]},
        index=pd.date_range("2024-01-01", periods=2, freq="min"),
    )
    monkeypatch.setattr(viewer, "read_pi_data", lambda *args: frame)

    figure, records, status = viewer.update_viewer(
        1,
        "TAG_A",
        "2024-01-01 00:00:00",
        "2024-01-01 00:02:00",
    )

    assert len(figure.data) == 1
    assert records[0]["Tag"] == "TAG_A"
    assert records[0]["count"] == 2
    assert records[0]["mean"] == 1.5
    assert records[0]["std"] == pytest.approx(0.7071067811865476)
    assert records[0]["min"] == 1.0
    assert records[0]["max"] == 2.0
    assert status == ""
    assert viewer.get_dataframe() is frame


def test_variable_options_default_to_all_and_limit_display_to_eight():
    frame = pd.DataFrame(
        {f"TAG_{index}": [float(index)] for index in range(9)},
        index=pd.date_range("2024-01-01", periods=1, freq="min"),
    )

    options, selected, status = viewer._variable_selection_state(frame)

    assert [option["value"] for option in options] == list(frame.columns)
    assert selected == list(frame.columns[:8])
    assert "最多选择8个变量" in status
    limited_options = viewer.update_variable_options(
        {"options": options}, selected
    )
    assert limited_options[8]["disabled"] is True


def test_selected_view_updates_trend_and_statistics_without_reading_again():
    frame = pd.DataFrame(
        {"A": [1.0, 2.0], "B": [10.0, 20.0], "C": [100.0, 200.0]},
        index=pd.date_range("2024-01-01", periods=2, freq="min"),
    )
    viewer.store_dataframe(frame)

    figure, records, status = viewer.update_selected_view(["A", "C"])

    assert [trace.name for trace in figure.data] == ["A", "C"]
    assert [record["Tag"] for record in records] == ["A", "C"]
    assert status == ""


def test_render_viewer_waits_for_explicit_show_click_and_limits_points(monkeypatch):
    frame = pd.DataFrame(
        {"A": range(150), "B": range(150, 300)},
        index=pd.date_range("2024-01-01", periods=150, freq="min"),
    )
    viewer.store_dataframe(frame)
    state = {"ready": True, "status": ""}

    monkeypatch.setattr(viewer, "_triggered_id", lambda: "viewer-state")
    empty_figure, empty_cards, status = viewer.render_trend_view(
        state, 0, ["A", "B"], "shared", "2024-01-01T00:10", "2024-01-01T02:29", 100
    )

    assert len(empty_figure.data) == 0
    assert empty_cards == []
    assert status == ""

    monkeypatch.setattr(viewer, "_triggered_id", lambda: "show-trend-button")
    figure, cards, status = viewer.render_trend_view(
        state, 1, ["A", "B"], "independent", "2024-01-01T00:10", "2024-01-01T02:29", 100
    )

    assert len(figure.data) == 2
    assert len(figure.data[0].x) == 100
    assert figure.data[0].x[0] == frame.index[10]
    assert figure.data[0].x[-1] == frame.index[-1]
    assert len(cards) == 2
    assert "原始 140 点，显示 100 点" in status


def test_render_trend_uses_full_filtered_frame_for_statistics():
    frame = pd.DataFrame(
        {"A": np.arange(150, dtype=float) ** 2},
        index=pd.date_range("2024-01-01", periods=150, freq="min"),
    )

    figure, records, cards, _ = viewer._render_trend_frame(
        frame, ["A"], max_points=100
    )

    expected = calculate_series_summary(frame["A"])
    assert len(figure.data[0].x) == 100
    assert records[0]["count"] == expected["count"] == 150
    assert records[0]["mean"] == expected["mean"]
    assert records[0]["std"] == pytest.approx(np.std(frame["A"], ddof=1))
    assert records[0]["min"] == expected["min"]
    assert records[0]["max"] == expected["max"]
    rows = {
        row.children[0].children: row.children[1].children
        for row in cards[0].children[1].children
    }
    assert rows["极差"] == viewer._format_stat_value(expected["range"])
    assert rows["中位数"] == viewer._format_stat_value(expected["median"])
    assert rows["有效点数/占比"] == "150 / 100.0%"


def test_render_trend_statistics_use_filtered_full_frame_not_original_frame():
    frame = pd.DataFrame(
        {"A": np.arange(200, dtype=float) ** 2},
        index=pd.date_range("2024-01-01", periods=200, freq="min"),
    )

    figure, records, cards, _ = viewer._render_trend_frame(
        frame,
        ["A"],
        start_time="2024-01-01T00:30:00",
        end_time="2024-01-01T02:49:00",
        max_points=100,
    )

    filtered = frame.iloc[30:170]
    expected = calculate_series_summary(filtered["A"])
    assert len(figure.data[0].x) == 100
    assert records[0]["count"] == expected["count"] == 140
    assert records[0]["mean"] == expected["mean"]
    rows = {
        row.children[0].children: row.children[1].children
        for row in cards[0].children[1].children
    }
    assert rows["有效点数/占比"] == "140 / 100.0%"
    assert rows["最小值"] == viewer._format_stat_value(expected["min"])
    assert rows["最大值"] == viewer._format_stat_value(expected["max"])


def test_trend_time_controls_follow_loaded_frame():
    frame = pd.DataFrame(
        {"A": [1.0, 2.0]},
        index=pd.date_range("2024-01-01", periods=2, freq="min"),
    )
    viewer.store_dataframe(frame)

    assert viewer.update_trend_time_controls({"ready": True}) == (
        "2024-01-01T00:00:00",
        "2024-01-01T00:01:00",
    )
    assert viewer.update_trend_time_controls({"ready": False}) == (None, None)


def test_trend_controls_are_compact_and_aligned():
    trend_tab = viewer.layout.children[2].children[1].children[0].children[0]
    trend_controls = trend_tab.children[0]

    control_ids = [
        *(child.children[1].id for child in trend_controls.children[:4]),
        trend_controls.children[4].id,
    ]

    assert len(trend_controls.children) == 5
    assert control_ids == [
        "trend-start-time",
        "trend-end-time",
        "trend-max-points",
        "trend-axis-mode",
        "show-trend-button",
    ]
    assert trend_controls.style["gridTemplateColumns"] == "repeat(5, minmax(0, 1fr))"
    assert trend_controls.children[3].children[1].value == "independent"
    assert all(
        child.children[1].style["height"] == "38px"
        for child in trend_controls.children[:4]
    )
    assert trend_controls.children[4].style["height"] == "32px"
    assert trend_controls.children[4].style["minHeight"] == "32px"
    detail_section = trend_tab.children[2]
    assert detail_section.className == "detail-section"
    assert len(detail_section.children) == 1
    assert detail_section.children[0].className == "detail-content"


def test_trend_max_points_has_new_default_and_upper_bound():
    assert viewer._resolve_max_plot_points(None, 1) == 45_000
    assert viewer._resolve_max_plot_points(45_000, 8) == 45_000
    assert viewer._resolve_max_plot_points(45_000, 1) == 45_000
    assert viewer._resolve_max_plot_points(135_000, 8) == 135_000
    assert viewer._resolve_max_plot_points(135_000, 1) == 135_000
    assert viewer._resolve_max_plot_points(135_001, 1) == 135_000
    trend_tab = viewer.layout.children[2].children[1].children[0].children[0]
    max_points_input = trend_tab.children[0].children[2].children[1]
    assert max_points_input.value == 45_000
    assert max_points_input.max == 135_000


def test_statistics_cards_follow_selected_columns_and_include_distribution():
    frame = pd.DataFrame(
        {"A": [1.0, 2.0, 3.0], "B": [10.0, 20.0, 30.0], "C": [4.0, 4.0, 4.0]},
        index=pd.date_range("2024-01-01", periods=3, freq="min"),
    )

    cards = viewer._statistics_cards(frame, ["A", "C"])

    assert len(cards) == 2
    assert [card.children[0].children for card in cards] == ["A", "C"]
    labels = [row.children[0].children for row in cards[0].children[1].children]
    values = [row.children[1].children for row in cards[0].children[1].children]
    assert labels == ["均值", "标准差", "最大值", "最小值", "极差", "中位数", "有效点数/占比"]
    assert values == ["2", "0.8165", "3", "1", "2", "2", "3 / 100.0%"]
    assert cards[0].children[3].figure.data[0].type == "bar"


def test_clear_data_callback_clears_selection_without_removing_store(monkeypatch):
    frame = pd.DataFrame({"A": [1.0], "B": [2.0]})
    viewer.store_dataframe(frame)
    monkeypatch.setattr(viewer, "_triggered_id", lambda: "clear-data-button")

    state, selected = viewer.update_data_state(
        n_clicks=0,
        source="pi",
        upload_result=None,
        clear_clicks=1,
        tag_value=None,
        start_time=None,
        end_time=None,
    )

    assert viewer.get_dataframe() is frame
    assert state["options"] == [
        {"label": "A", "value": "A"},
        {"label": "B", "value": "B"},
    ]
    assert state["ready"] is True
    assert selected == []

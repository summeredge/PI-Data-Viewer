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


def test_create_trend_figure_only_draws_selected_columns():
    frame = pd.DataFrame(
        {"A": [1.0, 2.0], "B": [10.0, 20.0], "C": [100.0, 200.0]},
        index=pd.date_range("2024-01-01", periods=2, freq="min"),
    )

    figure = create_trend_figure(frame, ["A", "C"])

    assert [trace.name for trace in figure.data] == ["A", "C"]
    assert list(frame.columns) == ["A", "B", "C"]


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
        upload_contents=None,
        clear_clicks=1,
        tag_value=None,
        start_time=None,
        end_time=None,
        upload_filename=None,
    )

    assert viewer.get_dataframe() is frame
    assert state["options"] == [
        {"label": "A", "value": "A"},
        {"label": "B", "value": "B"},
    ]
    assert state["ready"] is True
    assert selected == []

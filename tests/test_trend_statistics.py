import pandas as pd
import pytest

from backend.statistics import calculate_statistics
from charts.trend import create_trend_figure
from pages import viewer


def test_create_trend_figure_preserves_datetime_index_and_multiple_tags():
    index = pd.DatetimeIndex(
        ["2024-01-01 00:00:00", "2024-01-01 00:01:00"], name="Timestamp"
    )
    frame = pd.DataFrame({"TAG_A": [1.0, 2.0], "TAG_B": [10.0, 20.0]}, index=index)

    figure = create_trend_figure(frame)

    assert [trace.name for trace in figure.data] == ["TAG_A", "TAG_B"]
    assert all(list(trace.x) == list(index) for trace in figure.data)
    assert figure.layout.xaxis.rangeslider.visible is True


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

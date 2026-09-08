import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

from backend.dataframe_store import clear_dataframe, store_dataframe
from backend.frequency import (
    DUPLICATE_TIMESTAMP_MESSAGE,
    INSUFFICIENT_DATA_MESSAGE,
    INSUFFICIENT_VARIATION_MESSAGE,
    IRREGULAR_SAMPLING_MESSAGE,
    calculate_fft_spectrum,
)
from charts.frequency import SINGLE_VARIABLE_MESSAGE, create_frequency_figure
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
    return " ".join(item for item in _components(component) if isinstance(item, str))


def setup_function():
    clear_dataframe()


def teardown_function():
    clear_dataframe()


def _signal(periods=240, frequency_cph=1.0, amplitude=2.0, interval="1min"):
    index = pd.date_range("2026-01-01", periods=periods, freq=interval)
    t_hours = np.arange(periods) * pd.Timedelta(interval).total_seconds() / 3600
    values = amplitude * np.sin(2 * np.pi * frequency_cph * t_hours)
    return pd.Series(values, index=index, name="PV1")


def test_fft_spectrum_recovers_frequency_and_amplitude_with_hann_correction():
    result = calculate_fft_spectrum(_signal())

    assert result["sample_size"] == 240
    assert result["dominant_frequency_cph"] == pytest.approx(1.0)
    assert result["dominant_period_hours"] == pytest.approx(1.0)
    assert result["dominant_amplitude"] == pytest.approx(2.0, rel=1e-3)
    assert result["sampling_interval_seconds"] == pytest.approx(60.0)
    assert result["nyquist_cph"] == pytest.approx(30.0)
    assert result["frequency_resolution_cph"] == pytest.approx(0.25)


def test_fft_spectrum_selects_the_strongest_of_multiple_frequencies():
    series = _signal(frequency_cph=0.5, amplitude=3.0)
    t_hours = np.arange(len(series)) / 60
    series = pd.Series(
        series.to_numpy() + np.sin(2 * np.pi * 2.0 * t_hours),
        index=series.index,
    )

    result = calculate_fft_spectrum(series)

    assert result["dominant_frequency_cph"] == pytest.approx(0.5)
    assert result["dominant_period_hours"] == pytest.approx(2.0)
    assert result["dominant_amplitude"] == pytest.approx(3.0, rel=1e-3)


@pytest.mark.parametrize(
    ("interval", "expected_interval", "expected_nyquist"),
    [("1min", 60.0, 30.0), ("5min", 300.0, 6.0), ("1h", 3600.0, 0.5)],
)
def test_fft_spectrum_uses_seconds_internally_and_cycles_per_hour_on_output(
    interval, expected_interval, expected_nyquist
):
    result = calculate_fft_spectrum(_signal(periods=8, interval=interval))

    assert result["sampling_interval_seconds"] == pytest.approx(expected_interval)
    assert result["nyquist_cph"] == pytest.approx(expected_nyquist)
    assert result["frequency_cph"][1] == pytest.approx(
        3600.0 / (8 * expected_interval)
    )


def test_fft_spectrum_accepts_small_timestamp_jitter_within_tolerance():
    index = pd.to_datetime(
        [
            "2026-01-01 00:00:00",
            "2026-01-01 00:01:00",
            "2026-01-01 00:02:00.001",
            "2026-01-01 00:03:00",
            "2026-01-01 00:04:00.001",
            "2026-01-01 00:05:00",
            "2026-01-01 00:06:00.001",
            "2026-01-01 00:07:00",
        ],
        format="mixed",
    )
    result = calculate_fft_spectrum(pd.Series(np.arange(8.0), index=index))

    assert result["sampling_interval_seconds"] == pytest.approx(60.0)


def test_fft_spectrum_rejects_internal_gaps_after_invalid_value_filtering():
    index = pd.date_range("2026-01-01", periods=9, freq="min")
    series = pd.Series(np.arange(9.0), index=index)
    series.iloc[4] = np.nan

    with pytest.raises(ValueError, match="等间隔") as error:
        calculate_fft_spectrum(series)
    assert str(error.value) == IRREGULAR_SAMPLING_MESSAGE


@pytest.mark.parametrize(
    ("series", "message"),
    [
        (pd.Series(np.arange(8.0)), "日期时间索引"),
        (
            pd.Series(
                np.arange(8.0),
                index=pd.DatetimeIndex(
                    [
                        "2026-01-01 00:00",
                        "2026-01-01 00:01",
                        "2026-01-01 00:00",
                        "2026-01-01 00:03",
                        "2026-01-01 00:04",
                        "2026-01-01 00:05",
                        "2026-01-01 00:06",
                        "2026-01-01 00:07",
                    ]
                ),
            ),
            DUPLICATE_TIMESTAMP_MESSAGE,
        ),
        (
            pd.Series(
                np.arange(8.0),
                index=pd.to_datetime(
                    [
                        "2026-01-01 00:00",
                        "2026-01-01 00:01",
                        "2026-01-01 00:03",
                        "2026-01-01 00:02",
                        "2026-01-01 00:04",
                        "2026-01-01 00:05",
                        "2026-01-01 00:06",
                        "2026-01-01 00:07",
                    ]
                ),
            ),
            "严格递增",
        ),
        (pd.Series(np.arange(7.0), index=pd.date_range("2026-01-01", periods=7, freq="min")), INSUFFICIENT_DATA_MESSAGE),
        (
            pd.Series(["bad"] * 8, index=pd.date_range("2026-01-01", periods=8, freq="min")),
            "有效数值",
        ),
        (
            pd.Series([1.0] * 8, index=pd.date_range("2026-01-01", periods=8, freq="min")),
            INSUFFICIENT_VARIATION_MESSAGE,
        ),
    ],
)
def test_fft_spectrum_rejects_invalid_inputs_with_clear_messages(series, message):
    with pytest.raises(ValueError, match=message):
        calculate_fft_spectrum(series)


def test_fft_spectrum_filters_nan_and_infinite_values_without_mutating_series():
    index = pd.date_range("2026-01-01", periods=11, freq="min")
    series = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, np.nan, np.inf, "bad"], index=index)
    original = series.copy(deep=True)

    result = calculate_fft_spectrum(series)

    assert result["sample_size"] == 8
    assert np.isfinite(result["frequency_cph"]).all()
    assert np.isfinite(result["amplitude"]).all()
    pd.testing.assert_series_equal(series, original)


def test_frequency_figure_uses_positive_scattergl_spectrum_and_peak_marker():
    result = calculate_fft_spectrum(_signal())

    figure = create_frequency_figure("PV1", result)

    assert isinstance(figure, go.Figure)
    assert figure.data[0].type == "scattergl"
    assert all(value > 0 for trace in figure.data for value in trace.x)
    assert figure.layout.xaxis.title.text == "频率（次/小时）"
    assert figure.layout.yaxis.title.text == "振幅"
    assert "主峰" in {trace.name for trace in figure.data}
    assert all(
        label in figure.data[0].hovertemplate
        for label in ("频率", "周期", "振幅")
    )
    assert any("主频：1.00 次/小时" in annotation.text for annotation in figure.layout.annotations)


def test_frequency_tab_is_last_and_uses_shared_selector():
    tabs = viewer.layout.children[2].children[1].children[0]

    assert [tab.label for tab in tabs.children] == [
        "趋势图",
        "散点矩阵",
        "箱线图",
        "概率图",
        "能力分析",
        "控制图",
        "频谱分析",
    ]
    frequency_tab = tabs.children[6]
    component_ids = {
        component.id
        for component in _components(frequency_tab)
        if hasattr(component, "id")
    }
    assert {
        "frequency-graph",
        "frequency-summary",
        "frequency-selected-columns",
        "frequency-status",
    } <= component_ids
    assert "variable-selector" not in component_ids
    assert "汉宁窗" in _text(frequency_tab)
    assert "不会自动插值或重采样" in _text(frequency_tab)


def test_render_frequency_view_validates_selection_and_preserves_shared_frame():
    frame = pd.DataFrame(
        {"PV1": _signal().to_numpy(), "PV2": np.arange(240.0)},
        index=_signal().index,
    )
    original = frame.copy(deep=True)
    store_dataframe(frame)

    _, _, selected, no_selection_status = viewer.render_frequency_view(
        {"ready": True}, []
    )
    assert selected == "未选择变量"
    assert no_selection_status == "请至少选择一个变量"

    _, _, selected, multi_status = viewer.render_frequency_view(
        {"ready": True}, ["PV1", "PV2"]
    )
    assert selected == "PV1, PV2"
    assert multi_status == SINGLE_VARIABLE_MESSAGE

    figure, summary, selected, status = viewer.render_frequency_view(
        {"ready": True}, ["PV1"]
    )
    assert isinstance(figure, go.Figure)
    assert selected == "PV1"
    assert status == ""
    assert "主频" in _text(summary)
    assert viewer.get_dataframe() is frame
    pd.testing.assert_frame_equal(frame, original)


def test_frequency_callback_uses_shared_state_and_selector():
    from app import app

    callback = next(
        entry
        for entry in app.callback_map.values()
        if entry.get("callback")
        and entry["callback"].__name__ == "render_frequency_view"
    )

    assert [item["id"] for item in callback["inputs"]] == [
        "viewer-state",
        "variable-selector",
        "viewer-tabs",
    ]

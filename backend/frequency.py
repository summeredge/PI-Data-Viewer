"""Single-sided FFT spectrum calculations for one shared time series."""

from __future__ import annotations

import numpy as np
import pandas as pd


NO_VALID_DATA_MESSAGE = "所选变量无有效数值数据"
INSUFFICIENT_DATA_MESSAGE = "有效数值点不足，FFT 至少需要 8 个连续采样点"
INVALID_INDEX_MESSAGE = "Frequency Analysis 只支持 DatetimeIndex"
INVALID_TIMESTAMP_MESSAGE = "时间戳必须有效"
DUPLICATE_TIMESTAMP_MESSAGE = "时间戳不能重复"
NON_INCREASING_TIMESTAMP_MESSAGE = "时间戳必须严格递增"
IRREGULAR_SAMPLING_MESSAGE = (
    "FFT 要求连续且等间隔采样的数据；请检查时间间隔，"
    "工具不会自动插值或重采样"
)
INSUFFICIENT_VARIATION_MESSAGE = "数据波动不足，无法进行频域分析"


def calculate_fft_spectrum(series: pd.Series) -> dict[str, object]:
    """Calculate a Hann-windowed, single-sided amplitude spectrum."""

    if not isinstance(series, pd.Series):
        raise TypeError("series must be a pandas Series")
    if not isinstance(series.index, pd.DatetimeIndex):
        raise ValueError(INVALID_INDEX_MESSAGE)

    index = series.index
    if index.hasnans:
        raise ValueError(INVALID_TIMESTAMP_MESSAGE)
    if index.has_duplicates:
        raise ValueError(DUPLICATE_TIMESTAMP_MESSAGE)
    if len(index) > 1 and np.any(np.diff(index.asi8) <= 0):
        raise ValueError(NON_INCREASING_TIMESTAMP_MESSAGE)

    try:
        numeric = pd.to_numeric(series, errors="coerce")
        values = numeric.to_numpy(dtype=float, na_value=np.nan)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(NO_VALID_DATA_MESSAGE) from exc

    finite = np.isfinite(values)
    valid_values = values[finite]
    valid_index = index[finite]
    if valid_values.size == 0:
        raise ValueError(NO_VALID_DATA_MESSAGE)

    if valid_values.size >= 2:
        deltas = (valid_index[1:] - valid_index[:-1]).total_seconds()
        deltas = np.asarray(deltas, dtype=float)
        sampling_interval_seconds = float(np.median(deltas))
        if sampling_interval_seconds <= 0 or not np.allclose(
            deltas,
            sampling_interval_seconds,
            rtol=0.01,
            atol=0.001,
        ):
            raise ValueError(IRREGULAR_SAMPLING_MESSAGE)
    else:
        raise ValueError(INSUFFICIENT_DATA_MESSAGE)

    if valid_values.size < 8:
        raise ValueError(INSUFFICIENT_DATA_MESSAGE)
    if np.all(valid_values == valid_values[0]):
        raise ValueError(INSUFFICIENT_VARIATION_MESSAGE)

    sample_size = int(valid_values.size)
    values_centered = valid_values - valid_values.mean()
    window = np.hanning(sample_size)
    windowed = values_centered * window
    fft_values = np.fft.rfft(windowed)
    frequency_hz = np.fft.rfftfreq(sample_size, d=sampling_interval_seconds)
    amplitude = 2.0 * np.abs(fft_values) / window.sum()
    amplitude[0] *= 0.5
    if sample_size % 2 == 0:
        amplitude[-1] *= 0.5

    frequency_cph = frequency_hz * 3600.0
    positive = np.flatnonzero(frequency_cph > 0)
    peak_index = int(positive[np.argmax(amplitude[positive])])
    frequency_resolution_cph = float(frequency_cph[1] - frequency_cph[0])
    dominant_frequency_cph = float(frequency_cph[peak_index])

    return {
        "frequency_cph": frequency_cph.astype(float),
        "amplitude": amplitude.astype(float),
        "sample_size": sample_size,
        "sampling_interval_seconds": sampling_interval_seconds,
        "duration_hours": sample_size * sampling_interval_seconds / 3600.0,
        "nyquist_cph": 3600.0 / (2.0 * sampling_interval_seconds),
        "frequency_resolution_cph": frequency_resolution_cph,
        "dominant_frequency_cph": dominant_frequency_cph,
        "dominant_period_hours": 1.0 / dominant_frequency_cph,
        "dominant_amplitude": float(amplitude[peak_index]),
    }

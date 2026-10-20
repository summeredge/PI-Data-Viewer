"""Statistical process control calculations for I-MR charts."""

from __future__ import annotations

import numpy as np
import pandas as pd


D2 = 1.128
D3 = 0.0
D4 = 3.267
DEFAULT_SPECIAL_CAUSE_TESTS = (1,)


def _normalize_tests(tests, max_test: int) -> tuple[int, ...]:
    tests = DEFAULT_SPECIAL_CAUSE_TESTS if tests is None else tests
    if isinstance(tests, (str, bytes)):
        raise ValueError("检验选项必须是检验编号")
    try:
        selected = tuple(dict.fromkeys(int(test) for test in tests))
    except (TypeError, ValueError) as exc:
        raise ValueError("检验选项必须是检验编号") from exc
    if any(test < 1 or test > max_test for test in selected):
        raise ValueError(f"检验编号必须在 1 到 {max_test} 之间")
    return selected


def _rolling_count(mask: pd.Series, window: int, minimum: int) -> pd.Series:
    return mask.astype(int).rolling(window, min_periods=window).sum().ge(minimum)


def detect_special_causes(
    series: pd.Series,
    center: float,
    sigma: float,
    tests=None,
    *,
    ucl: float | None = None,
    lcl: float | None = None,
    max_test: int = 8,
) -> dict[int, pd.Series]:
    """Return Minitab-style special-cause signals at the completing point."""

    if not isinstance(series, pd.Series):
        raise TypeError("series must be a pandas Series")
    center = float(center)
    sigma = float(sigma)
    if not np.isfinite(center) or not np.isfinite(sigma) or sigma < 0:
        raise ValueError("center and sigma must be finite; sigma cannot be negative")

    selected = _normalize_tests(tests, max_test)
    values = pd.to_numeric(series, errors="coerce").astype(float)
    values = values.where(np.isfinite(values.to_numpy(dtype=float)))
    valid = values.notna()
    signals: dict[int, pd.Series] = {}

    if 1 in selected:
        upper = center + 3 * sigma if ucl is None else float(ucl)
        lower = center - 3 * sigma if lcl is None else float(lcl)
        signals[1] = ((values > upper) | (values < lower)).fillna(False)
    if 2 in selected:
        signals[2] = _rolling_count(values > center, 9, 9) | _rolling_count(
            values < center, 9, 9
        )
    if 3 in selected:
        differences = values.diff()
        signals[3] = _rolling_count(differences > 0, 5, 5) | _rolling_count(
            differences < 0, 5, 5
        )
    if 4 in selected:
        differences = values.diff()
        alternating = differences.mul(differences.shift()).lt(0)
        signals[4] = _rolling_count(alternating, 12, 12)
    if 5 in selected:
        complete = _rolling_count(valid, 3, 3)
        signals[5] = complete & (
            _rolling_count(values > center + 2 * sigma, 3, 2)
            | _rolling_count(values < center - 2 * sigma, 3, 2)
        )
    if 6 in selected:
        complete = _rolling_count(valid, 5, 5)
        signals[6] = complete & (
            _rolling_count(values > center + sigma, 5, 4)
            | _rolling_count(values < center - sigma, 5, 4)
        )
    if 7 in selected:
        signals[7] = _rolling_count((values - center).abs() < sigma, 15, 15)
    if 8 in selected:
        signals[8] = _rolling_count((values - center).abs() > sigma, 8, 8)
    return signals


def _combined_signals(results: dict[int, pd.Series], index: pd.Index) -> pd.Series:
    combined = pd.Series(False, index=index)
    for signals in results.values():
        combined |= signals
    return combined


def calculate_imr(series: pd.Series, tests=None) -> dict[str, object]:
    """Calculate I-MR values and Shewhart control limits."""

    if not isinstance(series, pd.Series):
        raise TypeError("series must be a pandas Series")

    numeric = pd.to_numeric(series, errors="coerce").astype(float)
    finite = np.isfinite(numeric.to_numpy(dtype=float))
    values = numeric.where(finite)
    valid_values = values.dropna()
    if valid_values.empty:
        raise ValueError("所选变量无有效数值数据")

    moving_range = values.diff().abs()
    valid_moving_range = moving_range.dropna()
    xbar = float(valid_values.mean())
    mr_bar = float(valid_moving_range.mean()) if not valid_moving_range.empty else 0.0
    sigma = mr_bar / D2
    individual_ucl = xbar + 3 * sigma
    individual_lcl = xbar - 3 * sigma
    mr_ucl = D4 * mr_bar
    mr_lcl = D3 * mr_bar

    individual_outliers = (
        (values > individual_ucl) | (values < individual_lcl)
    ).fillna(False)
    moving_range_outliers = (
        (moving_range > mr_ucl) | (moving_range < mr_lcl)
    ).fillna(False)
    selected_tests = _normalize_tests(tests, 8)
    individual_tests = detect_special_causes(
        values,
        xbar,
        sigma,
        selected_tests,
        ucl=individual_ucl,
        lcl=individual_lcl,
    )
    moving_range_tests = detect_special_causes(
        moving_range,
        mr_bar,
        sigma,
        [test for test in selected_tests if test <= 4],
        ucl=mr_ucl,
        lcl=mr_lcl,
        max_test=4,
    )
    return {
        "values": values,
        "moving_range": moving_range,
        "xbar": xbar,
        "mr_bar": mr_bar,
        "sigma": sigma,
        "individual_cl": xbar,
        "individual_ucl": individual_ucl,
        "individual_lcl": individual_lcl,
        "mr_cl": mr_bar,
        "mr_ucl": mr_ucl,
        "mr_lcl": mr_lcl,
        "individual_outliers": individual_outliers,
        "moving_range_outliers": moving_range_outliers,
        "selected_tests": selected_tests,
        "individual_tests": individual_tests,
        "moving_range_tests": moving_range_tests,
        "individual_signals": _combined_signals(individual_tests, values.index),
        "moving_range_signals": _combined_signals(
            moving_range_tests, moving_range.index
        ),
    }


def calculate_staged_imr(
    series: pd.Series, boundaries, tests=None
) -> list[dict[str, object]]:
    """Split the series at `boundaries` and run calculate_imr() per stage.

    A boundary starts a new stage from that timestamp onward, so every stage
    restarts its own moving range and special-cause runs. Boundaries are
    validated against the index exactly as bound_stages() does.
    """

    stages = []
    for stage_number, (start, stage_series) in enumerate(
        stage_slices(series, boundaries), start=1
    ):
        try:
            result = calculate_imr(stage_series, tests=tests)
        except ValueError as exc:
            raise ValueError(f"阶段 {stage_number}：{exc}") from None
        if result["moving_range"].dropna().empty:
            raise ValueError(
                f"阶段 {stage_number}（{_format_time(start)} 起）有效数据不足，"
                "无法计算移动极差与控制限，请调整分界时间"
            )
        stage = dict(result)
        stage["stage"] = stage_number
        stage["start"] = start
        stages.append(stage)
    return stages


def stage_slices(series: pd.Series, boundaries) -> list[tuple[pd.Timestamp, pd.Series]]:
    """Return (first timestamp, samples) for each stage defined by boundaries."""

    index = series.index
    if not isinstance(index, pd.DatetimeIndex):
        raise TypeError("series must use a pandas DatetimeIndex")
    if index.empty:
        return []
    stamps = bound_stages(index, boundaries)
    starts = [index[0], *stamps]
    # 每段是 [起点, 下一段起点)：分界点本身属于新阶段。
    bounds = [*starts, index[-1] + pd.Timedelta(1, "ns")]
    return [
        (start, series[(index >= start) & (index < end)])
        for start, end in zip(starts, bounds[1:])
    ]


def bound_stages(index: pd.DatetimeIndex, boundaries) -> list[pd.Timestamp]:
    """Sort, de-duplicate and validate stage boundaries for a DatetimeIndex.

    Boundaries must fall strictly inside the data range. A boundary on the
    exact last timestamp would leave the following stage without samples, so it
    is rejected up front instead of producing a misleading stage.
    """

    if not isinstance(index, pd.DatetimeIndex):
        raise TypeError("series must use a pandas DatetimeIndex")
    if boundaries in (None, ""):
        return []
    if isinstance(boundaries, (str, bytes)) or not hasattr(boundaries, "__iter__"):
        raise ValueError("阶段分界时间必须是时间列表")

    stamps = set()
    for value in boundaries:
        if value in (None, ""):
            continue
        try:
            stamp = pd.Timestamp(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"无法识别的分界时间：{value}") from exc
        if stamp is pd.NaT:
            raise ValueError(f"无法识别的分界时间：{value}")
        stamps.add(stamp)
    if not stamps:
        return []
    if index.empty:
        raise ValueError("当前数据无时间范围，无法设置阶段")

    ordered = sorted(stamps)
    first, last = index[0], index[-1]
    for stamp in ordered:
        try:
            too_early = stamp <= first
            too_late = stamp >= last
        except TypeError:
            raise ValueError("分界时间与数据时间的时区不一致") from None
        if too_early:
            raise ValueError(
                f"分界时间 {_format_time(stamp)} 必须晚于数据起点 {_format_time(first)}"
            )
        if too_late:
            raise ValueError(
                f"分界时间 {_format_time(stamp)} 必须早于数据终点 {_format_time(last)}"
            )
    return ordered


def _format_time(value: pd.Timestamp) -> str:
    return pd.Timestamp(value).strftime("%Y-%m-%d %H:%M:%S")

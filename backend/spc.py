"""Statistical process control calculations for I-MR charts."""

from __future__ import annotations

import numpy as np
import pandas as pd


D2 = 1.128
D3 = 0.0
D4 = 3.267


def calculate_imr(series: pd.Series) -> dict[str, object]:
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
    }

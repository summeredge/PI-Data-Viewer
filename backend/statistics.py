"""Basic statistics for the current Viewer DataFrame."""

from __future__ import annotations

import numpy as np
import pandas as pd


def calculate_statistics(df: pd.DataFrame) -> pd.DataFrame:
    """Return one row per tag without changing the input DataFrame."""

    if not isinstance(df, pd.DataFrame):
        raise TypeError("df must be a pandas DataFrame")
    return df.agg(["count", "mean", "std", "min", "max"]).T


def calculate_series_summary(series: pd.Series) -> dict[str, object]:
    """Return finite-value summary data for one trend-statistics card."""

    if not isinstance(series, pd.Series):
        raise TypeError("series must be a pandas Series")

    numeric = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    values = numeric[np.isfinite(numeric)]
    count = int(values.size)
    total = len(series)
    if not count:
        return {
            "values": values,
            "mean": np.nan,
            "std": np.nan,
            "max": np.nan,
            "min": np.nan,
            "range": np.nan,
            "median": np.nan,
            "count": 0,
            "ratio": 0.0,
        }

    mean = float(values.mean())
    return {
        "values": values,
        "mean": mean,
        "std": float(values.std(ddof=0)),
        "max": float(values.max()),
        "min": float(values.min()),
        "range": float(values.max() - values.min()),
        "median": float(np.median(values)),
        "count": count,
        "ratio": count / total if total else 0.0,
    }

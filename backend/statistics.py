"""Basic statistics for the current Viewer DataFrame."""

from __future__ import annotations

import pandas as pd


def calculate_statistics(df: pd.DataFrame) -> pd.DataFrame:
    """Return one row per tag without changing the input DataFrame."""

    if not isinstance(df, pd.DataFrame):
        raise TypeError("df must be a pandas DataFrame")
    return df.agg(["count", "mean", "std", "min", "max"]).T

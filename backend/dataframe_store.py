"""Small in-process cache for the current Viewer DataFrame."""

import pandas as pd


_dataframe: pd.DataFrame | None = None


def store_dataframe(df: pd.DataFrame) -> None:
    if not isinstance(df, pd.DataFrame):
        raise TypeError("df must be a pandas DataFrame")
    global _dataframe
    _dataframe = df


def clear_dataframe() -> None:
    global _dataframe
    _dataframe = None


def get_dataframe() -> pd.DataFrame | None:
    return _dataframe

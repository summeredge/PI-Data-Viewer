import pandas as pd

from backend.dataframe_store import clear_dataframe, get_dataframe, store_dataframe


def test_dataframe_store_round_trip():
    frame = pd.DataFrame(
        {"TAG_A": [1.0]}, index=pd.DatetimeIndex(["2024-01-01 00:00:00"])
    )

    store_dataframe(frame)

    assert get_dataframe() is frame


def test_clear_dataframe_removes_current_frame():
    store_dataframe(pd.DataFrame({"TAG_A": [1.0]}))

    clear_dataframe()

    assert get_dataframe() is None

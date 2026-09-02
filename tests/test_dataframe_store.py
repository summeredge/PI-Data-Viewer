import pandas as pd

from backend.dataframe_store import get_dataframe, store_dataframe


def test_dataframe_store_round_trip():
    frame = pd.DataFrame(
        {"TAG_A": [1.0]}, index=pd.DatetimeIndex(["2024-01-01 00:00:00"])
    )

    store_dataframe(frame)

    assert get_dataframe() is frame

import base64
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest

from backend.dataframe_store import get_dataframe
from backend.file_reader import read_local_file
from pages import viewer


CSV_DATA = """Timestamp,A.PV,B.PV
2026-09-01 00:00:00,10.1,20.1
2026-09-01 00:01:00,10.2,20.2
"""


def _upload_contents(data: bytes, media_type: str) -> str:
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


def test_csv_import_uses_standard_dataframe_format():
    frame = read_local_file(
        _upload_contents(CSV_DATA.encode("utf-8"), "text/csv"), "sample.csv"
    )

    assert isinstance(frame.index, pd.DatetimeIndex)
    assert frame.index.name == "Timestamp"
    assert list(frame.columns) == ["A.PV", "B.PV"]
    assert frame["A.PV"].tolist() == [10.1, 10.2]
    assert frame["B.PV"].tolist() == [20.1, 20.2]
    assert all(pd.api.types.is_numeric_dtype(frame[column]) for column in frame.columns)


def test_excel_import_matches_equivalent_csv():
    source = pd.DataFrame(
        {
            "Timestamp": pd.to_datetime(
                ["2026-09-01 00:00:00", "2026-09-01 00:01:00"]
            ),
            "A.PV": [10.1, 10.2],
            "B.PV": [20.1, 20.2],
        }
    )
    workbook = BytesIO()
    source.to_excel(workbook, index=False, engine="openpyxl")

    excel_frame = read_local_file(
        _upload_contents(
            workbook.getvalue(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
        "sample.xlsx",
    )
    csv_frame = read_local_file(
        _upload_contents(CSV_DATA.encode("utf-8"), "text/csv"), "sample.csv"
    )

    pd.testing.assert_frame_equal(excel_frame, csv_frame)


@pytest.mark.parametrize(
    ("contents", "filename", "message"),
    [
        (_upload_contents(b"", "text/csv"), "sample.csv", "文件为空"),
        (
            _upload_contents(b"Timestamp\n2026-09-01 00:00:00\n", "text/csv"),
            "sample.csv",
            "没有有效数据列",
        ),
        (
            _upload_contents(b"not a supported file", "text/plain"),
            "sample.json",
            "不支持的文件类型",
        ),
    ],
)
def test_local_file_validation_errors_are_clear(contents, filename, message):
    with pytest.raises(ValueError, match=message):
        read_local_file(contents, filename)


def test_invalid_timestamp_is_rejected():
    contents = _upload_contents(
        b"Timestamp,A.PV\nnot-a-timestamp,10.1\n", "text/csv"
    )

    with pytest.raises(ValueError, match="时间列无法解析"):
        read_local_file(contents, "sample.csv")


def test_local_import_stores_one_shared_frame_for_trend_and_statistics(monkeypatch):
    stored = []
    real_store = viewer.store_dataframe

    def store_and_record(frame):
        stored.append(frame)
        real_store(frame)

    monkeypatch.setattr(viewer, "store_dataframe", store_and_record)
    monkeypatch.setattr(
        viewer, "read_pi_data", lambda *args: pytest.fail("local import called PI reader")
    )

    figure, records, status = viewer.update_viewer(
        0,
        None,
        None,
        None,
        "file",
        _upload_contents(CSV_DATA.encode("utf-8"), "text/csv"),
        "sample.csv",
    )

    assert status == ""
    assert len(stored) == 1
    assert get_dataframe() is stored[0]
    assert [trace.name for trace in figure.data] == ["A.PV", "B.PV"]
    assert records[0]["Tag"] == "A.PV"
    assert records[0]["mean"] == pytest.approx(10.15)


def test_source_controls_toggle_pi_and_file_inputs():
    pi_style, file_style = viewer.update_source_controls("pi")
    assert pi_style["display"] == "flex"
    assert file_style["display"] == "none"

    pi_style, file_style = viewer.update_source_controls("file")
    assert pi_style["display"] == "none"
    assert file_style["display"] == "block"


def test_graphics_modules_do_not_read_from_pi():
    project_root = Path(__file__).resolve().parents[1]
    paths = [
        project_root / "backend" / "statistics.py",
        *[
            project_root / "charts" / f"{name}.py"
            for name in ("trend", "scatter", "histogram", "boxplot", "heatmap", "control_chart")
        ],
    ]

    for path in paths:
        source = path.read_text(encoding="utf-8")
        assert "read_pi_data" not in source
        assert "PIReader.exe" not in source

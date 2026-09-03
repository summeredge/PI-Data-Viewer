import base64
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest

from backend.dataframe_store import get_dataframe
from backend import file_reader
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


def test_utf8_sig_csv_keeps_timestamp_index():
    frame = read_local_file(
        _upload_contents(CSV_DATA.encode("utf-8-sig"), "text/csv"), "sample.csv"
    )

    assert isinstance(frame.index, pd.DatetimeIndex)
    assert frame.index.name == "Timestamp"
    assert frame.index[0] == pd.Timestamp("2026-09-01 00:00:00")


def test_windows_encoded_csv_is_read_without_utf8_decode_failure():
    data = (
        "时间,温度.PV\n"
        "2026-09-01 00:00:00,10\n"
        "2026-09-01 00:01:00,11\n"
    ).encode("gbk")

    frame = read_local_file(_upload_contents(data, "text/csv"), "sample.csv")

    assert frame.index.name == "Timestamp"
    assert list(frame.columns) == ["温度.PV"]
    assert frame["温度.PV"].tolist() == [10, 11]


def test_gb18030_csv_is_read():
    data = (
        "时间,温度𠀀.PV\n"
        "2026-09-01 00:00:00,10\n"
        "2026-09-01 00:01:00,11\n"
    ).encode("gb18030")

    frame = read_local_file(_upload_contents(data, "text/csv"), "sample.csv")

    assert frame.index.name == "Timestamp"
    assert list(frame.columns) == ["温度𠀀.PV"]
    assert frame["温度𠀀.PV"].tolist() == [10, 11]


def test_upload_bytes_reach_pandas_as_binary_stream(monkeypatch):
    data = CSV_DATA.encode("utf-8")
    streams = []

    def fake_read_csv(stream, **kwargs):
        streams.append((stream, kwargs))
        assert isinstance(stream, BytesIO)
        assert stream.read() == data
        return pd.DataFrame(
            {"Timestamp": ["2026-09-01 00:00:00"], "A.PV": [10]}
        )

    monkeypatch.setattr(file_reader.pd, "read_csv", fake_read_csv)

    frame = read_local_file(_upload_contents(data, "text/csv"), "sample.csv")

    assert len(streams) == 1
    assert streams[0][1] == {"encoding": "utf-8"}
    assert frame.index.name == "Timestamp"


def test_csv_upload_path_does_not_force_utf8_decode():
    source = (
        Path(__file__).resolve().parents[1] / "backend" / "file_reader.py"
    ).read_text(encoding="utf-8")

    assert ".decode(" not in source
    assert "StringIO" not in source
    assert "pd.read_csv(BytesIO(raw), encoding=encoding)" in source


def test_csv_fallback_tries_all_encodings_and_reports_clear_error(monkeypatch):
    encodings = []
    failures = iter(
        (
            UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid byte"),
            pd.errors.ParserError("malformed CSV"),
            ValueError("invalid CSV value"),
            ValueError("invalid CSV value"),
        )
    )

    def fake_read_csv(stream, **kwargs):
        encodings.append(kwargs["encoding"])
        raise next(failures)

    monkeypatch.setattr(file_reader.pd, "read_csv", fake_read_csv)

    with pytest.raises(ValueError, match="CSV 文件无法读取"):
        read_local_file(_upload_contents(b"not a csv", "text/csv"), "sample.csv")

    assert encodings == ["utf-8", "utf-8-sig", "gb18030", "gbk"]


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


def test_interval_dropdown_is_available_for_pi_and_hidden_with_file_controls():
    controls = viewer.layout.children[2].children[0].children[3]
    interval = next(
        child for child in controls.children if getattr(child, "id", None) == "interval"
    )

    assert [option["value"] for option in interval.options] == [
        "1m",
        "5m",
        "10m",
        "30m",
        "1h",
    ]
    assert interval.value == "1m"
    assert viewer.update_source_controls("file")[0]["display"] == "none"


def test_pi_query_passes_selected_interval_to_reader(monkeypatch):
    frame = pd.DataFrame(
        {"TAG_A": [1.0]},
        index=pd.date_range("2024-01-01", periods=1, freq="min"),
    )
    calls = []

    def fake_read(*args):
        calls.append(args)
        return frame

    monkeypatch.setattr(viewer, "read_pi_data", fake_read)

    viewer.update_viewer(
        1,
        "TAG_A",
        "2024-01-01 00:00:00",
        "2024-01-01 00:01:00",
        interval="10m",
    )

    assert calls == [
        (
            ["TAG_A"],
            "2024-01-01 00:00:00",
            "2024-01-01 00:01:00",
            "10m",
        )
    ]


def test_data_source_switch_does_not_reload_or_parse_data(monkeypatch):
    frame = pd.DataFrame(
        {"TAG_A": [1.0]},
        index=pd.date_range("2024-01-01", periods=1, freq="min"),
    )
    pi_calls = []
    file_calls = []
    triggered = ["query-button"]

    def fake_pi(*args):
        pi_calls.append(args)
        return frame

    def fake_file(*args):
        file_calls.append(args)
        return frame

    monkeypatch.setattr(viewer, "read_pi_data", fake_pi)
    monkeypatch.setattr(viewer, "read_local_file", fake_file)
    monkeypatch.setattr(viewer, "_triggered_id", lambda: triggered[0])

    viewer.update_data_state(
        1, None, 0, "pi", "TAG_A", "2024-01-01", "2024-01-01 00:01", None
    )
    assert len(pi_calls) == 1

    triggered[0] = "data-source"
    viewer.update_data_state(
        1, "upload-contents", 0, "file", "TAG_A", "2024-01-01", "2024-01-01 00:01", "sample.csv"
    )
    triggered[0] = "data-source"
    viewer.update_data_state(
        1, "upload-contents", 0, "pi", "TAG_A", "2024-01-01", "2024-01-01 00:01", "sample.csv"
    )
    assert len(pi_calls) == 1
    assert file_calls == []

    triggered[0] = "file-upload"
    viewer.update_data_state(
        1, "upload-contents", 0, "file", "TAG_A", "2024-01-01", "2024-01-01 00:01", "sample.csv"
    )
    assert len(file_calls) == 1


def test_data_loading_callback_uses_data_source_as_state():
    from app import app

    callback = next(
        entry for entry in app.callback_map.values()
        if entry["callback"].__name__ == "update_data_state"
    )
    assert "data-source" not in {item["id"] for item in callback["inputs"]}
    assert "data-source" in {item["id"] for item in callback["state"]}


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

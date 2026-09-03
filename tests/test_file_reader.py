import importlib
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest

from backend import file_reader
from backend.dataframe_store import clear_dataframe, get_dataframe
from backend.file_reader import read_local_file
from pages import viewer


CSV_DATA = """time,S_consumption_6h,FICQ706004.PV,FI706017.PV
2026/6/21 0:00,0.959938288,4437.596680,230.048660
2026/6/21 0:01,0.959908000,4415.406738,229.038712
"""


@pytest.fixture(autouse=True)
def _reset_store():
    clear_dataframe()
    yield
    clear_dataframe()


def _write_file(tmp_path, data: bytes, filename="sample.csv") -> Path:
    path = tmp_path / filename
    path.write_bytes(data)
    return path


def _post_upload(filename: str, data: bytes):
    app_module = importlib.import_module("app")
    return app_module.app.server.test_client().post(
        "/api/upload",
        data={"file": (BytesIO(data), filename)},
        content_type="multipart/form-data",
    )


def test_csv_import_uses_standard_dataframe_format(tmp_path):
    frame = read_local_file(_write_file(tmp_path, CSV_DATA.encode("utf-8")))

    assert isinstance(frame.index, pd.DatetimeIndex)
    assert frame.index.name == "Timestamp"
    assert list(frame.columns) == [
        "S_consumption_6h",
        "FICQ706004.PV",
        "FI706017.PV",
    ]
    assert frame["S_consumption_6h"].tolist() == [0.959938288, 0.959908]
    assert frame["FICQ706004.PV"].tolist() == [4437.59668, 4415.406738]
    assert frame["FI706017.PV"].tolist() == [230.04866, 229.038712]
    assert all(pd.api.types.is_numeric_dtype(frame[column]) for column in frame.columns)


def test_utf8_sig_csv_keeps_timestamp_index(tmp_path):
    frame = read_local_file(_write_file(tmp_path, CSV_DATA.encode("utf-8-sig")))

    assert isinstance(frame.index, pd.DatetimeIndex)
    assert frame.index.name == "Timestamp"
    assert frame.index[0] == pd.Timestamp("2026-06-21 00:00:00")


def test_windows_encoded_csv_is_read_without_utf8_decode_failure(tmp_path):
    data = (
        "时间,温度.PV\n"
        "2026-09-01 00:00:00,10\n"
        "2026-09-01 00:01:00,11\n"
    ).encode("gbk")

    frame = read_local_file(_write_file(tmp_path, data))

    assert frame.index.name == "Timestamp"
    assert list(frame.columns) == ["温度.PV"]
    assert frame["温度.PV"].tolist() == [10, 11]


def test_gb18030_csv_is_read(tmp_path):
    data = (
        "时间,温度𠀀.PV\n"
        "2026-09-01 00:00:00,10\n"
        "2026-09-01 00:01:00,11\n"
    ).encode("gb18030")

    frame = read_local_file(_write_file(tmp_path, data))

    assert frame.index.name == "Timestamp"
    assert list(frame.columns) == ["温度𠀀.PV"]
    assert frame["温度𠀀.PV"].tolist() == [10, 11]


def test_csv_path_reaches_pandas_as_a_path(tmp_path, monkeypatch):
    path = _write_file(tmp_path, CSV_DATA.encode("utf-8"))
    calls = []

    def fake_read_csv(csv_path, **kwargs):
        calls.append((csv_path, kwargs))
        assert isinstance(csv_path, Path)
        assert csv_path == path
        return pd.DataFrame(
            {"time": ["2026-09-01 00:00:00"], "A.PV": [10]}
        )

    monkeypatch.setattr(file_reader.pd, "read_csv", fake_read_csv)

    frame = read_local_file(path)

    assert len(calls) == 1
    assert calls[0][1] == {"encoding": "utf-8"}
    assert frame.index.name == "Timestamp"


def test_production_file_reader_is_path_based():
    source = (
        Path(__file__).resolve().parents[1] / "backend" / "file_reader.py"
    ).read_text(encoding="utf-8")

    assert "base64" not in source.lower()
    assert "BytesIO" not in source
    assert "pd.read_csv(path" in source
    assert "pd.read_excel(path" in source


def test_csv_fallback_tries_all_encodings_and_reports_clear_error(tmp_path, monkeypatch):
    path = _write_file(tmp_path, b"not a csv")
    encodings = []
    failures = iter(
        (
            UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid byte"),
            pd.errors.ParserError("malformed CSV"),
            ValueError("invalid CSV value"),
            ValueError("invalid CSV value"),
        )
    )

    def fake_read_csv(csv_path, **kwargs):
        assert csv_path == path
        encodings.append(kwargs["encoding"])
        raise next(failures)

    monkeypatch.setattr(file_reader.pd, "read_csv", fake_read_csv)

    with pytest.raises(ValueError, match="CSV 文件无法读取"):
        read_local_file(path)

    assert encodings == ["utf-8", "utf-8-sig", "gb18030", "gbk"]


def test_excel_import_matches_equivalent_csv(tmp_path):
    source = pd.DataFrame(
        {
            "Timestamp": pd.to_datetime(
                ["2026-09-01 00:00:00", "2026-09-01 00:01:00"]
            ),
            "A.PV": [10.1, 10.2],
            "B.PV": [20.1, 20.2],
        }
    )
    excel_path = tmp_path / "sample.xlsx"
    source.to_excel(excel_path, index=False, engine="openpyxl")
    csv_path = _write_file(
        tmp_path,
        b"Timestamp,A.PV,B.PV\n"
        b"2026-09-01 00:00:00,10.1,20.1\n"
        b"2026-09-01 00:01:00,10.2,20.2\n",
    )

    excel_frame = read_local_file(excel_path)
    csv_frame = read_local_file(csv_path)

    pd.testing.assert_frame_equal(excel_frame, csv_frame)


@pytest.mark.parametrize(
    ("filename", "data", "message"),
    [
        ("sample.csv", b"", "文件为空"),
        (
            "sample.csv",
            b"Timestamp\n2026-09-01 00:00:00\n",
            "没有有效数据列",
        ),
        ("sample.json", b"not a supported file", "不支持的文件类型"),
    ],
)
def test_local_file_validation_errors_are_clear(tmp_path, filename, data, message):
    with pytest.raises(ValueError, match=message):
        read_local_file(_write_file(tmp_path, data, filename))


def test_invalid_timestamp_is_rejected(tmp_path):
    path = _write_file(
        tmp_path,
        b"Timestamp,A.PV\nnot-a-timestamp,10.1\n",
    )

    with pytest.raises(ValueError, match="时间列无法解析"):
        read_local_file(path)


def test_multipart_csv_upload_uses_temp_path_and_one_shared_frame(monkeypatch):
    app_module = importlib.import_module("app")
    real_read = app_module.read_local_file
    real_store = app_module.store_dataframe
    read_paths = []
    stored = []

    def read(path):
        path = Path(path)
        read_paths.append(path)
        assert path.exists()
        assert path.suffix == ".csv"
        return real_read(path)

    def store(frame):
        stored.append(frame)
        real_store(frame)

    monkeypatch.setattr(app_module, "read_local_file", read)
    monkeypatch.setattr(app_module, "store_dataframe", store)

    response = _post_upload("../sample.csv", CSV_DATA.encode("utf-8"))

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["filename"] == "sample.csv"
    assert payload["rows"] == 2
    assert payload["columns"] == [
        "S_consumption_6h",
        "FICQ706004.PV",
        "FI706017.PV",
    ]
    assert len(read_paths) == 1
    assert not read_paths[0].exists()
    assert len(stored) == 1
    assert get_dataframe() is stored[0]

    figure, records, status = viewer.update_selected_view(["S_consumption_6h"])
    assert [trace.name for trace in figure.data] == ["S_consumption_6h"]
    assert records[0]["Tag"] == "S_consumption_6h"
    assert status == ""
    assert len(read_paths) == 1
    assert len(stored) == 1


def test_multipart_xlsx_upload_preserves_excel_support():
    source = pd.DataFrame(
        {
            "Timestamp": pd.to_datetime(["2026-09-01 00:00:00"]),
            "A.PV": [10.1],
        }
    )
    workbook = BytesIO()
    source.to_excel(workbook, index=False, engine="openpyxl")

    response = _post_upload("sample.xlsx", workbook.getvalue())

    assert response.status_code == 200
    assert response.get_json()["columns"] == ["A.PV"]
    frame = get_dataframe()
    assert frame is not None
    assert frame.index.name == "Timestamp"
    assert frame["A.PV"].tolist() == [10.1]


def test_multipart_upload_rejects_missing_or_unsupported_files():
    app_module = importlib.import_module("app")
    client = app_module.app.server.test_client()

    missing = client.post("/api/upload", data={}, content_type="multipart/form-data")
    unsupported = client.post(
        "/api/upload",
        data={"file": (BytesIO(b"not supported"), "sample.txt")},
        content_type="multipart/form-data",
    )

    assert missing.status_code == 400
    assert "请选择文件" in missing.get_json()["error"]
    assert unsupported.status_code == 400
    assert "不支持的文件类型" in unsupported.get_json()["error"]


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


def test_data_source_switch_does_not_reload_data(monkeypatch):
    frame = pd.DataFrame(
        {"TAG_A": [1.0]},
        index=pd.date_range("2024-01-01", periods=1, freq="min"),
    )
    pi_calls = []
    triggered = ["query-button"]

    def fake_pi(*args):
        pi_calls.append(args)
        return frame

    monkeypatch.setattr(viewer, "read_pi_data", fake_pi)
    monkeypatch.setattr(viewer, "_triggered_id", lambda: triggered[0])

    viewer.update_data_state(
        1, None, 0, "pi", "TAG_A", "2024-01-01", "2024-01-01 00:01"
    )
    assert len(pi_calls) == 1

    triggered[0] = "data-source"
    viewer.update_data_state(
        1, {"ok": True}, 0, "file", "TAG_A", "2024-01-01", "2024-01-01 00:01"
    )
    triggered[0] = "data-source"
    viewer.update_data_state(
        1, {"ok": True}, 0, "pi", "TAG_A", "2024-01-01", "2024-01-01 00:01"
    )
    assert len(pi_calls) == 1

    triggered[0] = "upload-result"
    state, selected = viewer.update_data_state(
        1, {"ok": True}, 0, "file", "TAG_A", "2024-01-01", "2024-01-01 00:01"
    )
    assert state["ready"] is True
    assert selected == ["TAG_A"]
    assert len(pi_calls) == 1


def test_production_upload_path_is_multipart_and_not_dash_base64():
    project_root = Path(__file__).resolve().parents[1]
    app_source = (project_root / "app.py").read_text(encoding="utf-8")
    viewer_source = (project_root / "pages" / "viewer.py").read_text(encoding="utf-8")
    asset_source = (project_root / "assets" / "upload.js").read_text(encoding="utf-8")

    assert "request.files" in app_source
    assert '"/api/upload"' in app_source
    assert "dcc.Upload" not in viewer_source
    assert 'Input("file-upload", "contents")' not in viewer_source
    assert "base64" not in viewer_source.lower()
    assert "FormData" in viewer_source
    assert 'fetch("/api/upload"' in viewer_source
    assert "base64" not in asset_source.lower()
    assert 'document.createElement("input")' in asset_source
    assert 'input.type = "file"' in asset_source


def test_data_loading_callback_uses_upload_result_as_input():
    from app import app

    callback = next(
        entry
        for entry in app.callback_map.values()
        if entry.get("callback")
        and entry["callback"].__name__ == "update_data_state"
    )
    assert "upload-result" in {item["id"] for item in callback["inputs"]}
    assert "file-upload" not in {item["id"] for item in callback["inputs"]}
    assert "data-source" in {item["id"] for item in callback["state"]}


def test_graphics_modules_do_not_read_from_pi():
    project_root = Path(__file__).resolve().parents[1]
    paths = [
        project_root / "backend" / "statistics.py",
        *[
            project_root / "charts" / f"{name}.py"
            for name in (
                "trend",
                "scatter",
                "histogram",
                "boxplot",
                "heatmap",
                "control_chart",
            )
        ],
    ]

    for path in paths:
        source = path.read_text(encoding="utf-8")
        assert "read_pi_data" not in source
        assert "PIReader.exe" not in source

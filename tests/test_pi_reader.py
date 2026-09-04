import json
import subprocess
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from backend import pi_reader


def test_read_pi_data_uses_pi_reader_json(monkeypatch, tmp_path):
    config_path = tmp_path / "config.txt"
    config_path.write_text("shared PIExport-format config", encoding="utf-8")
    executable = tmp_path / "PIReader.exe"
    executable.write_bytes(b"test executable")
    monkeypatch.setenv("PI_CONFIG", str(config_path))
    monkeypatch.setenv("PI_READER_EXE", str(executable))

    def fake_run(command, *, input, capture_output, text, encoding, errors, check, timeout):
        assert timeout == pi_reader.PI_READER_TIMEOUT_SECONDS
        assert command == [
            str(executable.resolve()),
            "--config",
            str(config_path.resolve()),
            "--tags",
            "-",
            "--start",
            "2024-01-01 00:00:00",
            "--end",
            "2024-01-01 00:02:00",
            "--interval",
            "5m",
        ]
        assert input == "TAG_A\nTAG_B\n"
        assert capture_output is True
        assert text is True
        assert encoding == "utf-8"
        assert errors == "strict"
        return subprocess.CompletedProcess(
            command,
            0,
            json.dumps(
                {
                    "columns": ["Timestamp", "TAG_A", "TAG_B"],
                    "data": [
                        ["2024-01-01 00:00:00", 85.2, 1.25],
                        ["2024-01-01 00:01:00", None, 1.26],
                    ],
                }
            ),
            "",
        )

    monkeypatch.setattr(pi_reader.subprocess, "run", fake_run)

    frame = pi_reader.read_pi_data(
        ["TAG_A", "TAG_A", "TAG_B"],
        datetime(2024, 1, 1),
        "2024-01-01 00:02:00",
        "5m",
    )

    assert isinstance(frame, pd.DataFrame)
    assert isinstance(frame.index, pd.DatetimeIndex)
    assert frame.index.name == "Timestamp"
    assert list(frame.columns) == ["TAG_A", "TAG_B"]
    assert frame.loc[pd.Timestamp("2024-01-01 00:00:00"), "TAG_A"] == 85.2
    assert pd.isna(frame.loc[pd.Timestamp("2024-01-01 00:01:00"), "TAG_A"])


def test_read_pi_data_forwards_pi_time_expressions(monkeypatch, tmp_path):
    config_path = tmp_path / "config.txt"
    config_path.write_text("shared PIExport-format config", encoding="utf-8")
    executable = tmp_path / "PIReader.exe"
    executable.write_bytes(b"test executable")
    monkeypatch.setenv("PI_CONFIG", str(config_path))
    monkeypatch.setenv("PI_READER_EXE", str(executable))

    def fake_run(command, **kwargs):
        assert command[command.index("--start") + 1] == "*-1h"
        assert command[command.index("--end") + 1] == "*"
        return subprocess.CompletedProcess(
            command,
            0,
            '{"columns": ["Timestamp", "TAG_A"], "data": []}',
            "",
        )

    monkeypatch.setattr(pi_reader.subprocess, "run", fake_run)

    frame = pi_reader.read_pi_data(["TAG_A"], "*-1h", "*")

    assert frame.empty
    assert list(frame.columns) == ["TAG_A"]


def test_pi_time_placeholders_document_supported_expressions():
    source = (Path(__file__).parents[1] / "pages" / "viewer.py").read_text(encoding="utf-8")

    assert source.count('placeholder="支持:\\n2026-09-01 00:00:00\\n*\\n*-1h"') == 2


def test_pi_reader_production_path_does_not_create_tags_file():
    source = Path(pi_reader.__file__).read_text(encoding="utf-8")

    assert "tags.txt" not in source
    assert "TemporaryDirectory" not in source
    assert "workdir" not in source


def test_pi_reader_program_supports_stdin_and_file_tags():
    source = (Path(__file__).parents[1] / "PIReader" / "Program.cs").read_text(encoding="utf-8")

    assert 'path == "-"' in source
    assert "Console.In" in source
    assert "File.ReadAllLines" in source
    assert "Console.InputEncoding = new UTF8Encoding(false);" in source
    assert "Console.OutputEncoding = new UTF8Encoding(false);" in source


def test_read_pi_data_preserves_columns_for_empty_json(monkeypatch, tmp_path):
    config_path = tmp_path / "config.txt"
    config_path.write_text("shared PIExport-format config", encoding="utf-8")
    executable = tmp_path / "PIReader.exe"
    executable.write_bytes(b"test executable")
    monkeypatch.setenv("PI_CONFIG", str(config_path))
    monkeypatch.setenv("PI_READER_EXE", str(executable))

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            0,
            '{"columns": ["Timestamp", "TAG_A", "TAG_B"], "data": []}',
            "",
        )

    monkeypatch.setattr(pi_reader.subprocess, "run", fake_run)

    frame = pi_reader.read_pi_data(
        ["TAG_A", "TAG_B"],
        datetime(2024, 1, 1),
        datetime(2024, 1, 1, 0, 2),
    )

    assert frame.empty
    assert isinstance(frame.index, pd.DatetimeIndex)
    assert list(frame.columns) == ["TAG_A", "TAG_B"]


def test_read_pi_data_rejects_invalid_json(monkeypatch, tmp_path):
    config_path = tmp_path / "config.txt"
    config_path.write_text("shared PIExport-format config", encoding="utf-8")
    executable = tmp_path / "PIReader.exe"
    executable.write_bytes(b"test executable")
    monkeypatch.setenv("PI_CONFIG", str(config_path))
    monkeypatch.setenv("PI_READER_EXE", str(executable))
    monkeypatch.setattr(
        pi_reader.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 0, "not-json", ""),
    )

    try:
        pi_reader.read_pi_data(["TAG_A"], datetime(2024, 1, 1), datetime(2024, 1, 1, 0, 1))
    except ValueError as error:
        assert str(error) == "PIReader returned invalid JSON"
    else:
        raise AssertionError("invalid PIReader JSON was accepted")


def test_read_pi_data_rejects_unsupported_interval(monkeypatch, tmp_path):
    config_path = tmp_path / "config.txt"
    config_path.write_text("shared PIExport-format config", encoding="utf-8")
    executable = tmp_path / "PIReader.exe"
    executable.write_bytes(b"test executable")
    monkeypatch.setenv("PI_CONFIG", str(config_path))
    monkeypatch.setenv("PI_READER_EXE", str(executable))

    with pytest.raises(ValueError, match="interval must be one of"):
        pi_reader.read_pi_data(
            ["TAG_A"],
            datetime(2024, 1, 1),
            datetime(2024, 1, 1, 0, 1),
            "2m",
        )


def test_read_pi_data_converts_timeout_to_user_error(monkeypatch, tmp_path):
    config_path = tmp_path / "config.txt"
    config_path.write_text("shared PIExport-format config", encoding="utf-8")
    executable = tmp_path / "PIReader.exe"
    executable.write_bytes(b"test executable")
    monkeypatch.setenv("PI_CONFIG", str(config_path))
    monkeypatch.setenv("PI_READER_EXE", str(executable))

    def fake_run(command, **kwargs):
        assert kwargs["timeout"] == pi_reader.PI_READER_TIMEOUT_SECONDS
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(pi_reader.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="PIReader 查询超时"):
        pi_reader.read_pi_data(
            ["TAG_A"],
            datetime(2024, 1, 1),
            datetime(2024, 1, 1, 0, 1),
        )

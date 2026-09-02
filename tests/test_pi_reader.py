import json
import subprocess
from datetime import datetime
from pathlib import Path

import pandas as pd

from backend import pi_reader


def test_read_pi_data_uses_pi_reader_json(monkeypatch, tmp_path):
    config_path = tmp_path / "config.txt"
    config_path.write_text("shared PIExport-format config", encoding="utf-8")
    executable = tmp_path / "PIReader.exe"
    executable.write_bytes(b"test executable")
    monkeypatch.setenv("PI_CONFIG", str(config_path))
    monkeypatch.setenv("PI_READER_EXE", str(executable))

    def fake_run(command, *, cwd, capture_output, text, check):
        assert command == [
            str(executable.resolve()),
            "--config",
            str(config_path.resolve()),
            "--tags",
            str(Path(cwd) / "tags.txt"),
            "--start",
            "2024-01-01 00:00:00",
            "--end",
            "2024-01-01 00:02:00",
        ]
        assert (Path(cwd) / "tags.txt").read_text(encoding="utf-8").splitlines() == [
            "TAG_A",
            "TAG_B",
        ]
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
    )

    assert isinstance(frame, pd.DataFrame)
    assert isinstance(frame.index, pd.DatetimeIndex)
    assert frame.index.name == "Timestamp"
    assert list(frame.columns) == ["TAG_A", "TAG_B"]
    assert frame.loc[pd.Timestamp("2024-01-01 00:00:00"), "TAG_A"] == 85.2
    assert pd.isna(frame.loc[pd.Timestamp("2024-01-01 00:01:00"), "TAG_A"])


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

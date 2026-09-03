"""Adapter for reading PI data through the standalone PIReader executable."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pandas as pd


_CONFIG_ENV = "PI_CONFIG"
_EXE_ENV = "PI_READER_EXE"
_PI_READER_EXE = "PIReader.exe"
_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
MAX_TAGS = 8
INTERVAL_OPTIONS = ("1m", "5m", "10m", "30m", "1h")
PI_READER_TIMEOUT_SECONDS = 300


def read_pi_data(tags, start_time, end_time, interval="1m") -> pd.DataFrame:
    """Return PI historical data as a pandas DataFrame."""

    normalized_tags = normalize_tags(tags)
    if interval not in INTERVAL_OPTIONS:
        raise ValueError(f"interval must be one of: {', '.join(INTERVAL_OPTIONS)}")
    start = _format_time(start_time, "start_time")
    end = _format_time(end_time, "end_time")
    if end <= start:
        raise ValueError("end_time must be later than start_time")

    config_path = _config_path()
    executable = _executable_path(config_path)

    tag_input = "\n".join(normalized_tags) + "\n"
    command = [
        str(executable),
        "--config",
        str(config_path),
        "--tags",
        "-",
        "--start",
        start,
        "--end",
        end,
        "--interval",
        interval,
    ]
    try:
        result = subprocess.run(
            command,
            input=tag_input,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            check=False,
            timeout=PI_READER_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            "PIReader 查询超时，请缩短时间范围或检查 PI Server 连接"
        ) from exc

    if result.returncode != 0:
        details = "\n".join(
            part.strip() for part in (result.stdout, result.stderr) if part and part.strip()
        )
        raise RuntimeError(
            "PIReader failed to return data" + (f": {details[-4000:]}" if details else "")
        )

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("PIReader returned invalid JSON") from exc
    return _read_reader_json(payload)


def _normalize_tags(tags) -> list[str]:
    if isinstance(tags, (str, bytes)):
        raise TypeError("tags must be an iterable of tag names")

    normalized: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        if not isinstance(tag, str):
            raise TypeError("each tag must be a string")
        tag = tag.strip()
        key = tag.casefold()
        if tag and not tag.startswith("#") and key not in seen:
            normalized.append(tag)
            seen.add(key)
    if not normalized:
        raise ValueError("tags must contain at least one tag name")
    return normalized


def normalize_tags(tags) -> list[str]:
    normalized = _normalize_tags(tags)
    if len(normalized) > MAX_TAGS:
        raise ValueError(f"Tag数量不能超过{MAX_TAGS}个")
    return normalized


def _format_time(value, name: str) -> str:
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} is not a valid datetime") from exc
    if pd.isna(timestamp) or timestamp.tzinfo is not None:
        raise ValueError(f"{name} must be a timezone-naive datetime")
    return timestamp.to_pydatetime().strftime(_TIME_FORMAT)


def _config_path() -> Path:
    configured = os.environ.get(_CONFIG_ENV)
    path = Path(configured).expanduser() if configured else Path.cwd() / "config.txt"
    if not path.is_file():
        raise FileNotFoundError(
            f"PI config not found: {path}. Set {_CONFIG_ENV} to the existing config.txt."
        )
    return path.resolve()


def _executable_path(config_path: Path) -> Path:
    configured = os.environ.get(_EXE_ENV)
    path = Path(configured).expanduser() if configured else config_path.with_name(_PI_READER_EXE)
    if not path.is_file():
        raise FileNotFoundError(
            f"PIReader executable not found: {path}. Set {_EXE_ENV} to PIReader.exe."
        )
    return path.resolve()


def _read_reader_json(payload) -> pd.DataFrame:
    if not isinstance(payload, dict):
        raise ValueError("PIReader JSON must be an object")

    columns = payload.get("columns")
    data = payload.get("data")
    if not isinstance(columns, list) or not columns or columns[0] != "Timestamp":
        raise ValueError("PIReader JSON is missing the Timestamp column")
    if not all(isinstance(column, str) for column in columns):
        raise ValueError("PIReader JSON columns must be strings")
    if not isinstance(data, list):
        raise ValueError("PIReader JSON data must be an array")
    if any(not isinstance(row, list) or len(row) != len(columns) for row in data):
        raise ValueError("PIReader JSON row width does not match columns")

    frame = pd.DataFrame(data, columns=columns)
    timestamps = pd.to_datetime(frame.pop("Timestamp"), errors="raise")
    frame.index = pd.DatetimeIndex(timestamps)
    frame.index.name = "Timestamp"
    return frame

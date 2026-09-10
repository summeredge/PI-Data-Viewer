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
        raise ValueError(f"采样间隔必须是以下选项之一：{', '.join(INTERVAL_OPTIONS)}")
    start = _format_time(start_time, "开始时间")
    end = _format_time(end_time, "结束时间")
    if not start.startswith("*") and not end.startswith("*") and end <= start:
        raise ValueError("结束时间必须晚于开始时间")

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
            "PIReader 查询超时，请缩短时间范围或检查 PI 服务器连接"
        ) from exc

    if result.returncode != 0:
        details = "\n".join(
            part.strip() for part in (result.stdout, result.stderr) if part and part.strip()
        )
        raise RuntimeError(
            "PIReader 未返回数据" + (f"：{details[-4000:]}" if details else "")
        )

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("PIReader 返回的 JSON 无效") from exc
    return _read_reader_json(payload)


def search_pi_tags(mask) -> list[str]:
    """Return PI tag names matching a server-side wildcard mask."""

    if not isinstance(mask, str) or not mask.strip():
        raise ValueError("请输入 Tag Mask")
    mask = mask.strip()
    if mask == "*":
        raise ValueError("搜索条件不能为 *，请缩小条件")

    config_path = _config_path()
    executable = _executable_path(config_path)
    command = [
        str(executable),
        "--config",
        str(config_path),
        "--search",
        "--mask",
        mask,
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            check=False,
            timeout=PI_READER_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("PIReader 搜索超时，请检查 PI 服务器连接") from exc

    if result.returncode != 0:
        details = "\n".join(
            part.strip() for part in (result.stdout, result.stderr) if part and part.strip()
        )
        raise RuntimeError("PIReader 搜索失败" + (f"：{details[-4000:]}" if details else ""))

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("PIReader 搜索返回的 JSON 无效") from exc
    if not isinstance(payload, dict):
        raise ValueError("PIReader 搜索 JSON 必须是对象")

    tags = payload.get("tags")
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        raise ValueError("PIReader 搜索 JSON 缺少有效的 tags 数组")
    if payload.get("truncated"):
        raise RuntimeError(payload.get("message") or "搜索结果超过限制，请缩小条件")
    return tags


def _normalize_tags(tags) -> list[str]:
    if isinstance(tags, (str, bytes)):
        raise TypeError("位号必须是可迭代集合")

    normalized: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        if not isinstance(tag, str):
            raise TypeError("每个位号必须是字符串")
        tag = tag.strip()
        key = tag.casefold()
        if tag and not tag.startswith("#") and key not in seen:
            normalized.append(tag)
            seen.add(key)
    if not normalized:
        raise ValueError("请至少提供一个位号")
    return normalized


def normalize_tags(tags) -> list[str]:
    normalized = _normalize_tags(tags)
    if len(normalized) > MAX_TAGS:
        raise ValueError(f"位号数量不能超过{MAX_TAGS}个")
    return normalized


def _format_time(value, name: str) -> str:
    if isinstance(value, str):
        value = value.strip()
        if value:
            if value.startswith("*"):
                return value
        else:
            raise ValueError(f"{name}无效")

    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name}无效") from exc
    if pd.isna(timestamp) or timestamp.tzinfo is not None:
        raise ValueError(f"{name}不能包含时区")
    return timestamp.to_pydatetime().strftime(_TIME_FORMAT)


def _config_path() -> Path:
    configured = os.environ.get(_CONFIG_ENV)
    path = Path(configured).expanduser() if configured else Path.cwd() / "config.txt"
    if not path.is_file():
        raise FileNotFoundError(
            f"找不到 PI 配置文件：{path}。请将 {_CONFIG_ENV} 指向现有的 config.txt。"
        )
    return path.resolve()


def _executable_path(config_path: Path) -> Path:
    configured = os.environ.get(_EXE_ENV)
    path = Path(configured).expanduser() if configured else config_path.with_name(_PI_READER_EXE)
    if not path.is_file():
        raise FileNotFoundError(
            f"找不到 PIReader 程序：{path}。请将 {_EXE_ENV} 指向 PIReader.exe。"
        )
    return path.resolve()


def _read_reader_json(payload) -> pd.DataFrame:
    if not isinstance(payload, dict):
        raise ValueError("PIReader JSON 必须是对象")

    columns = payload.get("columns")
    data = payload.get("data")
    if not isinstance(columns, list) or not columns or columns[0] != "Timestamp":
        raise ValueError("PIReader JSON 缺少 Timestamp 列")
    if not all(isinstance(column, str) for column in columns):
        raise ValueError("PIReader JSON 列名必须是字符串")
    if not isinstance(data, list):
        raise ValueError("PIReader JSON 数据必须是数组")
    if any(not isinstance(row, list) or len(row) != len(columns) for row in data):
        raise ValueError("PIReader JSON 行宽与列数不一致")

    frame = pd.DataFrame(data, columns=columns)
    timestamps = pd.to_datetime(frame.pop("Timestamp"), errors="raise")
    frame.index = pd.DatetimeIndex(timestamps)
    frame.index.name = "Timestamp"
    return frame

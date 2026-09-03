"""Read uploaded CSV/XLSX files into the Viewer DataFrame format."""

from __future__ import annotations

import base64
import binascii
from io import BytesIO
from pathlib import Path

import pandas as pd


_SUPPORTED_EXTENSIONS = {".csv", ".xlsx"}
_CSV_FALLBACK_ENCODINGS = ("gb18030", "cp1252")


def read_local_file(contents: str, filename: str) -> pd.DataFrame:
    """Decode a Dash upload and return a standardized numeric DataFrame."""

    suffix = Path(filename).suffix.lower() if isinstance(filename, str) else ""
    if suffix not in _SUPPORTED_EXTENSIONS:
        raise ValueError("不支持的文件类型，仅支持 .csv 和 .xlsx")

    raw = _decode_upload(contents)
    try:
        if suffix == ".csv":
            frame = _read_csv(raw)
        else:
            frame = pd.read_excel(BytesIO(raw), sheet_name=0, engine="openpyxl")
    except pd.errors.EmptyDataError as exc:
        raise ValueError("文件为空") from exc
    except ImportError as exc:
        raise ValueError("读取 Excel 需要安装 openpyxl") from exc
    except Exception as exc:
        raise ValueError(f"文件无法读取：{exc}") from exc

    return _standardize_frame(frame)


def _read_csv(raw: bytes) -> pd.DataFrame:
    try:
        return pd.read_csv(BytesIO(raw))
    except UnicodeDecodeError:
        for encoding in _CSV_FALLBACK_ENCODINGS:
            try:
                return pd.read_csv(BytesIO(raw), encoding=encoding)
            except UnicodeDecodeError:
                continue
        raise


def _decode_upload(contents: str) -> bytes:
    if not isinstance(contents, str) or not contents:
        raise ValueError("文件为空")

    payload = contents.split(",", 1)[-1]
    try:
        raw = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("文件内容无法读取") from exc
    if not raw:
        raise ValueError("文件为空")
    return raw


def _standardize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.shape[1] < 2:
        raise ValueError("没有有效数据列")
    if frame.empty:
        raise ValueError("文件为空")

    timestamps = pd.to_datetime(frame.iloc[:, 0], errors="coerce")
    if timestamps.isna().any():
        raise ValueError("时间列无法解析")

    values = frame.iloc[:, 1:].apply(pd.to_numeric, errors="coerce")
    if not values.notna().any().any():
        raise ValueError("没有有效数据列")

    values.index = pd.DatetimeIndex(timestamps)
    values.index.name = "Timestamp"
    return values

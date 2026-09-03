"""Read local CSV/XLSX paths into the Viewer DataFrame format."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


_SUPPORTED_EXTENSIONS = {".csv", ".xlsx"}
_CSV_ENCODINGS = ("utf-8", "utf-8-sig", "gb18030", "gbk")


def read_local_file(path: Path | str) -> pd.DataFrame:
    """Read a local CSV/XLSX path and return a standardized numeric DataFrame."""

    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in _SUPPORTED_EXTENSIONS:
        raise ValueError("不支持的文件类型，仅支持 .csv 和 .xlsx")

    try:
        if suffix == ".csv":
            frame = _read_csv(path)
        else:
            frame = pd.read_excel(path, sheet_name=0, engine="openpyxl")
    except pd.errors.EmptyDataError as exc:
        raise ValueError("文件为空") from exc
    except ImportError as exc:
        raise ValueError("读取 Excel 需要安装 openpyxl") from exc
    except Exception as exc:
        raise ValueError(f"文件无法读取：{exc}") from exc

    return _standardize_frame(frame)


def _read_csv(path: Path) -> pd.DataFrame:
    last_error = None
    for encoding in _CSV_ENCODINGS:
        try:
            return pd.read_csv(path, encoding=encoding)
        except pd.errors.EmptyDataError:
            raise
        except (UnicodeDecodeError, pd.errors.ParserError, ValueError) as exc:
            last_error = exc
    raise ValueError("CSV 文件无法读取，已尝试 utf-8、utf-8-sig、gb18030、gbk 编码") from last_error


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

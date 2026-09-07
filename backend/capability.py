"""Normal process capability calculations for individual observations."""

from __future__ import annotations

import numpy as np
import pandas as pd

from backend.spc import calculate_imr


NO_VALID_DATA_MESSAGE = "所选变量无有效数值数据"
INSUFFICIENT_DATA_MESSAGE = "有效数值点不足，至少需要 3 个有限数值点"
INSUFFICIENT_VARIATION_MESSAGE = "数据波动不足，无法计算过程能力"
SPECIFICATION_REQUIRED_MESSAGE = "LSL 和 USL 不能同时为空"


def _coerce_limit(value, label: str) -> float | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{label}必须是有限数值")
    try:
        limit = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{label}必须是有限数值") from exc
    if not np.isfinite(limit):
        raise ValueError(f"{label}必须是有限数值")
    return limit


def _capability_indices(
    mean: float,
    sigma: float,
    lsl: float | None,
    usl: float | None,
) -> tuple[float | None, float | None]:
    cpl = (mean - lsl) / (3 * sigma) if lsl is not None else None
    cpu = (usl - mean) / (3 * sigma) if usl is not None else None
    cp = (usl - lsl) / (6 * sigma) if lsl is not None and usl is not None else None
    if cpl is not None and cpu is not None:
        cpk = min(cpl, cpu)
    else:
        cpk = cpl if cpl is not None else cpu
    return cp, cpk


def calculate_normal_capability(
    series: pd.Series,
    lsl: float | None = None,
    usl: float | None = None,
) -> dict[str, object]:
    """Calculate normal capability indices for a single observation series."""

    if not isinstance(series, pd.Series):
        raise TypeError("series must be a pandas Series")

    lsl = _coerce_limit(lsl, "LSL")
    usl = _coerce_limit(usl, "USL")
    if lsl is None and usl is None:
        raise ValueError(SPECIFICATION_REQUIRED_MESSAGE)
    if lsl is not None and usl is not None and lsl >= usl:
        raise ValueError("LSL 必须小于 USL")

    # calculate_imr preserves gaps, so moving ranges never bridge invalid rows.
    imr = calculate_imr(series, tests=[])
    values = imr["values"]
    valid_values = values.dropna()
    sample_size = len(valid_values)
    if sample_size == 0:
        raise ValueError(NO_VALID_DATA_MESSAGE)
    if sample_size < 3:
        raise ValueError(INSUFFICIENT_DATA_MESSAGE)

    mean = float(valid_values.mean())
    within_sigma = float(imr["sigma"])
    overall_sigma = float(valid_values.std(ddof=1))
    if (
        not np.isfinite(mean)
        or not np.isfinite(within_sigma)
        or not np.isfinite(overall_sigma)
        or within_sigma <= 0
        or overall_sigma <= 0
    ):
        raise ValueError(INSUFFICIENT_VARIATION_MESSAGE)

    cp, cpk = _capability_indices(mean, within_sigma, lsl, usl)
    pp, ppk = _capability_indices(mean, overall_sigma, lsl, usl)
    cpl = (mean - lsl) / (3 * within_sigma) if lsl is not None else None
    cpu = (usl - mean) / (3 * within_sigma) if usl is not None else None
    ppl = (mean - lsl) / (3 * overall_sigma) if lsl is not None else None
    ppu = (usl - mean) / (3 * overall_sigma) if usl is not None else None
    metrics = (cp, cpk, pp, ppk, cpl, cpu, ppl, ppu)
    if any(value is not None and not np.isfinite(value) for value in metrics):
        raise ValueError("无法计算有效的过程能力指标")

    return {
        "values": values,
        "sample_size": sample_size,
        "mean": mean,
        "lsl": lsl,
        "usl": usl,
        "within_sigma": within_sigma,
        "overall_sigma": overall_sigma,
        "cpl": cpl,
        "cpu": cpu,
        "cp": cp,
        "cpk": cpk,
        "ppl": ppl,
        "ppu": ppu,
        "pp": pp,
        "ppk": ppk,
    }

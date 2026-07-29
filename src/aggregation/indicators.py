# src/aggregation/indicators.py
from __future__ import annotations

import pandas as pd

from config.rules_loader import RULES


def compute_pct_critical(
    historic_df: pd.DataFrame, region_id: int, n_weeks: int | None = None
) -> float:
    """Fraction (0-1) of the last `n_weeks` (default RULES.window_weeks) of
    historic data for `region_id` where CDI reached the critical threshold."""
    _n = n_weeks if n_weeks is not None else RULES.window_weeks
    region = historic_df[historic_df["drought_region_id"] == region_id].copy()
    region = region.sort_values("measured_at").tail(_n)
    if region.empty:
        return 0.0
    return float((region["cdi"] >= RULES.cdi_critical_min).sum() / len(region))


def compute_percentile(value: float, series: pd.Series) -> int:
    """Percentile rank (0-100) of `value` within `series`, ignoring NaNs.
    Returns 50 (median) when `series` has no usable data."""
    clean = series.dropna()
    if len(clean) == 0:
        return 50
    return int(round((clean < value).mean() * 100))


def compute_trend(current: float, prior: float) -> int:
    """Sign of the change from `prior` to `current`: 1 = increased,
    -1 = decreased, 0 = unchanged."""
    if current > prior:
        return 1
    if current < prior:
        return -1
    return 0

# src/aggregation/indicators.py
from __future__ import annotations

import pandas as pd


def compute_pct_critical(
    historic_df: pd.DataFrame, region_id: int, n_weeks: int = 52
) -> float:
    region = historic_df[historic_df["drought_region_id"] == region_id].copy()
    region = region.sort_values("measured_at").tail(n_weeks)
    if region.empty:
        return 0.0
    return float((region["cdi"] >= 3).sum() / len(region))


def compute_percentile(value: float, series: pd.Series) -> int:
    clean = series.dropna()
    if len(clean) == 0:
        return 50
    return int(round((clean < value).mean() * 100))


def compute_trend(current: float, prior: float) -> int:
    if current > prior:
        return 1
    if current < prior:
        return -1
    return 0

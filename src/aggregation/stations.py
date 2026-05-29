# src/aggregation/stations.py
from __future__ import annotations

from collections.abc import Collection

import pandas as pd

from src.models import DataBundle, DischargeStats

_DISCHARGE_LABEL = "Abfluss"


def compute_discharge_stats(region_ids: Collection[int], bundle: DataBundle) -> DischargeStats:
    """Count discharge stations in the given regions with low / very low flow.

    Low      = current value < threshold1 (at the station's current day-of-year).
    Very low = current value < q347 (subset of low).
    Only stations with label == "Abfluss" and a matching reference row are counted.
    """
    region_set = set(region_ids)
    current = bundle.current_stations_df
    reference = bundle.reference_stations_df
    if current.empty or reference.empty:
        return DischargeStats(n_total=0, n_low=0, n_very_low=0, pct_low=0)

    cur = current[current["label"] == _DISCHARGE_LABEL].copy()
    cur = cur[cur["hydro_station_id"].map(bundle.station_region_map).isin(region_set)]
    if cur.empty:
        return DischargeStats(n_total=0, n_low=0, n_very_low=0, pct_low=0)

    cur["doy"] = pd.to_datetime(cur["measured_at"]).dt.dayofyear

    ref = reference[reference["label"] == _DISCHARGE_LABEL][
        ["hydro_station_id", "doy", "threshold1", "q347"]
    ]
    merged = cur.merge(ref, on=["hydro_station_id", "doy"], how="inner")
    merged = merged.dropna(subset=["threshold1", "q347", "value"])

    n_total = len(merged)
    if n_total == 0:
        return DischargeStats(n_total=0, n_low=0, n_very_low=0, pct_low=0)

    n_low = int((merged["value"] < merged["threshold1"]).sum())
    n_very_low = int((merged["value"] < merged["q347"]).sum())
    pct_low = round(n_low / n_total * 100)
    return DischargeStats(n_total=n_total, n_low=n_low, n_very_low=n_very_low, pct_low=pct_low)

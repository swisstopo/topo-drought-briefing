# src/aggregation/regional.py
from __future__ import annotations

import math
from datetime import datetime

import pandas as pd

from config.settings import BERNE_REGION_NAMES
from src.aggregation.indicators import compute_pct_critical, compute_percentile, compute_trend
from src.models import DataBundle, RegionReport
from src.quality.checks import run_quality_checks


def compute_region_report(region_id: int, bundle: DataBundle) -> RegionReport:
    # --- Current snapshot (latest row for this region) ---
    current = bundle.current_df[bundle.current_df["drought_region_id"] == region_id]
    current = current.sort_values("measured_at")
    # Drop trailing rows with no actual data (all-NaN placeholder rows)
    current = current[current["cdi"].notna()]
    if current.empty:
        raise ValueError(f"No current data for region {region_id}")

    row = current.iloc[-1]
    prior_row = current.iloc[-2] if len(current) >= 2 else None

    def _safe(val: object) -> float:
        if val is None:
            return float("nan")
        if isinstance(val, float) and math.isnan(val):
            return float("nan")
        if pd.isna(val):
            return float("nan")
        return float(val)

    cdi = int(row["cdi"]) if not pd.isna(row["cdi"]) else 0
    spi_3m = _safe(row["spi_3m"])
    soil_moisture_pct = _safe(row["soil_moisture_ufc"])
    vhi = _safe(row["vhi"])

    # --- Trends vs prior week ---
    if prior_row is not None:
        prior_cdi = int(prior_row["cdi"]) if not pd.isna(prior_row["cdi"]) else cdi
        prior_spi = _safe(prior_row["spi_3m"])
        prior_vhi = _safe(prior_row["vhi"])
        cdi_trend = compute_trend(cdi, prior_cdi)
        spi_3m_delta = spi_3m - prior_spi if not math.isnan(spi_3m) and not math.isnan(prior_spi) else 0.0
        vhi_delta = vhi - prior_vhi if not math.isnan(vhi) and not math.isnan(prior_vhi) else 0.0
    else:
        cdi_trend = 0
        spi_3m_delta = 0.0
        vhi_delta = 0.0

    # --- 52-week pct_critical from historic ---
    pct_critical = compute_pct_critical(bundle.historic_df, region_id)

    # --- SPI-3m percentile vs historic distribution ---
    hist_region = bundle.historic_df[bundle.historic_df["drought_region_id"] == region_id]
    spi_3m_percentile = (
        compute_percentile(spi_3m, hist_region["spi_3m"])
        if not math.isnan(spi_3m)
        else 50
    )

    # --- Quality ---
    hist_spi_series = hist_region["spi_3m"] if not hist_region.empty else None
    quality = run_quality_checks(row, bundle.data_timestamp, spi_3m_reference=hist_spi_series)

    return RegionReport(
        region_id=region_id,
        region_name_de=BERNE_REGION_NAMES.get(region_id, f"Region {region_id}"),
        data_timestamp=bundle.data_timestamp,
        source=bundle.source,
        cdi=cdi,
        spi_3m=spi_3m,
        soil_moisture_pct=soil_moisture_pct,
        vhi=vhi,
        cdi_trend=cdi_trend,
        spi_3m_delta=spi_3m_delta,
        vhi_delta=vhi_delta,
        pct_critical=pct_critical,
        spi_3m_percentile=spi_3m_percentile,
        quality=quality,
    )

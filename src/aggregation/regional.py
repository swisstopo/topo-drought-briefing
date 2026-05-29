# src/aggregation/regional.py
from __future__ import annotations

import math
from datetime import datetime, timedelta

import pandas as pd

from config.settings import REGION_NAMES_DE
from src.aggregation.indicators import compute_pct_critical, compute_percentile, compute_trend
from src.aggregation.stations import compute_discharge_stats
from src.models import DataBundle, RegionReport, WarnkarteEntry
from src.quality.checks import run_quality_checks


def compute_region_report(
    region_id: int,
    bundle: DataBundle,
    warnkarte_entry: WarnkarteEntry | None = None,
    vhi_value: float | None = None,
) -> RegionReport:
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
    vhi = float(vhi_value) if vhi_value is not None else _safe(row["vhi"])

    # --- Trends vs prior week ---
    if prior_row is not None:
        prior_cdi = int(prior_row["cdi"]) if not pd.isna(prior_row["cdi"]) else cdi
        prior_spi = _safe(prior_row["spi_3m"])
        cdi_trend = compute_trend(cdi, prior_cdi)
        spi_3m_delta = spi_3m - prior_spi if not math.isnan(spi_3m) and not math.isnan(prior_spi) else 0.0
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

    precip_sum_1m = _safe(row.get("precip_sum_1m"))
    precip_sum_3m = _safe(row.get("precip_sum_3m"))
    precip_1m_index = (
        int(row["precip_1m_index"])
        if not pd.isna(row.get("precip_1m_index"))
        else 1
    )
    soil_moisture_index = (
        int(row["soil_moisture_index"])
        if not pd.isna(row.get("soil_moisture_index"))
        else 1
    )
    hydro_index = (
        int(row["hydro_index"])
        if not pd.isna(row.get("hydro_index"))
        else 1
    )
    cdi_forecast_week2 = _compute_cdi_forecast_week2(bundle, region_id)
    precip_1m_index_forecast = _forecast_week2_value(bundle, region_id, "precip_1m_index_p50")
    soil_moisture_index_forecast = _forecast_week2_value(bundle, region_id, "soil_moisture_index_p50")
    precip_deficit_delta = (
        precip_1m_index_forecast - precip_1m_index
        if precip_1m_index_forecast is not None else 0
    )
    soil_moisture_deficit_delta = (
        soil_moisture_index_forecast - soil_moisture_index
        if soil_moisture_index_forecast is not None else 0
    )
    discharge = compute_discharge_stats([region_id], bundle)
    if warnkarte_entry is not None:
        warnlevel = warnkarte_entry.warnlevel
        warnlevel_info_de = warnkarte_entry.info_de
        warnlevel_info_fr = warnkarte_entry.info_fr
    else:
        warnlevel = max(cdi, 1)
        warnlevel_info_de = ""
        warnlevel_info_fr = ""

    return RegionReport(
        region_id=region_id,
        region_name_de=REGION_NAMES_DE.get(region_id, f"Region {region_id}"),
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
        precip_sum_1m=precip_sum_1m,
        precip_sum_3m=precip_sum_3m,
        precip_1m_index=precip_1m_index,
        soil_moisture_index=soil_moisture_index,
        hydro_index=hydro_index,
        warnlevel=warnlevel,
        warnlevel_info_de=warnlevel_info_de,
        warnlevel_info_fr=warnlevel_info_fr,
        cdi_forecast_week2=cdi_forecast_week2,
        precip_1m_index_forecast=precip_1m_index_forecast,
        soil_moisture_index_forecast=soil_moisture_index_forecast,
        precip_deficit_delta=precip_deficit_delta,
        soil_moisture_deficit_delta=soil_moisture_deficit_delta,
        discharge=discharge,
    )


def _forecast_week2_value(bundle: DataBundle, region_id: int, column: str) -> int | None:
    """Return the week-2 (~+14d) p50 value of `column` for a region, or None."""
    forecast = bundle.forecast_df
    if forecast.empty or column not in forecast.columns:
        return None
    target_date = bundle.data_timestamp + timedelta(days=14)
    region_forecast = forecast[forecast["drought_region_id"] == region_id]
    if region_forecast.empty:
        return None
    region_forecast = region_forecast.copy()
    region_forecast["delta"] = (region_forecast["valid_at"] - target_date).abs()
    closest = region_forecast.sort_values("delta").iloc[0]
    if closest["delta"] > pd.Timedelta(days=5):
        return None
    if pd.isna(closest.get(column)):
        return None
    return int(closest[column])


def _compute_cdi_forecast_week2(bundle: DataBundle, region_id: int) -> int | None:
    """Return the CDI forecast for valid_at ≈ today + 14 d. None if forecast horizon is shorter."""
    return _forecast_week2_value(bundle, region_id, "cdi_p50")

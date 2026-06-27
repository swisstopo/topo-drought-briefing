# src/models.py
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
import pandas as pd


@dataclass
class HydroStationReport:
    station_id: str
    station_name: str
    current_value: float
    threshold1: float
    min_value: float


@dataclass
class DataBundle:
    current_df: pd.DataFrame
    historic_df: pd.DataFrame
    reference_df: pd.DataFrame
    data_timestamp: datetime
    source: Literal["api", "fixture"]
    forecast_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    current_stations_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    reference_stations_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    station_region_map: dict[str, int] = field(default_factory=dict)


@dataclass
class QualityReport:
    data_age_days: int
    coverage_pct: float
    missing_columns: list[str]
    outlier_flags: list[str]
    is_stale: bool
    overall: Literal["ok", "warning", "error"]


@dataclass
class DischargeStats:
    n_total: int      # discharge stations with a usable reference row
    n_low: int        # current value < threshold1
    n_very_low: int   # current value < q347 (subset of n_low)
    pct_low: int      # round(n_low / n_total * 100); 0 when n_total == 0


@dataclass
class RegionReport:
    region_id: int
    region_name_de: str
    data_timestamp: datetime
    source: Literal["api", "fixture"]
    cdi: int
    spi_3m: float
    soil_moisture_pct: float
    vhi: float
    cdi_trend: int  # -1 improving, 0 stable, +1 worsening
    spi_3m_delta: float
    vhi_delta: float
    pct_critical: float  # fraction of last 52 weeks with CDI >= 3
    spi_3m_percentile: int  # vs historic distribution
    quality: QualityReport
    # New fields added 2026-05-28 (defaults preserve backward compat until step 3)
    precip_sum_1m: float = 0.0
    precip_sum_3m: float = 0.0
    precip_1m_index: int = 1
    soil_moisture_index: int = 1
    hydro_index: int = 1
    warnlevel: int = 1
    warnlevel_info_de: str = ""
    warnlevel_info_fr: str = ""
    cdi_forecast_week2: int | None = None
    precip_1m_index_forecast: int | None = None
    soil_moisture_index_forecast: int | None = None
    precip_deficit_delta: int = 0
    soil_moisture_deficit_delta: int = 0
    vhi_index: int = 1
    discharge: DischargeStats = field(default_factory=lambda: DischargeStats(0, 0, 0, 0))
    hydro_stations: list[HydroStationReport] = field(default_factory=list)


@dataclass
class CantonReport:
    canton_id: int
    canton_name_de: str
    canton_name_fr: str
    data_timestamp: datetime
    source: Literal["api", "fixture"]
    regions: list[RegionReport]
    max_warnlevel: int                                  # 1-5
    max_warnlevel_info_de: str
    max_warnlevel_info_fr: str
    n_regions_by_precip_index: dict[int, int]           
    n_regions_by_soil_moisture_index: dict[int, int]
    n_regions_by_hydro_index: dict[int, int]
    quality: QualityReport
    n_regions_dry: int = 0
    cdi_min_dry: int | None = None
    cdi_max_dry: int | None = None
    cdi_situation_delta: int = 0
    mean_precip_sum_1m: float = 0.0
    mean_precip_sum_3m: float = 0.0
    precip_index_min: int = 1
    precip_index_max: int = 1
    n_regions_with_precip_deficit: int = 0
    n_regions_with_soil_moisture_deficit: int = 0
    n_regions_with_vhi_stress: int = 0
    max_vhi_index: int = 1
    discharge: DischargeStats = field(default_factory=lambda: DischargeStats(0, 0, 0, 0))


@dataclass
class WarnkarteEntry:
    drought_region_id: int
    warnlevel: int          # 1-5 (BAFU Gefahrenstufe)
    info_de: str
    info_fr: str
    info_it: str
    valid_from: datetime


@dataclass
class MapSpec:
    id: str
    title_de: str
    title_fr: str
    source: str             
    style: str              


@dataclass
class BriefingDocument:
    sections: dict[str, str]
    report: object                        # CantonReport or RegionReport
    locale: str = "de"
    generated_at: datetime = field(default_factory=datetime.now)
    lead_maps: list = field(default_factory=list)   # list[MapSpec]
    lead_headline: str = ""
    lead_meta: str = ""
    banner: list = field(default_factory=list)                 # list[dict]: {label, url}
    weiterfuehrende_links: list = field(default_factory=list)  # list[dict]: {label, url}

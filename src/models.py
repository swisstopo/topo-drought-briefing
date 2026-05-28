# src/models.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
import pandas as pd


@dataclass
class DataBundle:
    current_df: pd.DataFrame
    historic_df: pd.DataFrame
    reference_df: pd.DataFrame
    data_timestamp: datetime
    source: Literal["api", "fixture"]


@dataclass
class QualityReport:
    data_age_days: int
    coverage_pct: float
    missing_columns: list[str]
    outlier_flags: list[str]
    is_stale: bool
    overall: Literal["ok", "warning", "error"]


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
    cdi_trend: int          # -1 improving, 0 stable, +1 worsening
    spi_3m_delta: float
    vhi_delta: float
    pct_critical: float     # fraction of last 52 weeks with CDI >= 3
    spi_3m_percentile: int  # vs historic distribution
    quality: QualityReport


@dataclass
class MapSpec:
    id: str
    title_de: str
    title_fr: str
    source: str            # path expression into CantonReport, e.g. "canton.regions[*].cdi"
    style: str             # renderer hint, e.g. "choropleth_warnregionen"


@dataclass
class BriefingDocument:
    sections: dict[str, str]   # keys: "lage", "entwicklung", "einordnung", "datengrundlage"
    report: RegionReport
    mode: str                   # "behoerden" | "bulletin"
    generated_at: datetime

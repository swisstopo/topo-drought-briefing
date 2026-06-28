# src/data/fixture_loader.py
"""
Reads the bundled ZIP fixtures from data/ into a DataBundle.

CSV format: semicolon-separated; comment lines start with '#'.
Date format in data: DD.MM.YYYY
"""
from __future__ import annotations

import io
import json
import logging
import re
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd

from config.settings import (
    CURRENT_STATIONS_CSV,
    CURRENT_ZIP_NAME,
    DATA_DIR,
    HISTORIC_ZIP_NAME,
    REFERENCE_STATIONS_CSV,
    REFERENCE_ZIP_NAME,
    STATION_REGION_MAP_NAME,
)
from src.models import DataBundle

logger = logging.getLogger(__name__)


def _read_csv_from_zip(zip_path: Path, filename: str) -> tuple[pd.DataFrame, list[str]]:
    if not zip_path.exists():
        raise FileNotFoundError(
            f"Fixture ZIP not found: {zip_path}. "
            "Ensure data/ directory contains the bundled files."
        )
    with zipfile.ZipFile(zip_path) as z:
        with z.open(filename) as f:
            raw = f.read().decode("utf-8", errors="replace")
    lines = raw.splitlines()
    comment_lines = [line for line in lines if line.startswith("#")]
    data_lines = [line for line in lines if not line.startswith("#") and line.strip()]
    df = pd.read_csv(io.StringIO("\n".join(data_lines)), sep=";")
    return df, comment_lines


def _parse_timestamp(comment_lines: list[str]) -> datetime:
    for line in comment_lines:
        m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", line)
        if m:
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return datetime(y, mo, d)
    logger.warning("Could not parse data_timestamp from comment lines; using today's date. "
                   "Staleness checks may be inaccurate.")
    return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)


def load_station_region_map() -> dict[str, int]:
    """Load the curated station→region mapping (a local artifact, not in STAC)."""
    map_path = DATA_DIR / STATION_REGION_MAP_NAME
    if not map_path.exists():
        return {}
    raw_map = json.loads(map_path.read_text(encoding="utf-8"))
    return {str(k).strip(): int(v) for k, v in raw_map.items()}


def _read_stations_csv(zip_path: Path, filename: str) -> pd.DataFrame:
    """Read a station CSV, forcing hydro_station_id to str (leading zeros matter)."""
    if not zip_path.exists():
        raise FileNotFoundError(f"Fixture ZIP not found: {zip_path}.")
    with zipfile.ZipFile(zip_path) as z:
        with z.open(filename) as f:
            raw = f.read().decode("utf-8", errors="replace")
    data_lines = [ln for ln in raw.splitlines() if not ln.startswith("#") and ln.strip()]
    df = pd.read_csv(io.StringIO("\n".join(data_lines)), sep=";", dtype={"hydro_station_id": str})
    df["hydro_station_id"] = df["hydro_station_id"].str.strip()
    if "measured_at" in df.columns:
        df["measured_at"] = pd.to_datetime(df["measured_at"], format="%d.%m.%Y", errors="coerce")
    return df


def _parse_dates(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "measured_at" in df.columns:
        df["measured_at"] = pd.to_datetime(df["measured_at"], format="%d.%m.%Y", errors="coerce")
    return df


def load() -> DataBundle:
    current_df, comment_lines = _read_csv_from_zip(
        DATA_DIR / CURRENT_ZIP_NAME, "weekly_current_regions.csv"
    )
    historic_df, _ = _read_csv_from_zip(
        DATA_DIR / HISTORIC_ZIP_NAME, "weekly_historic_regions.csv"
    )
    reference_df, _ = _read_csv_from_zip(
        DATA_DIR / REFERENCE_ZIP_NAME, "regions.csv"
    )
    forecast_raw, _ = _read_csv_from_zip(
        DATA_DIR / CURRENT_ZIP_NAME, "weekly_forecast_regions.csv"
    )
    
    forecast_df = forecast_raw.copy()
    forecast_df["valid_at"] = pd.to_datetime(forecast_df["valid_at"], format="%d.%m.%Y", errors="coerce")
    data_timestamp = _parse_timestamp(comment_lines)

    current_stations_df = _read_stations_csv(DATA_DIR / CURRENT_ZIP_NAME, CURRENT_STATIONS_CSV)
    reference_stations_df = _read_stations_csv(DATA_DIR / REFERENCE_ZIP_NAME, REFERENCE_STATIONS_CSV)
    station_region_map = load_station_region_map()

    try:
        stations_df = _read_stations_csv(DATA_DIR / REFERENCE_ZIP_NAME, "stations.csv")
        station_names = dict(zip(stations_df["hydro_station_id"], stations_df["name"]))
    except (FileNotFoundError, KeyError) as e:
        logger.warning("Could not load stations.csv: %s", e)
        station_names = {}

    return DataBundle(
        current_df=_parse_dates(current_df),
        historic_df=_parse_dates(historic_df),
        reference_df=reference_df,
        forecast_df=forecast_df,
        current_stations_df=current_stations_df,
        reference_stations_df=reference_stations_df,
        station_region_map=station_region_map,
        station_names=station_names,
        data_timestamp=data_timestamp,
        source="fixture",
    )

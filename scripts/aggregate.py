"""
scripts/aggregate.py

Purpose : Load raw source datasets, run all regional and cantonal aggregations,
          and write JSON outputs to data/processed/.
          Falls back to bundled fixture data when data/raw/ is absent.
Inputs  : data/raw/current.zip, data/raw/historic.zip, data/raw/reference.zip,
          data/raw/warnkarte.json, data/raw/vhi.csv,
          data/station_region_mapping.json  (committed static reference)
Outputs : data/processed/
            warning_regions/{region_id}.json  – per-region aggregated report
            cantons/{canton_id}.json          – per-canton aggregated report
"""
from __future__ import annotations

import io
import json
import logging
import math
import re
import sys
import zipfile
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from config.settings import CANTON_TO_REGIONS, REGION_NAMES_DE
from src.aggregation.canton import compute_canton_report
from src.aggregation.regional import compute_region_report
from src.data import vhi_client as _vhi_client
from src.data import warnkarte_client as _warnkarte_client
from src.data.fixture_loader import load as load_fixture, load_station_region_map
from src.models import DataBundle, WarnkarteEntry

RAW_DIR = _REPO_ROOT / "data" / "raw"
PROCESSED_DIR = _REPO_ROOT / "data" / "processed"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Raw data loading
# ---------------------------------------------------------------------------

def _read_csv_from_zip(zip_path: Path, filename: str) -> tuple[pd.DataFrame, list[str]]:
    with zipfile.ZipFile(zip_path) as z:
        with z.open(filename) as f:
            raw = f.read().decode("utf-8", errors="replace")
    lines = raw.splitlines()
    comments = [ln for ln in lines if ln.startswith("#")]
    data = [ln for ln in lines if not ln.startswith("#") and ln.strip()]
    return pd.read_csv(io.StringIO("\n".join(data)), sep=";"), comments


def _read_stations_from_zip(zip_path: Path, filename: str) -> pd.DataFrame:
    with zipfile.ZipFile(zip_path) as z:
        with z.open(filename) as f:
            raw = f.read().decode("utf-8", errors="replace")
    data = [ln for ln in raw.splitlines() if not ln.startswith("#") and ln.strip()]
    df = pd.read_csv(io.StringIO("\n".join(data)), sep=";", dtype={"hydro_station_id": str})
    df["hydro_station_id"] = df["hydro_station_id"].str.strip()
    if "measured_at" in df.columns:
        df["measured_at"] = pd.to_datetime(df["measured_at"], format="%d.%m.%Y", errors="coerce")
    return df


def _parse_timestamp(comment_lines: list[str]) -> datetime:
    for line in comment_lines:
        m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", line)
        if m:
            return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    log.warning("Could not parse data_timestamp from raw data; using today.")
    return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)


def _parse_dates(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "measured_at" in df.columns:
        df["measured_at"] = pd.to_datetime(df["measured_at"], format="%d.%m.%Y", errors="coerce")
    return df


def _load_bundle_from_raw(raw_dir: Path) -> DataBundle:
    """Parse DataBundle from the raw ZIP files produced by scripts/download.py."""
    current_zip = raw_dir / "current.zip"
    historic_zip = raw_dir / "historic.zip"
    reference_zip = raw_dir / "reference.zip"

    current_df, comments = _read_csv_from_zip(current_zip, "weekly_current_regions.csv")
    forecast_raw, _ = _read_csv_from_zip(current_zip, "weekly_forecast_regions.csv")
    historic_df, _ = _read_csv_from_zip(historic_zip, "weekly_historic_regions.csv")
    reference_df, _ = _read_csv_from_zip(reference_zip, "regions.csv")
    current_stations_df = _read_stations_from_zip(current_zip, "weekly_current_stations.csv")
    reference_stations_df = _read_stations_from_zip(reference_zip, "daily_reference_stations.csv")

    forecast_df = forecast_raw.copy()
    forecast_df["valid_at"] = pd.to_datetime(
        forecast_df["valid_at"], format="%d.%m.%Y", errors="coerce"
    )

    try:
        stations_df = _read_stations_from_zip(reference_zip, "stations.csv")
        station_names = dict(zip(stations_df["hydro_station_id"], stations_df["name"]))
    except Exception as e:
        log.warning("Could not load stations.csv from raw data: %s", e)
        station_names = {}

    return DataBundle(
        current_df=_parse_dates(current_df),
        historic_df=_parse_dates(historic_df),
        reference_df=reference_df,
        forecast_df=forecast_df,
        current_stations_df=current_stations_df,
        reference_stations_df=reference_stations_df,
        station_region_map=load_station_region_map(),
        station_names=station_names,  # NEW
        data_timestamp=_parse_timestamp(comments),
        source="api",
    )


def _load_bundle(raw_dir: Path) -> DataBundle:
    if (raw_dir / "current.zip").exists():
        log.info("Loading data bundle from data/raw/ ...")
        return _load_bundle_from_raw(raw_dir)
    log.warning("data/raw/ absent — falling back to bundled fixture data.")
    return load_fixture()


def _load_warnkarte(raw_dir: Path) -> dict[int, WarnkarteEntry]:
    raw_path = raw_dir / "warnkarte.json"
    if raw_path.exists():
        log.info("Loading Warnkarte from data/raw/warnkarte.json ...")
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        return {int(rid): _warnkarte_client._parse_response(payload) for rid, payload in raw.items()}
    log.warning("data/raw/warnkarte.json absent — falling back to fixture.")
    # Discover which region IDs are actually present in the bundled fixture
    # (it may only cover a subset of all warning regions).
    fixture_raw = json.loads(_warnkarte_client._FIXTURE_PATH.read_text(encoding="utf-8"))
    available_ids = sorted(int(k) for k in fixture_raw)
    return _warnkarte_client._load_from_fixture(available_ids)


def _load_vhi(raw_dir: Path) -> dict[int, float]:
    vhi_path = raw_dir / "vhi.csv"
    all_ids = sorted(REGION_NAMES_DE.keys())
    if vhi_path.exists():
        log.info("Loading VHI from data/raw/vhi.csv ...")
        return _vhi_client._parse_csv(vhi_path, all_ids)
    log.warning("data/raw/vhi.csv absent — falling back to fixture.")
    return _vhi_client._load_from_fixture(all_ids)


# ---------------------------------------------------------------------------
# JSON serialization
# ---------------------------------------------------------------------------

class _DatetimeEncoder(json.JSONEncoder):
    def default(self, obj: object) -> object:
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


def _nan_to_none(obj: object) -> object:
    """Recursively replace NaN/Inf floats with None so output is valid JSON."""
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: _nan_to_none(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_nan_to_none(v) for v in obj]
    return obj


def _to_json(obj: object) -> str:
    """Serialize a dataclass (or plain dict) to a JSON string.

    Handles NaN → null and datetime → ISO-8601 string.
    """
    d = asdict(obj) if hasattr(obj, "__dataclass_fields__") else obj
    return json.dumps(_nan_to_none(d), ensure_ascii=False, indent=2, cls=_DatetimeEncoder)


# ---------------------------------------------------------------------------
# Aggregation pipeline
# ---------------------------------------------------------------------------

def run_aggregation(raw_dir: Path, processed_dir: Path) -> None:
    """
    Load raw data, compute all region and canton reports, write JSON to processed_dir.
    Falls back to fixture data if raw_dir does not contain the expected files.
    """
    bundle = _load_bundle(raw_dir)
    warnkarte = _load_warnkarte(raw_dir)
    vhi_data = _load_vhi(raw_dir)

    # Redirect vhi_client.fetch_for_regions so that compute_canton_report()
    # uses the pre-loaded file instead of making a live HTTP request.
    _orig_vhi = _vhi_client.fetch_for_regions
    _vhi_client.fetch_for_regions = lambda rids: {r: vhi_data[r] for r in rids if r in vhi_data}

    try:
        _write_regions(bundle, warnkarte, vhi_data, processed_dir)
        _write_cantons(bundle, warnkarte, processed_dir)
    finally:
        _vhi_client.fetch_for_regions = _orig_vhi


def _write_regions(
    bundle: DataBundle,
    warnkarte: dict[int, WarnkarteEntry],
    vhi_data: dict[int, float],
    processed_dir: Path,
) -> None:
    out_dir = processed_dir / "warning_regions"
    out_dir.mkdir(parents=True, exist_ok=True)
    log.info("Computing %d warning region reports ...", len(REGION_NAMES_DE))
    for region_id in sorted(REGION_NAMES_DE.keys()):
        try:
            report = compute_region_report(
                region_id,
                bundle,
                warnkarte_entry=warnkarte.get(region_id),
                vhi_value=vhi_data.get(region_id),
            )
            (out_dir / f"{region_id}.json").write_text(_to_json(report), encoding="utf-8")
        except Exception as exc:
            log.error("Region %d failed: %s", region_id, exc)


def _write_cantons(
    bundle: DataBundle,
    warnkarte: dict[int, WarnkarteEntry],
    processed_dir: Path,
) -> None:
    out_dir = processed_dir / "cantons"
    out_dir.mkdir(parents=True, exist_ok=True)
    log.info("Computing %d canton reports ...", len(CANTON_TO_REGIONS))
    for canton_id in sorted(CANTON_TO_REGIONS.keys()):
        try:
            report = compute_canton_report(canton_id, bundle, warnkarte_data=warnkarte)
            (out_dir / f"{canton_id}.json").write_text(_to_json(report), encoding="utf-8")
        except Exception as exc:
            log.error("Canton %d failed: %s", canton_id, exc)


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    run_aggregation(RAW_DIR, PROCESSED_DIR)
    log.info("Processed data written to %s", PROCESSED_DIR)


if __name__ == "__main__":
    main()

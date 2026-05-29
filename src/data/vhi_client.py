# src/data/vhi_client.py
"""
Fetches current VHI (Vegetation Health Index) per drought Warnregion
from the SwissEO REST endpoint.

On any network or HTTP error, falls back to data/vhi_fixture.csv.
Same pattern as src/data/warnkarte_client.py.

Endpoint:
  https://data.geo.admin.ch/ch.swisstopo.swisseo_vhi_v100/...
"""
from __future__ import annotations

import io
import logging
import warnings
from pathlib import Path
import pandas as pd

from config.settings import VHI_FIXTURE, VHI_URL

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 10


def fetch_for_regions(region_ids: list[int]) -> dict[int, float]:
    """
    Return {drought_region_id: vhi_mean} for each requested region.
    Falls back to data/vhi_fixture.csv on any network or HTTP error.
    """
    try:
        return _fetch_live(region_ids)
    except Exception as exc:
        warnings.warn(
            f"VHI fetch failed ({exc!r}); using bundled fixture data.",
            stacklevel=2,
        )
        return _load_from_fixture(region_ids)


def _fetch_live(region_ids: list[int]) -> dict[int, float]:
    import requests

    response = requests.get(VHI_URL, timeout=_TIMEOUT_SECONDS)
    response.raise_for_status()
    return _parse_csv(io.StringIO(response.text), region_ids)


def _load_from_fixture(region_ids: list[int]) -> dict[int, float]:
    return _parse_csv(VHI_FIXTURE, region_ids)


def _parse_csv(
    source: str | Path | io.StringIO,
    region_ids: list[int],
) -> dict[int, float]:
    df = pd.read_csv(source)
    df = df[df["REGION_NR"].isin(region_ids)]
    result = dict(zip(df["REGION_NR"].astype(int), df["vhi_mean"].astype(float)))
    missing = set(region_ids) - set(result.keys())
    if missing:
        logger.warning("VHI data missing for region IDs: %s", sorted(missing))
    return result

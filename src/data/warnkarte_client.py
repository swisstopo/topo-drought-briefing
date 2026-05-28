# src/data/warnkarte_client.py
"""
Fetches the current BAFU drought warning level per region.

API endpoint:
  https://api3.geo.admin.ch/rest/services/api/MapServer/ch.bafu.trockenheitswarnkarte/{drought_region_id}

On any network or HTTP error, falls back to the bundled fixture (data/warnkarte_fixture.json).
Same pattern as src/data/stac_client.py.
"""
from __future__ import annotations

import json
import logging
import warnings
from datetime import datetime
from pathlib import Path

from src.models import WarnkarteEntry

logger = logging.getLogger(__name__)

_BASE_URL = "https://api3.geo.admin.ch/rest/services/api/MapServer/ch.bafu.trockenheitswarnkarte"
_TIMEOUT_SECONDS = 10
_FIXTURE_PATH = Path(__file__).resolve().parents[2] / "data" / "warnkarte_fixture.json"


def _parse_response(payload: dict) -> WarnkarteEntry:
    """Convert the API JSON shape into a WarnkarteEntry."""
    attrs = payload["feature"]["attributes"]
    raw_warnlevel = int(attrs["warnlevel"])
    warnlevel = max(1, min(5, raw_warnlevel))
    return WarnkarteEntry(
        drought_region_id=int(attrs["idn"]),
        warnlevel=warnlevel,
        info_de=str(attrs["info_de"]),
        info_fr=str(attrs["info_fr"]),
        info_it=str(attrs["info_it"]),
        valid_from=datetime.strptime(
            str(attrs["valid_from"]).split("+")[0].strip(),
            "%Y/%m/%d %H:%M:%S",
        ),
    )


def fetch_for_regions(region_ids: list[int]) -> dict[int, WarnkarteEntry]:
    """
    Fetch the current warning level for each region.

    Returns a dict keyed by the requested region_id (the URL parameter).
    On any network or HTTP error, falls back to the fixture file.
    """
    try:
        return _fetch_live(region_ids)
    except Exception as exc:
        warnings.warn(
            f"Warnkarte fetch failed ({exc!r}); using bundled fixture data.",
            stacklevel=2,
        )
        return _load_from_fixture(region_ids)


def _fetch_live(region_ids: list[int]) -> dict[int, WarnkarteEntry]:
    import requests

    out: dict[int, WarnkarteEntry] = {}
    for rid in region_ids:
        url = f"{_BASE_URL}/{rid}"
        response = requests.get(url, timeout=_TIMEOUT_SECONDS)
        response.raise_for_status()
        out[rid] = _parse_response(response.json())
    return out


def _load_from_fixture(region_ids: list[int]) -> dict[int, WarnkarteEntry]:
    with _FIXTURE_PATH.open() as f:
        raw = json.load(f)

    out: dict[int, WarnkarteEntry] = {}
    for rid in region_ids:
        key = str(rid)
        if key not in raw:
            raise ValueError(
                f"Region {rid} not present in fixture {_FIXTURE_PATH} — "
                f"available keys: {sorted(raw.keys())}"
            )
        entry = raw[key]
        out[rid] = WarnkarteEntry(
            drought_region_id=int(entry["drought_region_id"]),
            warnlevel=int(entry["warnlevel"]),
            info_de=entry["info_de"],
            info_fr=entry["info_fr"],
            info_it=entry["info_it"],
            valid_from=datetime.fromisoformat(entry["valid_from"]),
        )
    return out

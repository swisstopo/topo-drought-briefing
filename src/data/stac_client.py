# src/data/stac_client.py
"""
Attempts to fetch the latest DataBundle from the BGDI STAC API.
On any network or HTTP error, logs a warning and falls back to the bundled fixture.

STAC endpoint:
  https://data.geo.admin.ch/api/stac/v0.9/collections/ch.bafu.trockenheitsdaten-numerisch

Response shape: standard STAC Collection JSON with links to downloadable CSV ZIPs.
If the API is unreachable, fixture_loader.load() is used transparently.
"""
from __future__ import annotations

import logging
import warnings

from src.data import fixture_loader
from src.models import DataBundle

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 10


def load() -> DataBundle:
    try:
        return _fetch_from_stac()
    except Exception as exc:
        warnings.warn(
            f"STAC fetch failed ({exc!r}); using bundled fixture data.",
            stacklevel=2,
        )
        return fixture_loader.load()


def _fetch_from_stac() -> DataBundle:
    import requests
    from config.settings import STAC_BASE_URL, STAC_COLLECTION

    url = f"{STAC_BASE_URL}/collections/{STAC_COLLECTION}"
    response = requests.get(url, timeout=_TIMEOUT_SECONDS)
    response.raise_for_status()

    # Full STAC download pipeline not yet implemented; fixture data used.
    raise NotImplementedError(
        "Full STAC download pipeline not yet implemented; fixture data used."
    )

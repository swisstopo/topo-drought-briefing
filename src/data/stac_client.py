# src/data/stac_client.py
"""
Fetches the latest DataBundle from the BGDI STAC API.
On any network or HTTP error, falls back to bundled fixture data transparently.

STAC endpoint:
  https://data.geo.admin.ch/api/stac/v1/collections/ch.bafu.trockenheitsdaten-numerisch
"""
from __future__ import annotations

import io
import logging
import re
import warnings
import zipfile
from datetime import datetime

import pandas as pd

from src.data import fixture_loader
from src.models import DataBundle

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 10
_DOWNLOAD_TIMEOUT = 60


def load() -> DataBundle:
    try:
        return _fetch_from_stac()
    except Exception as exc:
        warnings.warn(
            f"STAC fetch failed ({exc!r}); using bundled fixture data.",
            stacklevel=2,
        )
        return fixture_loader.load()


def _fetch_all_items(items_url: str) -> list[dict]:
    import requests

    items: list[dict] = []
    url: str | None = items_url
    params: dict | None = {"limit": 100}
    while url:
        response = requests.get(url, params=params, timeout=_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
        items.extend(data.get("features", []))
        url = next(
            (link["href"] for link in data.get("links", []) if link.get("rel") == "next"),
            None,
        )
        params = None
    return items


def _find_asset_href(assets: dict, keyword: str) -> str:
    for key, asset in assets.items():
        if keyword in key:
            href = asset.get("href", "")
            if href:
                return href
    raise RuntimeError(f"No asset containing '{keyword}' found in STAC item")


def _download_and_parse_zip(url: str) -> tuple[pd.DataFrame, list[str]]:
    import requests

    response = requests.get(url, timeout=_DOWNLOAD_TIMEOUT)
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        csv_name = next(n for n in z.namelist() if n.endswith(".csv"))
        with z.open(csv_name) as f:
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
    logger.warning("Could not parse data_timestamp from STAC comments; using today.")
    return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)


def _parse_dates(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["measured_at"] = pd.to_datetime(df["measured_at"], format="%d.%m.%Y", errors="coerce")
    return df


def _fetch_from_stac() -> DataBundle:
    from config.settings import STAC_BASE_URL, STAC_COLLECTION

    items_url = f"{STAC_BASE_URL}/collections/{STAC_COLLECTION}/items"
    items = _fetch_all_items(items_url)
    if not items:
        raise RuntimeError("STAC collection returned no items")

    latest_item = max(
        items,
        key=lambda x: x.get("properties", {}).get("datetime", ""),
    )
    assets = latest_item.get("assets", {})

    current_df, comment_lines = _download_and_parse_zip(_find_asset_href(assets, "current"))
    historic_df, _ = _download_and_parse_zip(_find_asset_href(assets, "historic"))
    reference_df, _ = _download_and_parse_zip(_find_asset_href(assets, "reference"))

    data_timestamp = _parse_timestamp(comment_lines)

    return DataBundle(
        current_df=_parse_dates(current_df),
        historic_df=_parse_dates(historic_df),
        reference_df=reference_df,
        data_timestamp=data_timestamp,
        source="api",
    )

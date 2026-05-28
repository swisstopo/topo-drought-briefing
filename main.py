#!/usr/bin/env python3
"""
Fetch items and assets from the Swiss federal drought data STAC API.
Saves asset metadata to JSON and optionally downloads files.
"""

import json
import time
from pathlib import Path

import requests

BASE_URL = "https://data.geo.admin.ch/api/stac/v1"
COLLECTION_ID = "ch.bafu.trockenheitsdaten-numerisch"
ITEMS_URL = f"{BASE_URL}/collections/{COLLECTION_ID}/items"

OUTPUT_DIR = Path("stac_data")
ASSETS_DIR = OUTPUT_DIR / "assets"


def fetch_all_items(limit: int = 100) -> list[dict]:
    """Fetch all items from the collection, handling pagination."""
    items = []
    url = ITEMS_URL
    params = {"limit": limit}

    while url:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        batch = data.get("features", [])
        items.extend(batch)
        print(f"  Fetched {len(batch)} items (total: {len(items)})")

        # Follow next link for pagination
        url = None
        params = None
        for link in data.get("links", []):
            if link.get("rel") == "next":
                url = link["href"]
                break

    return items


def extract_asset_catalog(items: list[dict]) -> list[dict]:
    """Build a flat list of asset records from all items."""
    catalog = []
    for item in items:
        item_id = item["id"]
        item_date = item.get("properties", {}).get("datetime", "")
        for asset_key, asset in item.get("assets", {}).items():
            catalog.append(
                {
                    "item_id": item_id,
                    "datetime": item_date,
                    "asset_key": asset_key,
                    "href": asset.get("href"),
                    "type": asset.get("type"),
                    "title": asset.get("title"),
                    "roles": asset.get("roles", []),
                }
            )
    return catalog


def download_assets(catalog: list[dict], max_downloads: int | None = None) -> None:
    """Download asset files into ASSETS_DIR."""
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    downloaded = 0

    for record in catalog:
        if max_downloads is not None and downloaded >= max_downloads:
            break

        href = record.get("href")
        if not href:
            continue

        filename = f"{record['item_id']}__{record['asset_key']}"
        dest = ASSETS_DIR / filename

        if dest.exists():
            print(f"  Skip (exists): {filename}")
            continue

        try:
            print(f"  Downloading: {filename}")
            resp = requests.get(href, timeout=60, stream=True)
            resp.raise_for_status()
            with dest.open("wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            downloaded += 1
            time.sleep(0.2)  # be polite
        except requests.HTTPError as e:
            print(f"  Error {e.response.status_code}: {href}")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Fetching STAC items...")
    items = fetch_all_items()
    print(f"Total items: {len(items)}")

    items_path = OUTPUT_DIR / "items.json"
    items_path.write_text(json.dumps(items, indent=2, ensure_ascii=False))
    print(f"Saved items -> {items_path}")

    catalog = extract_asset_catalog(items)
    catalog_path = OUTPUT_DIR / "asset_catalog.json"
    catalog_path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False))
    print(f"Saved asset catalog ({len(catalog)} assets) -> {catalog_path}")

    # Print a summary of asset types
    from collections import Counter
    type_counts = Counter(r["type"] for r in catalog)
    print("\nAsset types found:")
    for mime, count in type_counts.most_common():
        print(f"  {count:4d}  {mime}")

    # Uncomment to download all assets (can be large):
    download_assets(catalog)

    # Or download just the first N to verify:
    # download_assets(catalog, max_downloads=5)


if __name__ == "__main__":
    main()

# scripts/refresh_warnkarte_fixture.py
"""
Refresh data/warnkarte_fixture.json from the live BAFU Warnkarte API.

Usage:
    uv run python scripts/refresh_warnkarte_fixture.py
"""
import json
import sys
from datetime import datetime
from pathlib import Path

# Ensure the repo root is on sys.path so that `config` and `src` are importable.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import requests

from config.settings import CANTON_TO_REGIONS

URL = "https://api3.geo.admin.ch/rest/services/api/MapServer/ch.bafu.trockenheitswarnkarte/{rid}"
FIXTURE = Path(__file__).resolve().parents[1] / "data" / "warnkarte_fixture.json"


def main() -> None:
    out: dict[str, dict] = {}
    all_region_ids = sorted({r for regions in CANTON_TO_REGIONS.values() for r in regions})
    for rid in all_region_ids:
        resp = requests.get(URL.format(rid=rid), timeout=10)
        resp.raise_for_status()
        attrs = resp.json()["feature"]["attributes"]
        valid_from = datetime.strptime(
            str(attrs["valid_from"]).split("+")[0].strip(),
            "%Y/%m/%d %H:%M:%S",
        )
        out[str(rid)] = {
            "drought_region_id": int(attrs["idn"]),
            "warnlevel": int(attrs["warnlevel"]),
            "info_de": attrs["info_de"],
            "info_fr": attrs["info_fr"],
            "info_it": attrs["info_it"],
            "valid_from": valid_from.isoformat(),
        }
    FIXTURE.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(out)} regions to {FIXTURE}")


if __name__ == "__main__":
    main()

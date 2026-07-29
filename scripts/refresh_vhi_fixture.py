# scripts/refresh_vhi_fixture.py
"""
Refresh data/fixtures/vhi_fixture.csv from the live SwissEO VHI endpoint.

Usage:
    uv run python scripts/refresh_vhi_fixture.py
"""
import sys
from pathlib import Path

# Ensure the repo root is on sys.path so that `config` and `src` are importable.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import requests

from config.settings import VHI_FIXTURE, VHI_URL

_TIMEOUT_SECONDS = 10


def main() -> None:
    response = requests.get(VHI_URL, timeout=_TIMEOUT_SECONDS)
    response.raise_for_status()
    VHI_FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    VHI_FIXTURE.write_text(response.text, encoding="utf-8")
    print(f"Wrote {VHI_FIXTURE}")


if __name__ == "__main__":
    main()

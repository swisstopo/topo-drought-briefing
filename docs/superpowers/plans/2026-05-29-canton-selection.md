# Canton Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable all 26 Swiss cantons in the Streamlit canton selector by loading `data/kantone_warnregionen.json` at runtime in `config/settings.py`.

**Architecture:** `settings.py` loads the JSON at import time to build `CANTON_TO_REGIONS` (Bern hardcoded, all others from JSON), `CANTON_NAMES` (de/fr hardcoded for all 26), and `CANTON_CENTER_POINTS` (parsed from the `MAPGEO` field). `maps.py` imports `CANTON_CENTER_POINTS` instead of its own hardcoded dict. `app.py` is unchanged — its selectbox already reads from these dicts.

**Tech Stack:** Python, Streamlit, pytest, unittest.mock

---

### Task 1: Write failing tests for the three new settings constants

**Files:**
- Create: `tests/test_settings_cantons.py`

- [ ] **Step 1: Create the test file**

```python
# tests/test_settings_cantons.py
import pytest
from config.settings import CANTON_CENTER_POINTS, CANTON_NAMES, CANTON_TO_REGIONS


# ── CANTON_CENTER_POINTS ──────────────────────────────────────────────────

def test_canton_center_points_has_26_entries():
    assert len(CANTON_CENTER_POINTS) == 26


def test_canton_center_points_values_are_lv95_tuples():
    for canton_id, (x, y) in CANTON_CENTER_POINTS.items():
        assert 2_400_000 <= x <= 2_900_000, f"Canton {canton_id} x={x} out of LV95 range"
        assert 1_000_000 <= y <= 1_350_000, f"Canton {canton_id} y={y} out of LV95 range"


def test_canton_center_points_zurich():
    # Zürich MAPGEO: "&center=2691805,1252035&z=9"
    assert CANTON_CENTER_POINTS[1] == (2691805, 1252035)


def test_canton_center_points_bern():
    # Bern MAPGEO: "&center=2614322,1185492&z=8"
    assert CANTON_CENTER_POINTS[2] == (2614322, 1185492)


# ── CANTON_NAMES ──────────────────────────────────────────────────────────

def test_canton_names_has_26_entries():
    assert len(CANTON_NAMES) == 26


def test_canton_names_have_de_and_fr():
    for canton_id, names in CANTON_NAMES.items():
        assert "de" in names, f"Canton {canton_id} missing 'de'"
        assert "fr" in names, f"Canton {canton_id} missing 'fr'"


def test_canton_names_bern():
    assert CANTON_NAMES[2]["de"] == "Bern"
    assert CANTON_NAMES[2]["fr"] == "Berne"


def test_canton_names_zurich():
    assert CANTON_NAMES[1]["de"] == "Zürich"
    assert CANTON_NAMES[1]["fr"] == "Zurich"


def test_canton_names_geneva():
    assert CANTON_NAMES[25]["de"] == "Genève"
    assert CANTON_NAMES[25]["fr"] == "Genève"


# ── CANTON_TO_REGIONS ─────────────────────────────────────────────────────

def test_canton_to_regions_has_26_entries():
    assert len(CANTON_TO_REGIONS) == 26


def test_bern_regions_unchanged():
    assert CANTON_TO_REGIONS[2] == frozenset({33, 34, 35, 37, 38, 41})


def test_zurich_regions_from_json():
    # Zürich warnregionen in JSON: 42, 39, 43, 47
    assert CANTON_TO_REGIONS[1] == frozenset({42, 39, 43, 47})


def test_geneva_regions_from_json():
    # Geneva has exactly one region: 56 (Genferseebecken)
    assert CANTON_TO_REGIONS[25] == frozenset({56})


def test_all_region_sets_nonempty():
    for canton_id, regions in CANTON_TO_REGIONS.items():
        assert len(regions) > 0, f"Canton {canton_id} has no regions"


def test_all_region_sets_are_frozensets():
    for canton_id, regions in CANTON_TO_REGIONS.items():
        assert isinstance(regions, frozenset), f"Canton {canton_id} regions is not frozenset"
```

- [ ] **Step 2: Run to verify they all fail**

```bash
uv run pytest tests/test_settings_cantons.py -v
```

Expected: most tests FAIL — `CANTON_CENTER_POINTS` doesn't exist yet, `CANTON_NAMES` has only 1 entry, `CANTON_TO_REGIONS` has only 1 entry.

---

### Task 2: Implement the three new constants in `config/settings.py`

**Files:**
- Modify: `config/settings.py`

- [ ] **Step 1: Add imports and JSON loading at the top of `config/settings.py`**

Add after the existing imports (after `from pathlib import Path` and `from typing import Final`):

```python
import json
import re
```

Add after the `DATA_DIR` constant:

```python
_KANTONE = json.loads((DATA_DIR / "kantone_warnregionen.json").read_text(encoding="utf-8"))


def _parse_mapgeo(mapgeo: str) -> tuple[int, int]:
    m = re.search(r"center=(\d+),(\d+)", mapgeo)
    if not m:
        return (2614322, 1185492)  # Bern centre as safe fallback
    return (int(m.group(1)), int(m.group(2)))
```

- [ ] **Step 2: Add `CANTON_CENTER_POINTS`**

Add after the `_parse_mapgeo` helper:

```python
CANTON_CENTER_POINTS: Final[dict[int, tuple[int, int]]] = {
    entry["KANTONSNUM"]: _parse_mapgeo(entry["MAPGEO"])
    for entry in _KANTONE
}
```

- [ ] **Step 3: Replace the existing `CANTON_NAMES` dict with all 26 cantons**

Replace the current `CANTON_NAMES` block entirely:

```python
CANTON_NAMES: Final[dict[int, dict[str, str]]] = {
    1:  {"de": "Zürich",                    "fr": "Zurich"},
    2:  {"de": "Bern",                      "fr": "Berne",    "it": "Berna"},
    3:  {"de": "Luzern",                    "fr": "Lucerne"},
    4:  {"de": "Uri",                       "fr": "Uri"},
    5:  {"de": "Schwyz",                    "fr": "Schwytz"},
    6:  {"de": "Obwalden",                  "fr": "Obwald"},
    7:  {"de": "Nidwalden",                 "fr": "Nidwald"},
    8:  {"de": "Glarus",                    "fr": "Glaris"},
    9:  {"de": "Zug",                       "fr": "Zoug"},
    10: {"de": "Fribourg",                  "fr": "Fribourg"},
    11: {"de": "Solothurn",                 "fr": "Soleure"},
    12: {"de": "Basel-Stadt",               "fr": "Bâle-Ville"},
    13: {"de": "Basel-Landschaft",          "fr": "Bâle-Campagne"},
    14: {"de": "Schaffhausen",              "fr": "Schaffhouse"},
    15: {"de": "Appenzell Ausserrhoden",    "fr": "Appenzell Rhodes-Extérieures"},
    16: {"de": "Appenzell Innerrhoden",     "fr": "Appenzell Rhodes-Intérieures"},
    17: {"de": "St. Gallen",               "fr": "Saint-Gall"},
    18: {"de": "Graubünden",               "fr": "Grisons"},
    19: {"de": "Aargau",                   "fr": "Argovie"},
    20: {"de": "Thurgau",                  "fr": "Thurgovie"},
    21: {"de": "Ticino",                   "fr": "Tessin"},
    22: {"de": "Vaud",                     "fr": "Vaud"},
    23: {"de": "Valais",                   "fr": "Valais"},
    24: {"de": "Neuchâtel",               "fr": "Neuchâtel"},
    25: {"de": "Genève",                   "fr": "Genève"},
    26: {"de": "Jura",                     "fr": "Jura"},
}
```

- [ ] **Step 4: Replace the existing `CANTON_TO_REGIONS` dict**

Replace the current `CANTON_TO_REGIONS` block entirely:

```python
CANTON_TO_REGIONS: Final[dict[int, frozenset[int]]] = {
    2: frozenset({33, 34, 35, 37, 38, 41}),  # Bern – curated subset (excludes Freiberge etc.)
    **{
        entry["KANTONSNUM"]: frozenset(r["REGION_NR"] for r in entry["warnregionen"])
        for entry in _KANTONE
        if entry["KANTONSNUM"] != 2
    },
}
```

- [ ] **Step 5: Run the tests to verify they all pass**

```bash
uv run pytest tests/test_settings_cantons.py -v
```

Expected: all 16 tests PASS.

- [ ] **Step 6: Run the full test suite to check for regressions**

```bash
uv run pytest tests/ -v
```

Expected: all tests PASS. The existing `test_canton.py` tests rely on `CANTON_NAMES[2]` and `CANTON_TO_REGIONS[2]` — both are unchanged.

- [ ] **Step 7: Commit**

```bash
git add config/settings.py tests/test_settings_cantons.py
git commit -m "feat: load all 26 cantons from kantone_warnregionen.json"
```

---

### Task 3: Update `maps.py` to use `CANTON_CENTER_POINTS` from settings

**Files:**
- Modify: `src/viz/maps.py`
- Modify: `tests/test_settings_cantons.py` (add one map test)

- [ ] **Step 1: Add a failing test for the maps center point behaviour**

Append to `tests/test_settings_cantons.py`:

```python
# ── maps.py uses CANTON_CENTER_POINTS ─────────────────────────────────────

from unittest.mock import MagicMock, patch


def test_fetch_canton_geometry_uses_correct_center_for_zurich():
    """_fetch_canton_geometry must use CANTON_CENTER_POINTS[1] for Zürich."""
    from src.viz.maps import _fetch_canton_geometry

    captured = []

    def fake_get(url, timeout=None):
        captured.append(url)
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"results": []}  # empty → fallback bbox
        return mock_resp

    with patch("src.viz.maps.requests.get", side_effect=fake_get):
        _fetch_canton_geometry(canton_id=1)

    assert len(captured) == 1
    px, py = CANTON_CENTER_POINTS[1]  # (2691805, 1252035)
    assert f"geometry={px},{py}" in captured[0], (
        f"Expected geometry={px},{py} in URL but got: {captured[0]}"
    )
```

- [ ] **Step 2: Run the new test to verify it fails**

```bash
uv run pytest tests/test_settings_cantons.py::test_fetch_canton_geometry_uses_correct_center_for_zurich -v
```

Expected: FAIL — the URL contains the old fallback point `2600000,1200000` instead of `2691805,1252035`.

- [ ] **Step 3: Update `maps.py`**

In `src/viz/maps.py`, replace the `CANTON_IDENTIFY_POINTS` constant and its import with `CANTON_CENTER_POINTS`:

Replace the existing block:
```python
from config.settings import CDI_COLOURS
```
with:
```python
from config.settings import CANTON_CENTER_POINTS, CDI_COLOURS
```

Remove this block entirely (lines roughly 59–61):
```python
# A point guaranteed to be inside canton Bern (LV95 / EPSG:2056)
# Used for the identify call – change if targeting a different canton
CANTON_IDENTIFY_POINTS = {
    2: (2600000, 1200000),   # Bern – Belpberg area
}
CANTON_IDENTIFY_DEFAULT = (2600000, 1200000)
```

Replace it with just the fallback constant (keep fallback for safety):
```python
CANTON_IDENTIFY_DEFAULT = (2614322, 1185492)  # central Bern LV95 – fallback only
```

In `_fetch_canton_geometry`, replace:
```python
    px, py = CANTON_IDENTIFY_POINTS.get(canton_id, CANTON_IDENTIFY_DEFAULT)
```
with:
```python
    px, py = CANTON_CENTER_POINTS.get(canton_id, CANTON_IDENTIFY_DEFAULT)
```

- [ ] **Step 4: Run the new test to verify it passes**

```bash
uv run pytest tests/test_settings_cantons.py::test_fetch_canton_geometry_uses_correct_center_for_zurich -v
```

Expected: PASS.

- [ ] **Step 5: Run the full test suite**

```bash
uv run pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/viz/maps.py tests/test_settings_cantons.py
git commit -m "feat: use CANTON_CENTER_POINTS from settings in maps.py"
```

---

### Task 4: Smoke-test the UI with multiple cantons

**Files:**
- No code changes — verification only.

- [ ] **Step 1: Start the app**

```bash
make up
```

Open http://localhost:8501 in a browser.

- [ ] **Step 2: Verify the canton selector shows all 26 cantons**

In the sidebar, open the canton selectbox. Confirm you see all 26 cantons (Aargau, Appenzell Ausserrhoden, Appenzell Innerrhoden, Bern, Basel-Landschaft, Basel-Stadt, Fribourg, Genève, Glarus, Graubünden, Jura, Luzern, Neuchâtel, Nidwalden, Obwalden, Schaffhausen, Schwyz, Solothurn, St. Gallen, Thurgau, Ticino, Uri, Valais, Vaud, Zug, Zürich).

- [ ] **Step 3: Select a non-Bern canton and verify it loads**

Select **Zürich**. Confirm:
- The page title updates to "Trockenheitsbriefing Zürich"
- The lead headline renders without error
- Both maps display (centred on Zürich, not Bern)
- The regions tab shows Zürich's 4 regions (42, 39, 43, 47)

- [ ] **Step 4: Select a small canton and verify it loads**

Select **Genève**. Confirm:
- The lead headline renders without error
- The regions tab shows exactly 1 region (Genferseebecken, region 56)

- [ ] **Step 5: Verify Bern is unchanged**

Select **Bern**. Confirm:
- The regions tab still shows exactly 6 regions
- All indicator values match what was visible before this change

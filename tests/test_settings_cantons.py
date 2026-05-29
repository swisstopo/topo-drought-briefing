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

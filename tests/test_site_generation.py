"""
tests/test_site_generation.py

Tests for scripts/generate_site.py.
Covers deserialization round-trips and full site generation using fixture data.
All tests use fixture data — no network calls.
"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Load scripts/generate_site.py via importlib (no __init__.py in scripts/).
_site_spec = importlib.util.spec_from_file_location(
    "scripts_generate_site", _REPO_ROOT / "scripts" / "generate_site.py"
)
_site = importlib.util.module_from_spec(_site_spec)
_site_spec.loader.exec_module(_site)

canton_from_dict = _site.canton_from_dict
generate_site = _site.generate_site
_float_or_nan = _site._float_or_nan
_quality_from_dict = _site._quality_from_dict
_discharge_from_dict = _site._discharge_from_dict
_hydro_station_from_dict = _site._hydro_station_from_dict
_region_from_dict = _site._region_from_dict
_slug = _site._slug
_parse_regionen = _site._parse_regionen

# Load aggregate serializer for round-trip tests.
_agg_spec = importlib.util.spec_from_file_location(
    "scripts_aggregate", _REPO_ROOT / "scripts" / "aggregate.py"
)
_agg = importlib.util.module_from_spec(_agg_spec)
_agg_spec.loader.exec_module(_agg)
_to_json = _agg._to_json

from src.aggregation.canton import compute_canton_report
from src.aggregation.regional import compute_region_report
from src.data import vhi_client as _vhi_client
from src.data import warnkarte_client as _warnkarte_client
from src.data.fixture_loader import load as load_fixture

RULESET_PATH = _REPO_ROOT / "data" / "ruleset" / "canton-bulletin.yaml"
_BERN_REGION_IDS = [33, 34, 35, 37, 38, 41]


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def fixture_bundle():
    return load_fixture()


@pytest.fixture(scope="module")
def canton_2_report(fixture_bundle):
    """CantonReport for Bern (canton 2) computed from fixtures."""
    wk = _warnkarte_client._load_from_fixture(_BERN_REGION_IDS)
    vhi = _vhi_client._load_from_fixture(_BERN_REGION_IDS)
    orig = _vhi_client.fetch_for_regions
    _vhi_client.fetch_for_regions = lambda rids: {r: vhi[r] for r in rids if r in vhi}
    try:
        return compute_canton_report(2, fixture_bundle, wk)
    finally:
        _vhi_client.fetch_for_regions = orig


@pytest.fixture(scope="module")
def canton_2_dict(canton_2_report):
    """Canton 2 serialized to a JSON-compatible dict."""
    return json.loads(_to_json(canton_2_report))


# ---------------------------------------------------------------------------
# Unit tests for primitive helpers
# ---------------------------------------------------------------------------

class TestFloatOrNan:
    def test_none_returns_nan(self):
        result = _float_or_nan(None)
        assert math.isnan(result)

    def test_int_returns_float(self):
        assert _float_or_nan(42) == 42.0

    def test_float_returns_float(self):
        assert _float_or_nan(3.14) == pytest.approx(3.14)

    def test_zero_returns_zero(self):
        assert _float_or_nan(0) == 0.0


class TestQualityFromDict:
    _sample = {
        "data_age_days": 3,
        "coverage_pct": 0.85,
        "missing_columns": ["vhi"],
        "outlier_flags": [],
        "is_stale": False,
        "overall": "warning",
    }

    def test_fields_round_trip(self):
        q = _quality_from_dict(self._sample)
        assert q.data_age_days == 3
        assert q.coverage_pct == pytest.approx(0.85)
        assert q.missing_columns == ["vhi"]
        assert q.outlier_flags == []
        assert q.is_stale is False
        assert q.overall == "warning"


class TestDischargeFromDict:
    _sample = {"n_total": 10, "n_low": 4, "n_very_low": 2, "pct_low": 40}

    def test_fields_round_trip(self):
        d = _discharge_from_dict(self._sample)
        assert d.n_total == 10
        assert d.n_low == 4
        assert d.n_very_low == 2
        assert d.pct_low == 40


class TestHydroStationFromDict:
    def test_nulls_become_nan(self):
        d = {
            "station_id": "ABC",
            "station_name": "Test Station",
            "current_value": None,
            "low_flow_threshold": None,
            "min_value": 0.5,
        }
        s = _hydro_station_from_dict(d)
        assert math.isnan(s.current_value)
        assert math.isnan(s.low_flow_threshold)
        assert s.min_value == pytest.approx(0.5)
        assert s.station_id == "ABC"

    def test_values_preserved(self):
        d = {
            "station_id": "XY1",
            "station_name": "River Station",
            "current_value": 12.5,
            "low_flow_threshold": 8.0,
            "min_value": 2.1,
        }
        s = _hydro_station_from_dict(d)
        assert s.current_value == pytest.approx(12.5)
        assert s.low_flow_threshold == pytest.approx(8.0)


class TestSlug:
    def test_basic_ascii(self):
        assert _slug("Bern") == "bern"

    def test_umlaut_conversion(self):
        assert _slug("Zürich") == "zuerich"
        assert _slug("Bötschenberg") == "boetschenberg"

    def test_special_chars_replaced(self):
        result = _slug("Pays d'En-Haut")
        assert " " not in result
        assert "'" not in result

    def test_strips_leading_trailing_dashes(self):
        assert not _slug("  hello  ").startswith("-")


class TestParseRegionen:
    def test_parses_headings(self):
        text = "### Emmental\nDry.\n### Berner Oberland\nWet."
        result = _parse_regionen(text)
        assert "Emmental" in result
        assert "Berner Oberland" in result

    def test_empty_returns_empty(self):
        assert _parse_regionen("") == {}

    def test_no_headings_returns_empty(self):
        assert _parse_regionen("Some text without headings.") == {}


# ---------------------------------------------------------------------------
# Round-trip: serialize RegionReport → dict → _region_from_dict
# ---------------------------------------------------------------------------

class TestRegionRoundTrip:
    @pytest.fixture(scope="class")
    def region_34_report(self, fixture_bundle):
        wk = _warnkarte_client._load_from_fixture([34])
        vhi = _vhi_client._load_from_fixture([34])
        return compute_region_report(34, fixture_bundle, wk.get(34), vhi.get(34))

    @pytest.fixture(scope="class")
    def region_34_dict(self, region_34_report):
        return json.loads(_to_json(region_34_report))

    def test_region_id_preserved(self, region_34_report, region_34_dict):
        r = _region_from_dict(region_34_dict)
        assert r.region_id == region_34_report.region_id

    def test_cdi_preserved(self, region_34_report, region_34_dict):
        r = _region_from_dict(region_34_dict)
        assert r.cdi == region_34_report.cdi

    def test_warnlevel_preserved(self, region_34_report, region_34_dict):
        r = _region_from_dict(region_34_dict)
        assert r.warnlevel == region_34_report.warnlevel

    def test_quality_overall_preserved(self, region_34_report, region_34_dict):
        r = _region_from_dict(region_34_dict)
        assert r.quality.overall == region_34_report.quality.overall

    def test_data_timestamp_is_datetime(self, region_34_dict):
        from datetime import datetime
        r = _region_from_dict(region_34_dict)
        assert isinstance(r.data_timestamp, datetime)

    def test_null_forecast_becomes_none(self, fixture_bundle):
        import copy
        import pandas as pd
        b = copy.copy(fixture_bundle)
        b.forecast_df = pd.DataFrame()
        wk = _warnkarte_client._load_from_fixture([34])
        vhi = _vhi_client._load_from_fixture([34])
        report = compute_region_report(34, b, wk.get(34), vhi.get(34))
        d = json.loads(_to_json(report))
        assert d["cdi_forecast_week2"] is None
        r = _region_from_dict(d)
        assert r.cdi_forecast_week2 is None


# ---------------------------------------------------------------------------
# Round-trip: serialize CantonReport → dict → canton_from_dict
# ---------------------------------------------------------------------------

class TestCantonRoundTrip:
    def test_canton_id_preserved(self, canton_2_report, canton_2_dict):
        c = canton_from_dict(canton_2_dict)
        assert c.canton_id == canton_2_report.canton_id

    def test_max_warnlevel_preserved(self, canton_2_report, canton_2_dict):
        c = canton_from_dict(canton_2_dict)
        assert c.max_warnlevel == canton_2_report.max_warnlevel

    def test_region_count_preserved(self, canton_2_report, canton_2_dict):
        c = canton_from_dict(canton_2_dict)
        assert len(c.regions) == len(canton_2_report.regions)

    def test_canton_names_preserved(self, canton_2_report, canton_2_dict):
        c = canton_from_dict(canton_2_dict)
        assert c.canton_name_de == canton_2_report.canton_name_de
        assert c.canton_name_fr == canton_2_report.canton_name_fr

    def test_n_regions_dry_preserved(self, canton_2_report, canton_2_dict):
        c = canton_from_dict(canton_2_dict)
        assert c.n_regions_dry == canton_2_report.n_regions_dry

    def test_index_dict_keys_are_int(self, canton_2_dict):
        c = canton_from_dict(canton_2_dict)
        for k in c.n_regions_by_precip_index:
            assert isinstance(k, int)

    def test_quality_preserved(self, canton_2_report, canton_2_dict):
        c = canton_from_dict(canton_2_dict)
        assert c.quality.overall == canton_2_report.quality.overall
        assert c.quality.data_age_days == canton_2_report.quality.data_age_days

    def test_data_timestamp_is_datetime(self, canton_2_dict):
        from datetime import datetime
        c = canton_from_dict(canton_2_dict)
        assert isinstance(c.data_timestamp, datetime)

    def test_discharge_preserved(self, canton_2_report, canton_2_dict):
        c = canton_from_dict(canton_2_dict)
        assert c.discharge.n_total == canton_2_report.discharge.n_total


# ---------------------------------------------------------------------------
# Integration: generate_site() writes expected files
# ---------------------------------------------------------------------------

class TestGenerateSite:
    @pytest.fixture()
    def processed_dir(self, tmp_path, canton_2_dict):
        canton_dir = tmp_path / "cantons"
        canton_dir.mkdir(parents=True)
        (canton_dir / "2.json").write_text(json.dumps(canton_2_dict), encoding="utf-8")
        return tmp_path

    @pytest.fixture()
    def site_dir(self, tmp_path):
        return tmp_path / "site"

    @pytest.fixture()
    def built_site(self, processed_dir, site_dir):
        """Build the site once; all tests in this class share the result."""
        generate_site(processed_dir, RULESET_PATH, site_dir)
        return site_dir

    # --- Output files exist ---

    def test_canton_index_html_created(self, built_site):
        assert (built_site / "canton" / "BE" / "index.html").exists()

    def test_index_html_created(self, built_site):
        assert (built_site / "index.html").exists()

    def test_style_css_created(self, built_site):
        assert (built_site / "assets" / "style.css").exists()

    def test_app_js_created(self, built_site):
        assert (built_site / "assets" / "app.js").exists()

    def test_json_copied_to_site_data(self, built_site):
        assert (built_site / "data" / "cantons" / "2.json").exists()

    # --- HTML correctness ---

    def test_canton_page_is_valid_html(self, built_site):
        content = (built_site / "canton" / "BE" / "index.html").read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "<html" in content
        assert "</html>" in content

    def test_canton_page_contains_canton_name_de(self, built_site):
        content = (built_site / "canton" / "BE" / "index.html").read_text(encoding="utf-8")
        assert "Bern" in content

    def test_canton_page_contains_canton_name_fr(self, built_site):
        content = (built_site / "canton" / "BE" / "index.html").read_text(encoding="utf-8")
        # French name for Bern
        assert "Berne" in content

    def test_canton_page_has_both_lang_classes(self, built_site):
        content = (built_site / "canton" / "BE" / "index.html").read_text(encoding="utf-8")
        assert "lang-de" in content
        assert "lang-fr" in content

    def test_canton_page_links_to_assets(self, built_site):
        content = (built_site / "canton" / "BE" / "index.html").read_text(encoding="utf-8")
        assert "../../assets/style.css" in content
        assert "../../assets/app.js" in content

    def test_index_contains_canton_link(self, built_site):
        content = (built_site / "index.html").read_text(encoding="utf-8")
        assert "canton/BE/index.html" in content

    def test_index_has_both_lang_classes(self, built_site):
        content = (built_site / "index.html").read_text(encoding="utf-8")
        assert "lang-de" in content
        assert "lang-fr" in content

    def test_index_links_to_assets(self, built_site):
        content = (built_site / "index.html").read_text(encoding="utf-8")
        assert "assets/style.css" in content
        assert "assets/app.js" in content

    # --- Language switching ---

    def test_lang_toggle_buttons_present(self, built_site):
        content = (built_site / "canton" / "BE" / "index.html").read_text(encoding="utf-8")
        assert 'data-lang="de"' in content
        assert 'data-lang="fr"' in content

    def test_js_switchlang_function_defined(self, built_site):
        js = (built_site / "assets" / "app.js").read_text(encoding="utf-8")
        assert "switchLang" in js
        assert "droughtLang" in js

    def test_css_lang_visibility_rules_present(self, built_site):
        css = (built_site / "assets" / "style.css").read_text(encoding="utf-8")
        assert 'lang="fr"' in css
        assert 'lang="de"' in css
        assert "lang-de" in css
        assert "lang-fr" in css

    # --- Swiss design system ---

    def test_css_has_federal_blue(self, built_site):
        css = (built_site / "assets" / "style.css").read_text(encoding="utf-8")
        assert "#003F6B" in css or "#003f6b" in css.lower()

    def test_css_has_swiss_red(self, built_site):
        css = (built_site / "assets" / "style.css").read_text(encoding="utf-8")
        assert "#DC0000" in css or "#dc0000" in css.lower()

    def test_canton_page_has_warnlevel_badge(self, built_site):
        content = (built_site / "canton" / "BE" / "index.html").read_text(encoding="utf-8")
        assert "wl-" in content
        assert "badge-large" in content

    # --- No computation markers ---

    def test_no_jinja2_syntax_leaks_into_output(self, built_site):
        content = (built_site / "canton" / "BE" / "index.html").read_text(encoding="utf-8")
        assert "{{" not in content
        assert "{%" not in content

    # --- Error handling ---

    def test_missing_cantons_dir_exits(self, tmp_path):
        site_dir = tmp_path / "site"
        with pytest.raises(SystemExit) as exc_info:
            generate_site(tmp_path, RULESET_PATH, site_dir)
        assert exc_info.value.code == 1

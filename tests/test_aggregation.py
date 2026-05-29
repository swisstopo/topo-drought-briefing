# tests/test_aggregation.py
import math
from datetime import datetime as _dt

import pytest

from config.settings import CANTON_NAMES, CANTON_TO_REGIONS
from src.aggregation.regional import compute_region_report
from src.data.fixture_loader import load
from src.data.stac_client import load as load_data
from src.models import WarnkarteEntry


@pytest.fixture(scope="module")
def bundle():
    return load()


def test_region_report_basic_fields(bundle):
    report = compute_region_report(34, bundle)
    assert report.region_id == 34
    assert report.region_name_de == "Berner Mittelland"
    assert 0 <= report.cdi <= 5


def test_spi_3m_is_not_nan(bundle):
    report = compute_region_report(34, bundle)
    assert not math.isnan(report.spi_3m)


def test_pct_critical_in_range(bundle):
    report = compute_region_report(34, bundle)
    assert 0.0 <= report.pct_critical <= 1.0


def test_spi_3m_percentile_in_range(bundle):
    report = compute_region_report(34, bundle)
    assert 0 <= report.spi_3m_percentile <= 100


def test_cdi_trend_is_valid(bundle):
    report = compute_region_report(34, bundle)
    assert report.cdi_trend in (-1, 0, 1)


def test_quality_attached(bundle):
    report = compute_region_report(34, bundle)
    assert report.quality is not None
    assert report.quality.overall in ("ok", "warning", "error")


def test_all_berne_regions_compute(bundle):
    from config.settings import CANTON_TO_REGIONS
    for rid in CANTON_TO_REGIONS[2]:
        report = compute_region_report(rid, bundle)
        assert 0 <= report.cdi <= 5


def test_canton_to_regions_bern():
    assert CANTON_TO_REGIONS[2] == frozenset({33, 34, 35, 37, 38, 41})
    assert CANTON_NAMES[2]["de"] == "Bern"
    assert CANTON_NAMES[2]["fr"] == "Berne"


def test_region_report_has_new_fields_from_fixture():
    bundle = load_data()
    warnkarte = {
        34: WarnkarteEntry(
            drought_region_id=34,
            warnlevel=2,
            info_de="Mässige Gefahr",
            info_fr="Danger limité",
            info_it="Pericolo moderato",
            valid_from=_dt(2026, 5, 28),
        )
    }
    report = compute_region_report(34, bundle, warnkarte_entry=warnkarte[34])

    assert report.warnlevel == 2
    assert report.warnlevel_info_de == "Mässige Gefahr"
    assert report.warnlevel_info_fr == "Danger limité"
    assert report.precip_sum_1m >= 0.0
    assert report.precip_sum_3m >= 0.0
    assert 1 <= report.precip_1m_index <= 5
    assert 1 <= report.soil_moisture_index <= 5
    assert 1 <= report.hydro_index <= 5
    # Forecast week 2 may be None if data is shorter than 14 days
    assert report.cdi_forecast_week2 is None or 1 <= report.cdi_forecast_week2 <= 5


def test_region_report_deficit_deltas_and_discharge(bundle):
    from src.models import DischargeStats
    report = compute_region_report(34, bundle)
    assert isinstance(report.precip_deficit_delta, int)
    assert isinstance(report.soil_moisture_deficit_delta, int)
    assert isinstance(report.discharge, DischargeStats)
    assert report.discharge.n_total >= 0


def test_vhi_value_param_overrides_row_vhi(bundle):
    report = compute_region_report(34, bundle, vhi_value=42.5)
    assert report.vhi == pytest.approx(42.5)


def test_vhi_delta_is_zero_when_vhi_value_provided(bundle):
    report = compute_region_report(34, bundle, vhi_value=42.5)
    assert report.vhi_delta == 0.0

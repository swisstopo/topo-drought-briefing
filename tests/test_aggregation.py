# tests/test_aggregation.py
import math
import pytest
from src.data.fixture_loader import load
from src.aggregation.regional import compute_region_report


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
    from config.settings import BERNE_REGION_IDS
    for rid in BERNE_REGION_IDS:
        report = compute_region_report(rid, bundle)
        assert 0 <= report.cdi <= 5

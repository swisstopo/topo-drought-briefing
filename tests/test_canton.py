# tests/test_canton.py
from datetime import datetime

import pytest
import responses

from src.aggregation.canton import _fold_quality, compute_canton_report
from src.data.stac_client import load as load_data
from src.models import QualityReport, WarnkarteEntry


def _make_warnkarte(rid: int, warnlevel: int) -> WarnkarteEntry:
    info_map = {
        1: ("Keine Gefahr", "Aucun danger"),
        2: ("Mässige Gefahr", "Danger limité"),
        3: ("Erhebliche Gefahr", "Danger marqué"),
        4: ("Grosse Gefahr", "Danger fort"),
        5: ("Sehr grosse Gefahr", "Danger très fort"),
    }
    de, fr = info_map[warnlevel]
    return WarnkarteEntry(
        drought_region_id=rid,
        warnlevel=warnlevel,
        info_de=de,
        info_fr=fr,
        info_it="-",
        valid_from=datetime(2026, 5, 28),
    )


def test_compute_canton_report_basic():
    bundle = load_data()
    warnkarte = {
        33: _make_warnkarte(33, 2),
        34: _make_warnkarte(34, 4),
        35: _make_warnkarte(35, 1),
        37: _make_warnkarte(37, 3),
        38: _make_warnkarte(38, 2),
        41: _make_warnkarte(41, 1),
    }

    canton = compute_canton_report(canton_id=2, bundle=bundle, warnkarte_data=warnkarte)

    assert canton.canton_id == 2
    assert canton.canton_name_de == "Bern"
    assert canton.canton_name_fr == "Berne"
    assert len(canton.regions) == 6
    # Max warnlevel is the highest across regions
    assert canton.max_warnlevel == 4
    assert canton.max_warnlevel_info_de == "Grosse Gefahr"
    # All region IDs appear
    assert {r.region_id for r in canton.regions} == {33, 34, 35, 37, 38, 41}


def _q(overall: str, age: int = 1, coverage: float = 1.0) -> QualityReport:
    return QualityReport(
        data_age_days=age,
        coverage_pct=coverage,
        missing_columns=[],
        outlier_flags=[],
        is_stale=age > 14,
        overall=overall,
    )


def test_fold_quality_worst_wins():
    folded = _fold_quality([_q("ok"), _q("warning"), _q("ok")])
    assert folded.overall == "warning"


def test_fold_quality_error_dominates():
    folded = _fold_quality([_q("ok"), _q("error"), _q("warning")])
    assert folded.overall == "error"


def test_fold_quality_max_age():
    folded = _fold_quality([_q("ok", age=3), _q("ok", age=10), _q("ok", age=2)])
    assert folded.data_age_days == 10


def test_fold_quality_mean_coverage():
    folded = _fold_quality([_q("ok", coverage=0.6), _q("ok", coverage=1.0)])
    assert folded.coverage_pct == 0.8


_VHI_URL = (
    "https://data.geo.admin.ch/ch.swisstopo.swisseo_vhi_v100"
    "/swisseo_vhi_v100"
    "/ch.swisstopo.swisseo_vhi_v100_current_vegetation-warnregions.csv"
)
_VHI_CSV = (
    "REGION_NR,vhi_mean,availability_percentage\n"
    "33,55.0,99.9\n34,60.0,96.8\n35,70.0,80.5\n"
    "37,45.0,99.9\n38,80.0,95.0\n41,65.0,77.6\n"
)


@responses.activate
def test_canton_report_uses_swisseo_vhi():
    responses.add(
        responses.GET,
        _VHI_URL,
        body=_VHI_CSV,
        status=200,
        content_type="text/csv",
    )
    bundle = load_data()
    warnkarte = {rid: _make_warnkarte(rid, 2) for rid in [33, 34, 35, 37, 38, 41]}
    canton = compute_canton_report(canton_id=2, bundle=bundle, warnkarte_data=warnkarte)
    region_34 = next(r for r in canton.regions if r.region_id == 34)
    assert region_34.vhi == pytest.approx(60.0)

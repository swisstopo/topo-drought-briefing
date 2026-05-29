# tests/test_vhi_client.py
import io

import pytest
import responses

from src.data.vhi_client import _parse_csv, fetch_for_regions

_VHI_URL = (
    "https://data.geo.admin.ch/ch.swisstopo.swisseo_vhi_v100"
    "/swisseo_vhi_v100"
    "/ch.swisstopo.swisseo_vhi_v100_current_vegetation-warnregions.csv"
)
_CSV_BODY = (
    "REGION_NR,vhi_mean,availability_percentage\n"
    "33,61.8,99.9\n"
    "34,68.0,96.8\n"
    "35,82.0,80.5\n"
    "99,50.0,90.0\n"
)


def test_parse_csv_returns_requested_regions():
    result = _parse_csv(io.StringIO(_CSV_BODY), [33, 34])
    assert result == {33: pytest.approx(61.8), 34: pytest.approx(68.0)}
    assert 35 not in result
    assert 99 not in result


def test_parse_csv_returns_only_vhi_mean_values():
    result = _parse_csv(io.StringIO(_CSV_BODY), [33])
    assert set(result.keys()) == {33}
    assert result[33] == pytest.approx(61.8)  # vhi_mean, not availability_percentage


def test_parse_csv_warns_when_region_missing(caplog):
    import logging
    with caplog.at_level(logging.WARNING, logger="src.data.vhi_client"):
        result = _parse_csv(io.StringIO(_CSV_BODY), [999])
    assert result == {}
    assert "999" in caplog.text


@responses.activate
def test_fetch_for_regions_live_path():
    responses.add(
        responses.GET,
        _VHI_URL,
        body=_CSV_BODY,
        status=200,
        content_type="text/csv",
    )
    out = fetch_for_regions([33, 34])
    assert out[33] == pytest.approx(61.8)
    assert out[34] == pytest.approx(68.0)
    assert 99 not in out


@responses.activate
def test_fetch_for_regions_falls_back_to_fixture_on_error(recwarn):
    responses.add(responses.GET, _VHI_URL, status=503)
    out = fetch_for_regions([33])
    assert 33 in out
    assert out[33] > 0
    assert any("VHI fetch failed" in str(w.message) for w in recwarn.list)


@responses.activate
def test_fetch_for_regions_warns_on_network_error(recwarn):
    responses.add(responses.GET, _VHI_URL, body=ConnectionError("timeout"))
    out = fetch_for_regions([33])
    assert 33 in out
    assert any("VHI fetch failed" in str(w.message) for w in recwarn.list)

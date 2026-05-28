# tests/test_text_blocks.py
import re
import pytest
from datetime import datetime
from src.models import QualityReport, RegionReport
from src.briefing.template import build_briefing


@pytest.fixture
def sample_report():
    quality = QualityReport(
        data_age_days=1, coverage_pct=1.0,
        missing_columns=[], outlier_flags=[],
        is_stale=False, overall="ok",
    )
    return RegionReport(
        region_id=34, region_name_de="Berner Mittelland",
        data_timestamp=datetime(2026, 5, 26), source="fixture",
        cdi=2, spi_3m=-1.04, soil_moisture_pct=98.1, vhi=44.33,
        cdi_trend=0, spi_3m_delta=-0.05, vhi_delta=0.5,
        pct_critical=0.12, spi_3m_percentile=22, quality=quality,
    )


@pytest.mark.parametrize("mode", ["behoerden", "bulletin"])
@pytest.mark.parametrize("cdi", range(6))
def test_no_unfilled_slots(sample_report, mode, cdi):
    sample_report.cdi = cdi
    doc = build_briefing(sample_report, mode)
    for section_name, text in doc.sections.items():
        assert "{" not in text and "}" not in text, (
            f"Unfilled slot in {section_name} (mode={mode}, cdi={cdi}): {text}"
        )


@pytest.mark.parametrize("mode", ["behoerden", "bulletin"])
def test_all_four_sections_present(sample_report, mode):
    doc = build_briefing(sample_report, mode)
    assert set(doc.sections.keys()) == {"lage", "entwicklung", "einordnung", "datengrundlage"}


@pytest.mark.parametrize("mode", ["behoerden", "bulletin"])
def test_sections_non_empty(sample_report, mode):
    doc = build_briefing(sample_report, mode)
    for section_name, text in doc.sections.items():
        assert len(text.strip()) > 0, f"Empty section: {section_name}"


def test_mode_preserved_in_document(sample_report):
    doc = build_briefing(sample_report, "bulletin")
    assert doc.mode == "bulletin"

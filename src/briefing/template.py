# src/briefing/template.py
from __future__ import annotations

import math
from datetime import datetime

from config.settings import CDI_LABELS
from src.briefing.text_blocks import (
    DATENGRUNDLAGE_BLOCKS,
    ENTWICKLUNG_BLOCKS,
    EINORDNUNG_BLOCKS,
    LAGE_BLOCKS,
)
from src.models import BriefingDocument, RegionReport


def _safe_num(val: float, default: float = 0.0) -> float:
    """Replace NaN with a safe default for string formatting."""
    return val if not math.isnan(val) else default

_TREND_LABELS: dict[int, dict[str, str]] = {
    -1: {"behoerden": "verbessernd", "bulletin": "verbessert"},
    0:  {"behoerden": "stabil",      "bulletin": "stabilisiert"},
    1:  {"behoerden": "verschlechternd", "bulletin": "verschlechtert"},
}


def _format_kwargs(report: RegionReport, mode: str) -> dict:
    return {
        "region":            report.region_name_de,
        "cdi":               report.cdi,
        "cdi_label":         CDI_LABELS.get(report.cdi, "Unbekannt"),
        "spi_3m":            report.spi_3m,
        "spi_3m_delta":      report.spi_3m_delta,
        "soil_moisture_pct": report.soil_moisture_pct,
        "vhi":               _safe_num(report.vhi),
        "vhi_delta":         _safe_num(report.vhi_delta),
        "pct_critical_pct":  report.pct_critical * 100,
        "spi_3m_percentile": report.spi_3m_percentile,
        "data_timestamp":    report.data_timestamp.strftime("%d.%m.%Y"),
        "coverage_pct":      report.quality.coverage_pct,
        "overall":           report.quality.overall,
        "trend_de":          _TREND_LABELS.get(report.cdi_trend, {}).get(mode, "stabil"),
        "trend_de_bulletin": _TREND_LABELS.get(report.cdi_trend, {}).get("bulletin", "stabilisiert"),
    }


def build_briefing(report: RegionReport, mode: str) -> BriefingDocument:
    cdi = min(max(report.cdi, 0), 5)
    fmt = _format_kwargs(report, mode)
    sections = {
        "lage":           LAGE_BLOCKS[mode][cdi].format(**fmt),
        "entwicklung":    ENTWICKLUNG_BLOCKS[mode][cdi].format(**fmt),
        "einordnung":     EINORDNUNG_BLOCKS[mode][cdi].format(**fmt),
        "datengrundlage": DATENGRUNDLAGE_BLOCKS[mode].format(**fmt),
    }
    return BriefingDocument(
        sections=sections,
        report=report,
        mode=mode,
        generated_at=datetime.now(),
    )


def translate(text: str, lang: str = "de") -> str:
    """FR/IT translation stub — returns German text unchanged."""
    return text

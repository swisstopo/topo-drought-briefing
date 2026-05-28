import pandas as pd
import pytest
from datetime import datetime, timedelta
from src.quality.checks import run_quality_checks


def _base_row() -> pd.Series:
    return pd.Series({
        "cdi": 1, "spi_3m": -0.5, "soil_moisture_ufc": 85.0, "vhi": 50.0,
        "spi_1m": -0.3, "spi_6m": -0.4, "spi_12m": -0.2, "spi_24m": 0.1,
        "precip_sum_1m": 80.0, "precip_sum_3m": 220.0,
    })


def test_fresh_complete_data_is_ok():
    report = run_quality_checks(_base_row(), datetime.now())
    assert report.overall == "ok"
    assert report.is_stale is False
    assert report.coverage_pct == 1.0
    assert report.missing_columns == []


def test_missing_column_gives_warning():
    row = _base_row()
    row = row.drop("vhi")
    report = run_quality_checks(row, datetime.now())
    assert "vhi" in report.missing_columns
    assert report.overall in ("warning", "error")
    assert report.coverage_pct < 1.0


def test_stale_data_gives_error():
    old_ts = datetime.now() - timedelta(days=20)
    report = run_quality_checks(_base_row(), old_ts)
    assert report.is_stale is True
    assert report.overall == "error"
    assert report.data_age_days >= 20


def test_outlier_gives_warning():
    row = _base_row()
    row["spi_3m"] = -99.0  # extreme outlier
    hist = pd.Series([-1.0, -0.5, 0.0, 0.5, 1.0] * 20)
    report = run_quality_checks(row, datetime.now(), spi_3m_reference=hist)
    assert "spi_3m" in report.outlier_flags
    assert report.overall in ("warning", "error")

from __future__ import annotations

from datetime import datetime
from typing import Literal

import pandas as pd

from config.settings import DATA_STALENESS_DAYS, INDICATOR_COLUMNS
from src.models import QualityReport


def run_quality_checks(
    row: pd.Series,
    data_timestamp: datetime,
    spi_3m_reference: pd.Series | None = None,
) -> QualityReport:
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    data_age_days = (today - data_timestamp.replace(hour=0, minute=0, second=0, microsecond=0)).days
    is_stale = data_age_days > DATA_STALENESS_DAYS

    missing_columns: list[str] = [c for c in INDICATOR_COLUMNS if c not in row.index or pd.isna(row.get(c))]
    present = len(INDICATOR_COLUMNS) - len(missing_columns)
    coverage_pct = present / len(INDICATOR_COLUMNS)

    outlier_flags: list[str] = []
    if spi_3m_reference is not None:
        val = row.get("spi_3m")
        if val is not None and not pd.isna(val):
            q1 = spi_3m_reference.quantile(0.25)
            q3 = spi_3m_reference.quantile(0.75)
            iqr = q3 - q1
            if val < (q1 - 3 * iqr) or val > (q3 + 3 * iqr):
                outlier_flags.append("spi_3m")

    if is_stale or coverage_pct < 0.5:
        overall: Literal["ok", "warning", "error"] = "error"
    elif missing_columns or outlier_flags:
        overall = "warning"
    else:
        overall = "ok"

    return QualityReport(
        data_age_days=data_age_days,
        coverage_pct=coverage_pct,
        missing_columns=missing_columns,
        outlier_flags=outlier_flags,
        is_stale=is_stale,
        overall=overall,
    )

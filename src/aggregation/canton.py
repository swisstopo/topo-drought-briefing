# src/aggregation/canton.py
from __future__ import annotations

from collections import Counter

from config.rules_loader import RULES
from config.settings import CANTON_NAMES, CANTON_TO_REGIONS
from src.aggregation.regional import compute_region_report
from src.aggregation.stations import compute_discharge_stats
from src.data import vhi_client
from src.models import CantonReport, DataBundle, QualityReport, WarnkarteEntry


def compute_canton_report(
    canton_id: int,
    bundle: DataBundle,
    warnkarte_data: dict[int, WarnkarteEntry],
) -> CantonReport:
    if canton_id not in CANTON_TO_REGIONS:
        raise ValueError(
            f"Canton {canton_id} not in CANTON_TO_REGIONS. "
            f"Available: {sorted(CANTON_TO_REGIONS.keys())}"
        )

    region_ids = sorted(CANTON_TO_REGIONS[canton_id])
    vhi_data = vhi_client.fetch_for_regions(list(region_ids))
    region_reports = [
        compute_region_report(
            rid,
            bundle,
            warnkarte_entry=warnkarte_data.get(rid),
            vhi_value=vhi_data.get(rid),
        )
        for rid in region_ids
    ]

    # Max warning level across regions
    max_region = max(region_reports, key=lambda r: r.warnlevel)
    max_warnlevel = max_region.warnlevel
    max_warnlevel_info_de = max_region.warnlevel_info_de
    max_warnlevel_info_fr = max_region.warnlevel_info_fr

    # Index counts
    n_precip = Counter(r.precip_1m_index for r in region_reports)
    n_soil = Counter(r.soil_moisture_index for r in region_reports)
    n_hydro = Counter(r.hydro_index for r in region_reports)

    quality = _fold_quality([r.quality for r in region_reports])

    # --- New aggregates (template revision 2026-05-29) ---
    dry = [r for r in region_reports if r.cdi >= RULES.cdi_dry_min]
    n_regions_dry = len(dry)
    cdi_min_dry = min((r.cdi for r in dry), default=None)
    cdi_max_dry = max((r.cdi for r in dry), default=None)

    sum_current_cdi = sum(r.cdi for r in region_reports)
    sum_forecast_cdi = sum(
        r.cdi_forecast_week2 if r.cdi_forecast_week2 is not None else r.cdi
        for r in region_reports
    )
    cdi_situation_delta = sum_forecast_cdi - sum_current_cdi

    mean_precip_sum_1m = round(sum(r.precip_sum_1m for r in region_reports) / len(region_reports), 1)
    mean_precip_sum_3m = round(sum(r.precip_sum_3m for r in region_reports) / len(region_reports), 1)

    precip_indices = [r.precip_1m_index for r in region_reports]
    precip_index_min = min(precip_indices)
    precip_index_max = max(precip_indices)

    n_precip_deficit = sum(1 for r in region_reports if r.precip_1m_index >= RULES.precip_1m_index_min)
    n_soil_deficit = sum(1 for r in region_reports if r.soil_moisture_index >= RULES.soil_moisture_index_min)
    n_vhi_stress = sum(1 for r in region_reports if r.vhi_index >= RULES.vhi_stress_index_min)
    max_vhi_index = max(r.vhi_index for r in region_reports)

    discharge = compute_discharge_stats(region_ids, bundle)

    names = CANTON_NAMES[canton_id]
    return CantonReport(
        canton_id=canton_id,
        canton_name_de=names["de"],
        canton_name_fr=names["fr"],
        data_timestamp=bundle.data_timestamp,
        source=bundle.source,
        regions=region_reports,
        max_warnlevel=max_warnlevel,
        max_warnlevel_info_de=max_warnlevel_info_de,
        max_warnlevel_info_fr=max_warnlevel_info_fr,
        n_regions_by_precip_index=dict(n_precip),
        n_regions_by_soil_moisture_index=dict(n_soil),
        n_regions_by_hydro_index=dict(n_hydro),
        quality=quality,
        n_regions_dry=n_regions_dry,
        cdi_min_dry=cdi_min_dry,
        cdi_max_dry=cdi_max_dry,
        cdi_situation_delta=cdi_situation_delta,
        mean_precip_sum_1m=mean_precip_sum_1m,
        mean_precip_sum_3m=mean_precip_sum_3m,
        precip_index_min=precip_index_min,
        precip_index_max=precip_index_max,
        n_regions_with_precip_deficit=n_precip_deficit,
        n_regions_with_soil_moisture_deficit=n_soil_deficit,
        n_regions_with_vhi_stress=n_vhi_stress,
        max_vhi_index=max_vhi_index,
        discharge=discharge,
    )


_QUALITY_RANK = {"ok": 0, "warning": 1, "error": 2}


def _fold_quality(qualities: list[QualityReport]) -> QualityReport:
    """Combine per-region quality reports into one canton-level report."""
    if not qualities:
        raise ValueError("Cannot fold empty list of QualityReports")
    data_age = max(q.data_age_days for q in qualities)
    coverage = sum(q.coverage_pct for q in qualities) / len(qualities)
    missing: list[str] = []
    flags: list[str] = []
    for q in qualities:
        missing.extend(q.missing_columns)
        flags.extend(q.outlier_flags)
    is_stale = any(q.is_stale for q in qualities)
    overall_key = max(_QUALITY_RANK[q.overall] for q in qualities)
    overall = {v: k for k, v in _QUALITY_RANK.items()}[overall_key]
    return QualityReport(
        data_age_days=data_age,
        coverage_pct=coverage,
        missing_columns=sorted(set(missing)),
        outlier_flags=sorted(set(flags)),
        is_stale=is_stale,
        overall=overall,
    )

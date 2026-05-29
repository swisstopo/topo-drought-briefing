# tests/test_models.py
from datetime import datetime

import pandas as pd

from src.models import (
    CantonReport,
    DataBundle,
    DischargeStats,
    MapSpec,
    QualityReport,
    RegionReport,
    WarnkarteEntry,
)


def test_discharge_stats_dataclass():
    s = DischargeStats(n_total=4, n_low=2, n_very_low=1, pct_low=50)
    assert s.n_total == 4 and s.n_low == 2 and s.n_very_low == 1 and s.pct_low == 50


def test_databundle_station_fields_default_empty():
    b = DataBundle(
        current_df=pd.DataFrame(), historic_df=pd.DataFrame(),
        reference_df=pd.DataFrame(), data_timestamp=datetime(2026, 5, 26), source="fixture",
    )
    assert b.current_stations_df.empty
    assert b.reference_stations_df.empty
    assert b.station_region_map == {}


def test_map_spec_construction():
    spec = MapSpec(
        id="cdi_current",
        title_de="Aktueller CDI",
        title_fr="CDI actuel",
        source="canton.regions[*].cdi",
        style="choropleth_warnregionen",
    )
    assert spec.id == "cdi_current"
    assert spec.style == "choropleth_warnregionen"


def test_warnkarte_entry_construction():
    entry = WarnkarteEntry(
        drought_region_id=34,
        warnlevel=2,
        info_de="Mässige Gefahr",
        info_fr="Danger limité",
        info_it="Pericolo moderato",
        valid_from=datetime(2026, 5, 28),
    )
    assert entry.warnlevel == 2
    assert entry.info_de == "Mässige Gefahr"


def _make_minimal_region_report(rid: int, cdi: int = 2) -> RegionReport:
    return RegionReport(
        region_id=rid,
        region_name_de=f"Region {rid}",
        data_timestamp=datetime(2026, 5, 18),
        source="fixture",
        cdi=cdi,
        spi_3m=-0.5,
        soil_moisture_pct=60.0,
        vhi=50.0,
        cdi_trend=0,
        spi_3m_delta=0.0,
        vhi_delta=0.0,
        pct_critical=0.1,
        spi_3m_percentile=40,
        quality=QualityReport(
            data_age_days=3,
            coverage_pct=1.0,
            missing_columns=[],
            outlier_flags=[],
            is_stale=False,
            overall="ok",
        ),
    )


def test_canton_report_construction():
    regions = [_make_minimal_region_report(34, cdi=2), _make_minimal_region_report(35, cdi=4)]
    canton = CantonReport(
        canton_id=2,
        canton_name_de="Bern",
        canton_name_fr="Berne",
        data_timestamp=datetime(2026, 5, 18),
        source="fixture",
        regions=regions,
        max_warnlevel=4,
        max_warnlevel_info_de="Grosse Gefahr",
        max_warnlevel_info_fr="Danger élevé",
        n_regions_by_precip_index={1: 1, 2: 1},
        n_regions_by_soil_moisture_index={1: 2},
        n_regions_by_hydro_index={1: 1, 2: 1},
        quality=QualityReport(
            data_age_days=3,
            coverage_pct=1.0,
            missing_columns=[],
            outlier_flags=[],
            is_stale=False,
            overall="ok",
        ),
    )
    assert canton.max_warnlevel == 4
    assert len(canton.regions) == 2

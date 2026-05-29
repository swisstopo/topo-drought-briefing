# tests/test_fixture_loader.py
import pytest
from datetime import datetime
from src.data.fixture_loader import load


def test_load_returns_data_bundle():
    bundle = load()
    assert bundle.source == "fixture"
    assert bundle.data_timestamp is not None
    assert isinstance(bundle.data_timestamp, datetime)


def test_current_df_has_expected_columns():
    bundle = load()
    required = {"drought_region_id", "measured_at", "cdi", "spi_3m", "soil_moisture_ufc", "vhi"}
    assert required.issubset(set(bundle.current_df.columns))


def test_current_df_has_berne_regions():
    bundle = load()
    from config.settings import CANTON_TO_REGIONS
    ids_in_data = set(bundle.current_df["drought_region_id"].unique())
    assert CANTON_TO_REGIONS[2].issubset(ids_in_data)


def test_historic_df_has_multiple_weeks():
    bundle = load()
    region_34 = bundle.historic_df[bundle.historic_df["drought_region_id"] == 34]
    assert len(region_34) >= 10


def test_measured_at_is_datetime():
    bundle = load()
    import pandas as pd
    assert pd.api.types.is_datetime64_any_dtype(bundle.current_df["measured_at"])


def test_load_populates_station_data():
    bundle = load()
    assert not bundle.current_stations_df.empty
    assert not bundle.reference_stations_df.empty
    assert bundle.station_region_map  # non-empty dict
    # IDs are strings (leading-zero IDs like "0078" must survive)
    ids = set(bundle.current_stations_df["hydro_station_id"])
    assert "0078" in ids  # leading zero preserved
    assert all(isinstance(k, str) for k in list(bundle.station_region_map)[:5])
    for col in ("doy", "threshold1", "q347", "label"):
        assert col in bundle.reference_stations_df.columns

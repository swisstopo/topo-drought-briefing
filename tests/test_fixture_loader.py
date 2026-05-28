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
    from config.settings import BERNE_REGION_IDS
    ids_in_data = set(bundle.current_df["drought_region_id"].unique())
    assert BERNE_REGION_IDS.issubset(ids_in_data)


def test_historic_df_has_multiple_weeks():
    bundle = load()
    region_34 = bundle.historic_df[bundle.historic_df["drought_region_id"] == 34]
    assert len(region_34) >= 10


def test_measured_at_is_datetime():
    bundle = load()
    import pandas as pd
    assert pd.api.types.is_datetime64_any_dtype(bundle.current_df["measured_at"])

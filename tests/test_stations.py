from datetime import datetime

import pandas as pd

from src.aggregation.stations import compute_discharge_stats
from src.models import DataBundle


def _bundle(current_rows, ref_rows, mapping):
    return DataBundle(
        current_df=pd.DataFrame(), historic_df=pd.DataFrame(),
        reference_df=pd.DataFrame(), data_timestamp=datetime(2026, 5, 26), source="fixture",
        current_stations_df=pd.DataFrame(current_rows),
        reference_stations_df=pd.DataFrame(ref_rows),
        station_region_map=mapping,
    )


def test_counts_low_and_very_low():
    # doy for 2025-05-26 is 146
    cur = [
        {"hydro_station_id": "0078", "measured_at": datetime(2025, 5, 26), "value": 2.0, "label": "Abfluss"},  # < q347 -> very low (and low)
        {"hydro_station_id": "2009", "measured_at": datetime(2025, 5, 26), "value": 4.0, "label": "Abfluss"},  # < threshold1, > q347 -> low only
        {"hydro_station_id": "2004", "measured_at": datetime(2025, 5, 26), "value": 9.0, "label": "Abfluss"},  # ok
        {"hydro_station_id": "2007", "measured_at": datetime(2025, 5, 26), "value": 100.0, "label": "Wasserstand"},  # ignored
    ]
    ref = [
        {"hydro_station_id": "0078", "doy": 146, "threshold1": 5.0, "q347": 3.0, "label": "Abfluss"},
        {"hydro_station_id": "2009", "doy": 146, "threshold1": 5.0, "q347": 3.0, "label": "Abfluss"},
        {"hydro_station_id": "2004", "doy": 146, "threshold1": 5.0, "q347": 3.0, "label": "Abfluss"},
    ]
    mapping = {"0078": 33, "2009": 33, "2004": 33, "2007": 33}
    stats = compute_discharge_stats([33], _bundle(cur, ref, mapping))
    assert stats.n_total == 3
    assert stats.n_low == 2
    assert stats.n_very_low == 1
    assert stats.pct_low == 67  # round(2/3*100)


def test_filters_by_region():
    cur = [
        {"hydro_station_id": "0078", "measured_at": datetime(2025, 5, 26), "value": 2.0, "label": "Abfluss"},
        {"hydro_station_id": "2009", "measured_at": datetime(2025, 5, 26), "value": 2.0, "label": "Abfluss"},
    ]
    ref = [
        {"hydro_station_id": "0078", "doy": 146, "threshold1": 5.0, "q347": 3.0, "label": "Abfluss"},
        {"hydro_station_id": "2009", "doy": 146, "threshold1": 5.0, "q347": 3.0, "label": "Abfluss"},
    ]
    mapping = {"0078": 33, "2009": 41}
    stats = compute_discharge_stats([33], _bundle(cur, ref, mapping))
    assert stats.n_total == 1


def test_zero_stations():
    stats = compute_discharge_stats([99], _bundle([], [], {}))
    assert stats.n_total == 0
    assert stats.pct_low == 0
    assert stats.n_low == 0 and stats.n_very_low == 0


def test_skips_station_without_reference_row():
    cur = [{"hydro_station_id": "0078", "measured_at": datetime(2025, 5, 26), "value": 2.0, "label": "Abfluss"}]
    ref = [{"hydro_station_id": "2009", "doy": 146, "threshold1": 5.0, "q347": 3.0, "label": "Abfluss"}]
    stats = compute_discharge_stats([33], _bundle(cur, ref, {"0078": 33, "2009": 33}))
    assert stats.n_total == 0

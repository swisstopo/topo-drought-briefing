# tests/test_models.py
from src.models import MapSpec


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

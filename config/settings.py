# config/settings.py
from pathlib import Path
from typing import Final

DATA_DIR: Final[Path] = Path(__file__).parent.parent / "data"

BERNE_REGION_NAMES: Final[dict[int, str]] = {
    33: "Unteres Emmental",
    34: "Berner Mittelland",
    35: "Westliches Berner Oberland",
    37: "Oberaargau",
    38: "Oberes Emmental",
    41: "Östliches Berner Oberland",
}

CDI_LABELS: Final[dict[int, str]] = {
    0: "Keine Trockenheit",
    1: "Leichte Trockenheit",
    2: "Erhebliche Trockenheit",
    3: "Schwere Trockenheit",
    4: "Extreme Trockenheit",
    5: "Ausserordentliche Trockenheit",
}

CDI_LABELS_FR: Final[dict[int, str]] = {
    0: "Pas de sécheresse",
    1: "Sécheresse légère",
    2: "Sécheresse notable",
    3: "Sécheresse sévère",
    4: "Sécheresse extrême",
    5: "Sécheresse exceptionnelle",
}

CDI_COLOURS: Final[dict[int, str]] = {
    0: "#2ecc71",
    1: "#f1c40f",
    2: "#e67e22",
    3: "#e74c3c",
    4: "#8e44ad",
    5: "#2c3e50",
}

STAC_BASE_URL: Final[str] = "https://data.geo.admin.ch/api/stac/v1"
STAC_COLLECTION: Final[str] = "ch.bafu.trockenheitsdaten-numerisch"

VHI_URL: Final[str] = (
    "https://data.geo.admin.ch/ch.swisstopo.swisseo_vhi_v100"
    "/swisseo_vhi_v100"
    "/ch.swisstopo.swisseo_vhi_v100_current_vegetation-warnregions.csv"
)
VHI_FIXTURE: Final[Path] = DATA_DIR / "vhi_fixture.csv"

CURRENT_ZIP_NAME: Final[str] = (
    "trockenheitsdaten-numerisch_current__trockenheitsdaten-numerisch_current.csv.zip"
)
HISTORIC_ZIP_NAME: Final[str] = (
    "trockenheitsdaten-numerisch_historic__trockenheitsdaten-numerisch_historic.csv.zip"
)
REFERENCE_ZIP_NAME: Final[str] = (
    "trockenheitsdaten-numerisch_reference__trockenheitsdaten-numerisch_reference.csv.zip"
)

GEOJSON_FIXTURE: Final[Path] = DATA_DIR / "berne_warnregionen.geojson"

# Canton → drought region mapping.
# Bern is the launch canton. Other cantons will be added when their
# canton→regions mapping is curated.
CANTON_TO_REGIONS: Final[dict[int, frozenset[int]]] = {
    2: frozenset({33, 34, 35, 37, 38, 41}),  # Bern (BFS canton ID 2)
}

CANTON_NAMES: Final[dict[int, dict[str, str]]] = {
    2: {"de": "Bern", "fr": "Berne", "it": "Berna"},
}

DATA_STALENESS_DAYS: Final[int] = 14
INDICATOR_COLUMNS: Final[list[str]] = [
    "cdi", "spi_3m", "soil_moisture_ufc", "vhi",
    "spi_1m", "spi_6m", "spi_12m", "spi_24m",
    "precip_sum_1m", "precip_sum_3m",
]

# config/settings.py
from pathlib import Path
from typing import Final
import json
import re

DATA_DIR: Final[Path] = Path(__file__).parent.parent / "data"

_KANTONE = json.loads((DATA_DIR / "kantone_warnregionen.json").read_text(encoding="utf-8"))

if not _KANTONE:
    raise ValueError("kantone_warnregionen.json is empty or could not be parsed")

_MAPGEO_RE = re.compile(r"center=(\d+),(\d+)")


def _parse_mapgeo(mapgeo: str) -> tuple[int, int]:
    m = _MAPGEO_RE.search(mapgeo)
    if not m:
        raise ValueError(f"Cannot parse MAPGEO center coordinates: {mapgeo!r}")
    return (int(m.group(1)), int(m.group(2)))


# Center points for all 26 cantons from JSON. Bern's center is from JSON (fine);
# only Bern's region set is overridden below.
CANTON_CENTER_POINTS: Final[dict[int, tuple[int, int]]] = {
    entry["KANTONSNUM"]: _parse_mapgeo(entry["MAPGEO"])
    for entry in _KANTONE
}

BERNE_REGION_NAMES: Final[dict[int, str]] = {
    33: "Unteres Emmental",
    34: "Berner Mittelland",
    35: "Westliches Berner Oberland",
    37: "Oberaargau",
    38: "Oberes Emmental",
    41: "Östliches Berner Oberland",
}

# German names for all 38 Swiss drought warning regions, derived from JSON.
REGION_NAMES_DE: Final[dict[int, str]] = {
    r["REGION_NR"]: r["Name"]
    for entry in _KANTONE
    for r in entry["warnregionen"]
}

# French names for all 38 Swiss drought warning regions.
REGION_NAMES_FR: Final[dict[int, str]] = {
    31: "Jura oriental",
    32: "Balsthal",
    33: "Basse-Emmental",
    34: "Mittelland bernois",
    35: "Oberland bernois occidental",
    36: "Pays de Gruyère",
    37: "Haute-Argovie",
    38: "Haute-Emmental",
    39: "Freiamt",
    40: "Suisse centrale occidentale",
    41: "Oberland bernois oriental",
    42: "Moyen Pays oriental",
    43: "Bassin du lac de Zurich",
    44: "Suisse centrale orientale",
    45: "Alpes uranaises",
    46: "Surselva",
    47: "Alpstein",
    48: "Alpes de Glaris",
    49: "Grisons centraux nord",
    50: "Grisons centraux sud",
    51: "Vallée du Rhin",
    52: "Prättigau",
    53: "Franches-Montagnes",
    54: "Jura occidental",
    55: "Moyen Pays occidental",
    56: "Bassin lémanique",
    57: "Chablais",
    58: "Alpes valaisannes méridionales",
    59: "Valais septentrional",
    60: "Vallées de Viège",
    61: "Conches",
    62: "Tessin occidental",
    63: "Tessin septentrional",
    64: "Tessin oriental",
    65: "Sottoceneri",
    66: "Vallées méridionales des Grisons",
    67: "Haute-Engadine",
    68: "Basse-Engadine",
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

CURRENT_STATIONS_CSV: Final[str] = "weekly_current_stations.csv"
REFERENCE_STATIONS_CSV: Final[str] = "daily_reference_stations.csv"
STATION_REGION_MAP_NAME: Final[str] = "station_region_mapping.json"

GEOJSON_FIXTURE: Final[Path] = DATA_DIR / "berne_warnregionen.geojson"

CANTON_NAMES: Final[dict[int, dict[str, str]]] = {
    1:  {"de": "Zürich",                    "fr": "Zurich"},
    2:  {"de": "Bern",                      "fr": "Berne",    "it": "Berna"},
    3:  {"de": "Luzern",                    "fr": "Lucerne"},
    4:  {"de": "Uri",                       "fr": "Uri"},
    5:  {"de": "Schwyz",                    "fr": "Schwytz"},
    6:  {"de": "Obwalden",                  "fr": "Obwald"},
    7:  {"de": "Nidwalden",                 "fr": "Nidwald"},
    8:  {"de": "Glarus",                    "fr": "Glaris"},
    9:  {"de": "Zug",                       "fr": "Zoug"},
    10: {"de": "Fribourg",                  "fr": "Fribourg"},
    11: {"de": "Solothurn",                 "fr": "Soleure"},
    12: {"de": "Basel-Stadt",               "fr": "Bâle-Ville"},
    13: {"de": "Basel-Landschaft",          "fr": "Bâle-Campagne"},
    14: {"de": "Schaffhausen",              "fr": "Schaffhouse"},
    15: {"de": "Appenzell Ausserrhoden",    "fr": "Appenzell Rhodes-Extérieures"},
    16: {"de": "Appenzell Innerrhoden",     "fr": "Appenzell Rhodes-Intérieures"},
    17: {"de": "St. Gallen",               "fr": "Saint-Gall"},
    18: {"de": "Graubünden",               "fr": "Grisons"},
    19: {"de": "Aargau",                   "fr": "Argovie"},
    20: {"de": "Thurgau",                  "fr": "Thurgovie"},
    21: {"de": "Ticino",                   "fr": "Tessin"},
    22: {"de": "Vaud",                     "fr": "Vaud"},
    23: {"de": "Valais",                   "fr": "Valais"},
    24: {"de": "Neuchâtel",               "fr": "Neuchâtel"},
    25: {"de": "Genève",                   "fr": "Genève"},
    26: {"de": "Jura",                     "fr": "Jura"},
}

# Canton → drought region mapping.
# Bern is the launch canton with a curated subset (excludes Freiberge etc.).
# All other cantons are loaded from kantone_warnregionen.json.
CANTON_TO_REGIONS: Final[dict[int, frozenset[int]]] = {
    2: frozenset({33, 34, 35, 37, 38, 41}),  # Bern – curated subset (excludes Freiberge etc.)
    **{
        entry["KANTONSNUM"]: frozenset(r["REGION_NR"] for r in entry["warnregionen"])
        for entry in _KANTONE
        if entry["KANTONSNUM"] != 2
    },
}

DATA_STALENESS_DAYS: Final[int] = 14
INDICATOR_COLUMNS: Final[list[str]] = [
    "cdi", "spi_3m", "soil_moisture_ufc", "vhi",
    "spi_1m", "spi_6m", "spi_12m", "spi_24m",
    "precip_sum_1m", "precip_sum_3m",
]

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

All dev operations run inside Docker via `make`:

```bash
make build       # Build Docker image
make up          # Run Streamlit app at http://localhost:8501 (hot-reload on save)
make run-tests   # Run full test suite in Docker
make shell       # Open bash shell in app container
make down        # Stop containers
```

To run tests locally (requires `uv`):
```bash
uv run pytest tests/ -v
uv run pytest tests/test_aggregation.py -v   # single file
uv run pytest -k test_name                   # single test by name
```

The Docker image uses `uv` with a fixed venv at `/venv` (`UV_PROJECT_ENVIRONMENT=/venv`). Chromium is bundled in the image for kaleido PNG export.

## Architecture

Pipeline-first: **DataBundle → CantonReport → BriefingDocument → UI/Export**. Each stage is a typed dataclass defined in `src/models.py`. `app.py` is thin — it calls the pipeline and renders. No Streamlit imports exist outside `app.py`.

**Data layer** (`src/data/`):
- `stac_client.py` is the public entry point (`load()`). It tries a live STAC fetch but `_fetch_from_stac()` raises `NotImplementedError` intentionally, so it always falls back to fixture data via `fixture_loader.load()`.
- `fixture_loader.py` reads five bundled datasets from `data/` (three drought CSVs in ZIPs + two hydro-station CSVs in ZIPs). Semicolon-separated, `#`-prefixed comment lines. Station CSVs are read via `_read_stations_csv()` which forces `hydro_station_id` to `str` (leading zeros matter). Also loads `data/station_region_mapping.json` into `DataBundle.station_region_map`. Parses the data timestamp from comment headers. Returns a `DataBundle`.
- `warnkarte_client.py::fetch_for_regions()` fetches official BAFU warning levels per region from the geo.admin.ch REST API. Falls back to `data/warnkarte_fixture.json` on any network or HTTP error. Refresh the fixture via `scripts/refresh_warnkarte_fixture.py`.
- `vhi_client.py::fetch_for_regions()` fetches VHI (Vegetation Health Index) per region from the SwissEO REST endpoint. Falls back to `data/vhi_fixture.csv` on any error. Returns `{region_id: vhi_mean}`. The VHI value is passed as `vhi_value` override into `compute_region_report()` — it does not come from the CDI CSV.

**Aggregation layer** (`src/aggregation/`):
- `regional.py::compute_region_report()` filters `current_df` to rows where `cdi.notna()` before taking the latest row — the fixture has trailing all-NaN placeholder rows that must be excluded. Accepts optional `vhi_value` override (from `vhi_client`) and `warnkarte_entry`; if no warnkarte entry, falls back to `max(cdi, 1)`. Also calls `_compute_hydro_stations()` (private helper in the same file) which builds `list[HydroStationReport]` from `bundle.station_region_map` and the station DataFrames — no JSON file is loaded at this stage.
- `canton.py::compute_canton_report()` calls `compute_region_report()` for every region in `CANTON_TO_REGIONS[canton_id]`, folds the results into a `CantonReport`, and merges per-region `QualityReport`s via `_fold_quality()` (worst-case wins).
- `stations.py::compute_discharge_stats(region_ids, bundle)` counts discharge stations with low/very-low flow. Filters `current_stations_df` to `label == "Abfluss"` and the target regions (via `bundle.station_region_map`), joins to `reference_stations_df` on `(hydro_station_id, doy)` to get `threshold1` (low) and `q347` (very low). Returns a `DischargeStats`. Refresh `station_region_mapping.json` via `scripts/extract_station_mappings.py`.
- `indicators.py` holds pure helpers: `compute_pct_critical`, `compute_percentile`, `compute_trend`.
- Forecast: `DataBundle.forecast_df` feeds `_forecast_week2_value()` in `regional.py`, which finds the forecast row closest to today+14d (within 5 days) for any column. `_compute_cdi_forecast_week2()` wraps it for `cdi_p50`. Results stored as `RegionReport.cdi_forecast_week2`, `precip_1m_index_forecast`, `soil_moisture_index_forecast`.

**Briefing layer** (`src/briefing/`):
- `renderer.py::load_ruleset()` loads and validates `data/ruleset/canton-bulletin.yaml` via Pydantic (`schemas.py::RulesetSchema`).
- `renderer.py::render_briefing()` renders each section using Jinja2. Templates in the YAML use Handlebars-style syntax — `_handlebars_to_jinja2()` converts `{{#each …}}`, `{{/each}}`, `{{#if …}}`, `{{/if}}`, and `{{this.field}}` before rendering. `StrictUndefined` catches typos in placeholder names at render time.
- Jinja2 template globals available in YAML templates: `canton` (CantonReport), `deficit_range(min_idx, max_idx, key)`, `trend(delta, key)`, `plural(n, singular, plural)`, `nomenclature`, `handlungsempfehlungen`, `data_sources`, `references`.
- The YAML ruleset (`data/ruleset/canton-bulletin.yaml`) is the single source of truth for bulletin content: section templates, nomenclature (index→text), trend wording, `handlungsempfehlungen`, lead block, `banner` links, and `weiterfuehrende_links`. Edit the YAML to change bulletin text — do not hardcode strings in Python.
- `weiterfuehrende_links[].url` can be a plain string or a dict keyed by BFS canton ID — this allows canton-specific deep links. Links with no matching canton ID are silently dropped by `render_briefing()`.

**Viz layer** (`src/viz/`):
- `maps.py::build_canton_map()` returns a folium map coloured by CDI/warnlevel per region (interactive, Streamlit only).
- `maps.py::build_export_map()` renders the same map as static PNG bytes via matplotlib/geopandas — used by the HTML export pipeline.
- `charts.py` produces a Plotly dual-axis figure: CDI bars (left) + SPI-3m line (right), 52 weeks.

**Export layer** (`src/export/report.py`):
- `to_html()` produces a self-contained HTML string with inline CSS, embedded chart PNG (via kaleido), and the static map PNG. No external URLs — required for government infra.

**Quality layer** (`src/quality/checks.py`):
- `run_quality_checks()` returns a `QualityReport` with staleness (>14 days = error), coverage, missing columns, and IQR×3 outlier flags. Attached to every `RegionReport` and folded into `CantonReport`.

**i18n layer** (`src/i18n/strings.py`):
- `t(key, lang)` looks up UI strings; falls back to German if key or lang is missing.
- `get_cdi_labels(lang)` and `get_region_names(lang)` return lang-specific dicts. Supported languages: `"de"` and `"fr"`.

## Key Models (`src/models.py`)

All pipeline stages are typed dataclasses:
- `DataBundle` — raw DataFrames (current, historic, reference, forecast) + station DataFrames (`current_stations_df`, `reference_stations_df`) + `station_region_map: dict[str, int]` (hydro_station_id → region_id) + source tag. Station fields and `station_region_map` default to empty.
- `HydroStationReport` — per-station discharge snapshot for display: `station_id`, `station_name`, `current_value`, `threshold1`, `min_value` (all floats, NaN-safe).
- `DischargeStats` — aggregate discharge health for a region set: `n_total`, `n_low` (below threshold1), `n_very_low` (below q347), `pct_low`.
- `QualityReport` — per-dataset health: `data_age_days`, `coverage_pct`, `missing_columns`, `outlier_flags`, `is_stale`, `overall` (ok/warning/error).
- `RegionReport` — per-region indicators: CDI (0–5), SPI, soil moisture, VHI, precip sums, sub-index levels (precip_1m_index / soil_moisture_index / hydro_index, each 1–5), warnlevel, forecast fields (`cdi_forecast_week2`, `precip_1m_index_forecast`, `soil_moisture_index_forecast`), deficit deltas (`precip_deficit_delta`, `soil_moisture_deficit_delta`), `discharge: DischargeStats` (aggregate counts), `hydro_stations: list[HydroStationReport]` (per-station detail for the UI table), quality.
- `CantonReport` — aggregated canton view: list of `RegionReport`, max warnlevel, region counts by index, folded quality, canton-level aggregates (`n_regions_dry`, `cdi_min_dry`, `cdi_max_dry`, `cdi_situation_delta`, `mean_precip_sum_1m/3m`, `n_regions_with_precip/soil_moisture_deficit`, `discharge: DischargeStats`).
- `WarnkarteEntry` — BAFU warning level (1–5) + bilingual info text + `valid_from` date.
- `MapSpec` — descriptor for a map panel: `id`, bilingual titles, `source` (path expression into CantonReport), `style` (renderer hint, e.g. `"choropleth_warnregionen"`).
- `BriefingDocument` — rendered section strings, lead headline/meta, `MapSpec` list, `banner` links, `weiterfuehrende_links`, locale.

## Deployment

Two deployment targets:

1. **Docker (dev/prod server):** `make up` — full Streamlit app with folium maps and HTML export.
2. **GitHub Pages (static):** `docs/index.html` bootstraps the app via [stlite](https://github.com/whitphx/stlite) (Pyodide-based Streamlit in the browser). CI (`deploy.yml`) rsync-copies the repo to `_site/` on every push to `main`. The stlite build lists all source files explicitly — **update `docs/index.html` when adding or removing source files**. The file list can drift: if stlite references a path that no longer exists, the browser app will silently 404 on it.

## Key Constants (`config/settings.py`)

`settings.py` loads `data/kantone_warnregionen.json` at import time (`_KANTONE`) to derive several constants:

- `CANTON_TO_REGIONS` — maps all 26 BFS canton IDs to their drought Warnregionen. Bern (ID 2) is hardcoded to a curated 6-region subset `{33,34,35,37,38,41}` (excludes region 53 Freiberge, which belongs to Canton Jura). All other 25 cantons use the full region list from the JSON.
- `CANTON_NAMES` — bilingual (de/fr) canton names for all 26 cantons, hardcoded.
- `CANTON_CENTER_POINTS` — LV95 center coordinates per canton, parsed from the `MAPGEO` field in the JSON.
- `REGION_NAMES_DE` — German names for all 38 Swiss drought warning regions, derived from the JSON.
- `REGION_NAMES_FR` — French names for all 38 regions, hardcoded.
- `DATA_STALENESS_DAYS = 14` — threshold for quality error status.
- `INDICATOR_COLUMNS` — the 10 columns expected in `current_df`; used to compute coverage %.
- `CURRENT_STATIONS_CSV`, `REFERENCE_STATIONS_CSV`, `STATION_REGION_MAP_NAME` — filenames for the hydro station datasets.

## Data Notes

- CSV files inside the ZIPs use `;` separator and `#`-prefixed comment lines.
- Dates are formatted `DD.MM.YYYY` and parsed in `fixture_loader._parse_dates()`.
- `soil_moisture_ufc` in the CSV maps to `soil_moisture_pct` in `RegionReport`.
- VHI can legitimately be NaN — guard with `math.isnan()` before formatting or displaying.
- `warnlevel` on `RegionReport` comes from `WarnkarteEntry` (BAFU API / fixture), not the CDI CSV. It is the official BAFU Gefahrenstufe (1–5) and is the source of truth for action recommendations.
- `station_region_map` keys are strings (hydro_station_id with leading zeros preserved); values are int region IDs. Refresh via `scripts/extract_station_mappings.py`.
- Station CSVs must be parsed with `dtype={"hydro_station_id": str}` — leading zeros are significant and `_read_stations_csv()` / `_parse_stations_from_zip_bytes()` enforce this.

## Canton View Layout (`app.py`)

The canton view uses a three-block structure:
1. Full-width warnlevel badge (+ optional banner links)
2. Two equal columns: left = `allgemeine-lage` section text; right = map switcher + CDI legend
3. Full-width remaining sections (`handlungsoptionen`, `datenquellen`, weiterführende Links)

The regionale lage table (regions view) is a 5-column layout: Warnstufe badge | Region name (hyperlinked) | Situation | Allgemeine Lage | Expert notes. The **Situation** column iterates `r.hydro_stations` to show per-station Abfluss value, T1 threshold, and historic minimum; falls back to a "Keine Stationen/Daten" placeholder when the list is empty.

The map switcher is `st.radio(horizontal=True)` keyed on `selected_canton_id`. It renders only the active `MapSpec` — `st.tabs()` was deliberately avoided because Leaflet maps inside hidden tabs initialise at 0×0 and never recover when the tab is shown.

## Expert Notes

`app.py` stores per-region free-text notes in `st.session_state.expert_notes` (keyed `expert_<region_id>`). These are injected into the HTML export via `to_html(..., expert_notes=st.session_state.expert_notes)`. Notes persist for the browser session only.

## Testing

HTTP clients (`warnkarte_client`, `vhi_client`) are tested using the `responses` library (registered in `[dependency-groups] dev`), which intercepts `requests` calls without a live network. To add a new HTTP client test, patch via `@responses.activate` and register mock URLs with `responses.add()`.

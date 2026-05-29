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
- `fixture_loader.py` reads three bundled ZIPs from `data/` (semicolon-separated CSVs, `#`-prefixed comment lines). Parses the data timestamp from comment headers. Returns a `DataBundle`.
- `warnkarte_client.py::fetch_for_regions()` fetches official BAFU warning levels per region from the geo.admin.ch REST API. Falls back to `data/warnkarte_fixture.json` on any network or HTTP error. Refresh the fixture via `scripts/refresh_warnkarte_fixture.py`.

**Aggregation layer** (`src/aggregation/`):
- `regional.py::compute_region_report()` filters `current_df` to rows where `cdi.notna()` before taking the latest row — the fixture has trailing NaN rows dated 2026-05-25 that must be excluded.
- `canton.py::compute_canton_report()` calls `compute_region_report()` for every region in `CANTON_TO_REGIONS[canton_id]`, folds the results into a `CantonReport`, and merges per-region `QualityReport`s via `_fold_quality()` (worst-case wins).
- `indicators.py` holds pure helpers: `compute_pct_critical`, `compute_percentile`, `compute_trend`.

**Briefing layer** (`src/briefing/`):
- `renderer.py::load_ruleset()` loads and validates `data/ruleset/canton-bulletin.yaml` via Pydantic (`schemas.py::RulesetSchema`).
- `renderer.py::render_briefing()` renders each section using Jinja2. Templates in the YAML use Handlebars-style loops (`{{#each …}}`) — `_handlebars_to_jinja2()` converts them before rendering. `StrictUndefined` catches typos in placeholder names at render time.
- The YAML ruleset (`data/ruleset/canton-bulletin.yaml`) is the single source of truth for bulletin content: section templates, nomenclature (index→text), trend wording, action recommendations (`handlungsempfehlungen`), and the lead block. Edit the YAML to change bulletin text — do not hardcode strings in Python.

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
- `DataBundle` — raw DataFrames (current, historic, reference, forecast) + source tag. `forecast_df` defaults to an empty DataFrame.
- `QualityReport` — per-dataset health: `data_age_days`, `coverage_pct`, `missing_columns`, `outlier_flags`, `is_stale`, `overall` (ok/warning/error).
- `RegionReport` — per-region indicators: CDI, SPI, soil moisture, VHI, precip sums, index levels (1–5), warnlevel, quality.
- `CantonReport` — aggregated canton view: list of `RegionReport`, max warnlevel, region counts by index, folded quality.
- `WarnkarteEntry` — BAFU warning level (1–5) + bilingual info text + `valid_from` date.
- `MapSpec` — descriptor for a map panel: `id`, bilingual titles, `source` (path expression into CantonReport), `style` (renderer hint, e.g. `"choropleth_warnregionen"`).
- `BriefingDocument` — rendered section strings, lead headline/meta, `MapSpec` list, locale.

## Deployment

Two deployment targets:

1. **Docker (dev/prod server):** `make up` — full Streamlit app with folium maps and HTML export.
2. **GitHub Pages (static):** `docs/index.html` bootstraps the app via [stlite](https://github.com/whitphx/stlite) (Pyodide-based Streamlit in the browser). CI (`deploy.yml`) rsync-copies the repo to `_site/` on every push to `main`. The stlite build lists all source files explicitly — update `docs/index.html` when adding new source files.

## Key Constants (`config/settings.py`)

- `CANTON_TO_REGIONS = {2: frozenset({33, 34, 35, 37, 38, 41})}` — maps BFS canton ID to its drought Warnregionen. Bern (ID 2) is the launch canton; region 53 Freiberge is Canton Jura and excluded.
- `CANTON_NAMES` — bilingual canton names keyed by BFS canton ID.
- `DATA_STALENESS_DAYS = 14` — threshold for quality error status.
- `INDICATOR_COLUMNS` — the 10 columns expected in `current_df`; used to compute coverage %.

## Data Notes

- CSV files inside the ZIPs use `;` separator and `#`-prefixed comment lines.
- Dates are formatted `DD.MM.YYYY` and parsed in `fixture_loader._parse_dates()`.
- `soil_moisture_ufc` in the CSV maps to `soil_moisture_pct` in `RegionReport`.
- VHI can legitimately be NaN — guard with `math.isnan()` before formatting or displaying.
- `warnlevel` on `RegionReport` comes from `WarnkarteEntry` (BAFU API / fixture), not the CDI CSV. It is the official BAFU Gefahrenstufe (1–5) and is the source of truth for action recommendations.

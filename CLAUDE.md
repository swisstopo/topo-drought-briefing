# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the app
uv run streamlit run app.py

# Run all tests
uv run pytest tests/ -v

# Run a single test
uv run pytest tests/test_aggregation.py::test_region_report_basic_fields -v

# Add a dependency
uv add <package>

# Add a dev dependency
uv add --dev <package>
```

## Architecture

Pipeline-first: **DataBundle → RegionReport → BriefingDocument → UI/Export**. Each stage is a typed dataclass defined in `src/models.py`. `app.py` is thin — it calls the pipeline and renders. No Streamlit imports exist outside `app.py`.

**Data layer** (`src/data/`):
- `stac_client.py` is the public entry point (`load()`). It tries a live STAC fetch but `_fetch_from_stac()` raises `NotImplementedError` intentionally, so it always falls back to fixture data via `fixture_loader.load()`.
- `fixture_loader.py` reads three bundled ZIPs from `data/` (semicolon-separated CSVs, `#`-prefixed comment lines). Parses the data timestamp from comment headers. Returns a `DataBundle`.

**Aggregation layer** (`src/aggregation/`):
- `regional.py::compute_region_report()` filters `current_df` to rows where `cdi.notna()` before taking the latest row — the fixture has trailing NaN rows dated 2026-05-25 that must be excluded.
- `indicators.py` holds pure helpers: `compute_pct_critical`, `compute_percentile`, `compute_trend`.

**Briefing layer** (`src/briefing/`):
- `text_blocks.py` holds nested dicts `LAGE_BLOCKS[mode][cdi_level]`, `ENTWICKLUNG_BLOCKS`, `EINORDNUNG_BLOCKS`, `DATENGRUNDLAGE_BLOCKS` — all German with proper umlauts (ä, ö, ü, ß).
- `template.py::build_briefing()` fills slots via `.format(**kwargs)`. Uses `_safe_num()` to replace NaN with 0.0 before formatting — VHI is NaN for some regions (e.g. region 37 Oberaargau).

**Viz layer** (`src/viz/`):
- `maps.py` has two paths: `build_map()` returns a folium map (interactive, Streamlit only), `build_export_map()` returns PNG bytes via matplotlib/geopandas (folium can't produce PNG).
- `charts.py` produces a Plotly dual-axis figure: CDI bars (left) + SPI-3m line (right), 52 weeks.

**Export layer** (`src/export/report.py`):
- `to_html()` produces a self-contained HTML string with inline CSS, embedded chart PNG (via kaleido), and the static map PNG. No external URLs — required for government infra.
- `to_pdf()` passes the HTML string to WeasyPrint.

**Quality layer** (`src/quality/checks.py`):
- `run_quality_checks()` returns a `QualityReport` with staleness (>14 days = error), coverage, missing columns, and IQR×3 outlier flags. Attached to every `RegionReport`.

## Key Constants (`config/settings.py`)

- `BERNE_REGION_IDS = {33, 34, 35, 37, 38, 41}` — the 6 Kanton Bern Warnregionen (region 53 Freiberge is Canton Jura, excluded).
- `DATA_STALENESS_DAYS = 14` — threshold for quality error status.
- `INDICATOR_COLUMNS` — the 10 columns expected in `current_df`; used to compute coverage %.

## Data Notes

- CSV files inside the ZIPs use `;` separator and `#`-prefixed comment lines.
- Dates are formatted `DD.MM.YYYY` and parsed in `fixture_loader._parse_dates()`.
- `soil_moisture_ufc` in the CSV maps to `soil_moisture_pct` in `RegionReport`.
- VHI can legitimately be NaN — guard with `math.isnan()` before formatting or displaying.

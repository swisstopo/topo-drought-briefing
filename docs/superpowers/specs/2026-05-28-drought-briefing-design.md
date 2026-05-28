# Design: One Click Drought Briefing

**Date:** 2026-05-28  
**Project:** GovTech 2026 — trockenheit.admin.ch  
**Status:** Approved

---

## Scope

Automated drought situation report generator for Swiss authorities, scoped to **Kanton Bern**. A user picks one of the 6–7 Berne Warnregionen and the app generates a drought briefing (web view + PDF/HTML export) from open Swiss federal data. The app always shows the **current snapshot** (latest available data); no date picker.

**Berne Warnregion IDs (config/settings.py):**

| ID | Name (DE) |
|----|-----------|
| 33 | Unteres Emmental |
| 34 | Berner Mittelland |
| 35 | Westliches Berner Oberland |
| 37 | Oberaargau |
| 38 | Oberes Emmental |
| 41 | Östliches Berner Oberland |

Region 53 (Freiberge/Franches-Montagnes) is canton Jura — excluded.

---

## Architecture

Pipeline-first: **fetch → aggregate → template → render**. Four distinct, testable layers communicating through typed dataclasses. `app.py` is thin — it calls the pipeline and renders results. No Streamlit imports in pipeline code.

```
DataBundle  →  RegionReport  →  BriefingDocument  →  Streamlit UI / Export
(data layer)   (aggregation)    (briefing layer)       (render layer)
```

Quality flags are computed in the aggregation layer and attached to `RegionReport`; they surface in both the UI and export without extra wiring.

---

## Directory Structure

```
drought-briefing/
├── app.py                        # Streamlit entry point (thin)
├── requirements.txt
├── config/
│   └── settings.py               # API endpoints, Berne region IDs, CDI thresholds, colours
├── data/                         # Bundled fixture ZIPs (already present)
│   ├── trockenheitsdaten-numerisch_current__*.zip
│   ├── trockenheitsdaten-numerisch_historic__*.zip
│   └── trockenheitsdaten-numerisch_reference__*.zip
├── src/
│   ├── data/
│   │   ├── fixture_loader.py     # Reads bundled ZIPs → DataBundle
│   │   └── stac_client.py        # BGDI STAC API → falls back to fixture_loader
│   ├── aggregation/
│   │   ├── regional.py           # Filter to region, compute RegionReport
│   │   └── indicators.py         # Trend, pct_critical, percentiles
│   ├── briefing/
│   │   ├── text_blocks.py        # Rule-based text keyed on CDI level × mode
│   │   └── template.py           # Assembles four briefing sections
│   ├── viz/
│   │   ├── maps.py               # Folium choropleth of Berne Warnregionen
│   │   └── charts.py             # Plotly time-series (CDI + SPI-3m, 52 weeks)
│   ├── quality/
│   │   └── checks.py             # Coverage, recency, missing-data, outlier flags
│   └── export/
│       └── report.py             # to_html() → str, to_pdf(html) → bytes (WeasyPrint)
└── tests/
    ├── test_aggregation.py
    ├── test_quality.py
    └── test_text_blocks.py
```

---

## Data Layer

### DataBundle (dataclass)

```python
@dataclass(frozen=True)
class DataBundle:
    current_df: pd.DataFrame    # weekly_current_regions.csv — latest CDI/SPI/VHI per region
    historic_df: pd.DataFrame   # weekly_historic_regions.csv — back to 1991
    reference_df: pd.DataFrame  # regions.csv + daily_reference_regions.csv — 1961–2020 percentiles
    data_timestamp: datetime     # parsed from CSV header "# letzte Aktualisierung"
    source: Literal["api", "fixture"]
```

### fixture_loader.py

Reads the three bundled ZIPs from `data/`. Parses the comment header to extract `data_timestamp`. Returns a `DataBundle` with `source="fixture"`.

Relevant CSV files used:
- `weekly_current_regions.csv` — current indicators
- `weekly_historic_regions.csv` — 52-week history for time-series
- `regions.csv` — region name lookup
- `daily_reference_regions.csv` — percentile reference values

### stac_client.py

Attempts live fetch from BGDI STAC collection `ch.bafu.trockenheitsdaten-numerisch`. On any `requests.RequestException` or non-200 response, logs `WARNING: falling back to fixture data` and delegates to `fixture_loader.load()`. The switch is transparent to all callers.

**Endpoint:** `https://data.geo.admin.ch/api/stac/v0.9/collections/ch.bafu.trockenheitsdaten-numerisch`

---

## Aggregation Layer

### RegionReport (dataclass)

```python
@dataclass(frozen=True)
class RegionReport:
    region_id: int
    region_name_de: str
    data_timestamp: datetime
    source: Literal["api", "fixture"]

    # Core indicators
    cdi: int                    # 0–5
    spi_3m: float
    soil_moisture_pct: float    # % UFC
    vhi: float

    # Derived
    cdi_trend: int              # delta vs prior week (-1, 0, +1)
    spi_3m_delta: float         # delta vs prior week
    vhi_delta: float
    pct_critical: float         # fraction of last 52 weeks with CDI ≥ 3
    spi_3m_percentile: int      # vs 1961–2020 reference

    # Quality
    quality: QualityReport
```

### regional.py

`compute_region_report(region_id: int, bundle: DataBundle) -> RegionReport`

1. Filter `current_df` to `drought_region_id == region_id`, take the most recent row.
2. Filter `historic_df` to same region, sort by `measured_at`, take last 52 rows for trend/pct_critical.
3. Look up reference percentile for `spi_3m` from `reference_df`.
4. Compute `cdi_trend` as sign of `cdi[now] - cdi[prior_week]`.
5. Compute `pct_critical` as `count(cdi ≥ 3) / 52`.
6. Run `quality/checks.py` and attach `QualityReport`.

### indicators.py

Helper functions called by `regional.py`:
- `compute_pct_critical(historic_df, region_id, n_weeks=52) -> float`
- `compute_percentile(value, reference_series) -> int`
- `compute_trend(current, prior) -> int` — returns -1, 0, or +1

---

## Briefing Layer

### Output Modes

| Mode | Key | Audience | Tone |
|------|-----|----------|------|
| Behördenbriefing | `behoerden` | Swiss authorities | Terse, standardised, no alarmism |
| Mein Trockenheitsbulletin | `bulletin` | Public / media | Accessible, plain-language |

Both modes are fully implemented with distinct text blocks.

### text_blocks.py

A nested dict `TEXT_BLOCKS[section][mode][cdi_level]` holding German string templates with slots: `{region}`, `{cdi}`, `{spi_3m}`, `{soil_moisture_pct}`, `{vhi}`, `{pct_critical_pct}`, `{spi_3m_percentile}`, `{data_timestamp}`.

CDI levels and labels:
- 0: Keine Trockenheit
- 1: Leichte Trockenheit
- 2: Mässige Trockenheit
- 3: Schwere Trockenheit
- 4: Extreme Trockenheit
- 5: Ausserordentliche Trockenheit

Text is filled strictly from `RegionReport` values. No conditional logic outside the CDI-level lookup. No invented facts.

### template.py

`build_briefing(report: RegionReport, mode: str) -> BriefingDocument`

Assembles four sections:
1. **Lage** — current CDI level + primary indicator values
2. **Entwicklung** — week-over-week trend narrative
3. **Einordnung** — pct_critical + percentile context vs reference period
4. **Datengrundlage** — source name, data timestamp, coverage, quality flags

Returns a `BriefingDocument`:

```python
@dataclass(frozen=True)
class BriefingDocument:
    sections: dict[str, str]   # keys: "lage", "entwicklung", "einordnung", "datengrundlage"
    report: RegionReport
    mode: str                  # "behoerden" | "bulletin"
    generated_at: datetime
```

---

## Visualisation Layer

### maps.py

`build_map(report: RegionReport, all_berne_reports: list[RegionReport]) -> folium.Map`

Renders a Folium choropleth of the 7 Berne Warnregionen coloured by CDI level (0=green → 5=dark red). Uses GeoJSON boundaries fetched from `geo.admin.ch` WMS or a bundled GeoJSON fixture. The selected region is highlighted with a bold border. Returns a `folium.Map` rendered via `streamlit_folium.st_folium`.

### charts.py

`build_timeseries(historic_df: pd.DataFrame, region_id: int) -> plotly.graph_objects.Figure`

52-week dual-axis Plotly line chart: CDI (bar, left axis) + SPI-3m (line, right axis). Threshold lines at CDI=2 and SPI=-0.84 (moderate drought). Returns a `go.Figure` rendered via `st.plotly_chart`.

---

## Quality Layer

### QualityReport (dataclass)

```python
@dataclass(frozen=True)
class QualityReport:
    data_age_days: int
    coverage_pct: float          # 0–1, fraction of expected columns present
    missing_columns: list[str]
    outlier_flags: list[str]     # column names with values outside 3×IQR
    is_stale: bool               # True if data_age_days > 14
    overall: Literal["ok", "warning", "error"]
```

### checks.py

`run_quality_checks(row: pd.Series, data_timestamp: datetime, reference_df: pd.DataFrame) -> QualityReport`

- **Recency:** `data_age_days = (today - data_timestamp).days`; `is_stale = data_age_days > 14`
- **Coverage:** count non-null indicator columns / expected columns
- **Outliers:** for each indicator, check if value falls outside `[Q1 - 3×IQR, Q3 + 3×IQR]` of the reference distribution
- **Overall:** `"error"` if coverage < 0.5 or is_stale; `"warning"` if any outlier or missing column; else `"ok"`

---

## UI Layer (app.py)

Layout (top to bottom):

1. **Sidebar** — mode toggle (`st.radio`), sub-region dropdown (`st.selectbox` over 7 Berne regions), Datenstand display, PDF + HTML download buttons.
2. **Header row** — region name + Datenstand + CDI badge (coloured by level).
3. **Indicator row** — 4 `st.metric` cards: SPI-3m (+ delta), Bodenfeuchte (+ percentile), VHI (+ delta), % kritische Wochen.
4. **Map + chart row** — `st_folium` map (left) + `st.plotly_chart` time-series (right) in `st.columns(2)`.
5. **Text sections** — Lage, Entwicklung, Einordnung in `st.expander` or flat `st.markdown` blocks.
6. **Quality panel** — `st.expander("Qualität & Datengrundlage")` with coverage, recency, outlier flags, source attribution.

`@st.cache_data` wraps `load_data()` (DataBundle) and `compute_region_report()` (RegionReport). The mode toggle and region selector are sidebar widgets; changing either re-runs only the briefing/text/UI layers (not the data fetch).

---

## Export Layer

### report.py

`to_html(doc: BriefingDocument, report: RegionReport) -> str`  
Renders a self-contained HTML string with all CSS inlined. Includes: all four text sections, indicator table, map as a static choropleth PNG (rendered via `matplotlib` + `geopandas.GeoDataFrame.plot()` — folium is interactive-only and cannot produce PNG directly), time-series as embedded Plotly PNG (via `plotly.io.to_image()`), quality panel. No external URLs.

`to_pdf(html_str: str) -> bytes`  
Passes the HTML string to `weasyprint.HTML(string=html_str).write_pdf()`. Returns PDF bytes. Called lazily — only when user clicks the download button.

Both functions are pure (no Streamlit) and testable.

---

## Testing

### test_aggregation.py

- Load `DataBundle` from fixture ZIPs.
- Call `compute_region_report(34, bundle)` (Berner Mittelland).
- Assert: `report.cdi` in range 0–5, `report.spi_3m` is not NaN, `report.pct_critical` in [0.0, 1.0], `report.region_name_de == "Berner Mittelland"`.

### test_quality.py

- Inject a synthetic row with one missing column → assert `missing_columns` non-empty and `overall != "ok"`.
- Inject a row with a value 10× the reference max → assert outlier flag fires.
- Inject a `data_timestamp` 30 days old → assert `is_stale == True` and `overall == "error"`.

### test_text_blocks.py

- For each CDI level (0–5) × mode (`behoerden`, `bulletin`) × section (Lage, Entwicklung, Einordnung):
  - Render the template with a synthetic `RegionReport`.
  - Assert no `{` or `}` remain in the rendered string (no unfilled slots).
  - Assert length > 0.

Run with: `pytest tests/ -v`

---

## Technical Stack

| Concern | Library |
|---------|---------|
| UI | Streamlit ≥ 1.57 |
| Data | pandas, dataclasses |
| Geo boundaries | geopandas, shapely |
| Maps | folium, streamlit-folium |
| Charts | plotly |
| HTTP | requests |
| STAC | pystac-client |
| PDF | weasyprint |
| Python | ≥ 3.12 (uv) |

---

## Constraints

- **Rule-based text only** — no LLM, no inference. All text derived strictly from computed values.
- **Every indicator shows source + Datenstand** — no statement without attribution.
- **Open data only** — no personal or confidential data.
- **Offline capable** — fixture fallback means the app runs at the hackathon without internet.
- **No external URLs in exports** — HTML/PDF must be self-contained for government infra.
- **FR/IT translation** — stub interface only (`translate(text, lang)` → returns German unchanged for now).

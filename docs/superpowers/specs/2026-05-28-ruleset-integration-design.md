# Ruleset integration & canton restructure — design

**Date:** 2026-05-28
**Status:** Draft — pending user review
**Scope:** Single implementation plan (one feature branch)

## Context

The repository has two parallel paths for producing the drought briefing:

1. **Production codepath** (on `main`) — Streamlit app, per-warning-region, two tonal modes (`behoerden` / `bulletin`), text blocks hard-coded in `src/briefing/text_blocks.py`, trend computed as current vs. prior week. Bern-only.
2. **Ruleset YAML** (`data/ruleset/example-report.yaml`, merged in PR #1) — declarative, BAFU/MeteoSchweiz terminology, single narrative style, trend computed as forecast vs. current, live BAFU Warnkarte API as the source of truth for the warning level.

The YAML was developed standalone. It is not wired into the app. Today the production code hard-codes content that the YAML now declares (terminology, recommendations, trend phrasing). Two parallel implementations is the worst possible state.

A separately-tracked TODO calls for restructuring the report to be **per canton** instead of per warning region: aggregated lead + two maps (current CDI / forecast CDI week 2), action recommendations for the max warning level across the canton's warning regions, and a new "Allgemeine Lage nach Regionen" section at the bottom containing the existing per-region narrative.

This spec covers both: integrating the YAML *and* restructuring to per-canton in one implementation pass.

## Goals

1. **Single source of truth** for report content: the YAML ruleset.
2. **Per-canton report scope** with aggregated lead, two maps, max-warnlevel-based recommendations, and a per-region breakdown section.
3. **Live BAFU Warnkarte API** as authoritative source for the warning level, with offline fixture fallback.
4. **Bern as launch canton**, architecture canton-agnostic so further cantons can be added without code changes (only data: canton→regions mapping).
5. **Single narrative style** (bulletin / BAFU-MeteoSchweiz terminology). The `behoerden` mode is removed.

## Decisions

These were taken during brainstorming and are foundational to the design:

| # | Decision | Rationale |
|---|---|---|
| 1 | Integration *and* canton restructure in one pass | YAML and existing code conflict structurally; refactoring twice (per-region first, then canton) is wasted effort. |
| 2 | Only bulletin mode is kept | YAML is single-style by design; behoerden mode is a key-value telegram, not a narrative — better served by a future data sheet. |
| 3 | Bern launches, architecture canton-agnostic | Data dependency (canton→regions mapping) only exists for Bern; full Swiss coverage is a separate data-gathering effort. |
| 4 | Live API with cache and fixture fallback | Production-grade resilience without making the app fragile against network outages. |
| 5 | Big-bang refactor (no feature flag) | Architectural conflicts are too fundamental for graceful coexistence; feature flags would invite indefinite legacy maintenance. |

## Architecture overview

New pipeline shape (preserves the existing pipeline-first principle):

```
DataBundle ──┐
             ├─► CantonReport ──► BriefingDocument ──► UI / Export
WarnkarteData ┘     │
                    └── contains N RegionReports + canton aggregates
                        (max_warnlevel, region counts by index level, etc.)
```

### Status of existing components

| Existing | Status | Replacement / change |
|---|---|---|
| `DataBundle` | unchanged | — |
| `RegionReport` | retained, extended | New fields for the per-region section: `precip_sum_1m`, `precip_sum_3m`, `precip_1m_index`, `soil_moisture_index`, `warnlevel`, `warnlevel_info_de`, `cdi_forecast_week2` |
| `BriefingDocument` | retained, extended | `sections: dict[str, str]` keys become `lead`, `allgemeine_lage`, `handlungsoptionen`, `regionen`, `datenquellen` (Markdown). New attribute `lead_maps: list[MapSpec]` holds the structured map specs from the YAML lead block — kept separate from `sections` so the Markdown dict stays a flat string-to-string mapping. |
| `text_blocks.py` | **deleted** | YAML ruleset + Jinja2 renderer |
| `template.py::build_briefing()` | **rewritten** | Loads ruleset, builds `CantonReport`, renders Jinja2 templates from YAML |
| `_TREND_LABELS` (in `template.py`) | **deleted** | Trend term comes from `trend.defizit` in the YAML |
| Sidebar mode radio | **removed** | Single narrative style |
| Sidebar region selector | becomes **canton selector** | Bern initially, canton-agnostic |

### New components

- `src/data/warnkarte_client.py` — HTTP adapter for the BAFU Warnkarte. `@st.cache_data(ttl=3600)` on the fetch function. On error, loads `data/warnkarte_fixture.json` (the last successful response with timestamp).
- `src/aggregation/canton.py` — `compute_canton_report(canton_id, bundle, warnkarte_data) -> CantonReport`.
- `src/briefing/renderer.py` — YAML loader + Jinja2 environment with custom filters (`format_date`) and globals (`trend`, `nomenclature`). Exposes `load_ruleset(path)` and `render_briefing(canton_report, ruleset, locale="de")`.
- `src/briefing/schemas.py` — Pydantic models validating the YAML shape (`extra="forbid"`, `StrictUndefined`-friendly).
- `src/models.py` — extended with `CantonReport`, `WarnkarteEntry`, `MapSpec`.

### Engine choice: Jinja2

The YAML was authored in Handlebars-style syntax (`{{#each X}} … {{/each}}`, `{{ this.field }}`). Jinja2 is the de-facto Python templating engine, supports the same primitives (`{% for item in X %} … {% endfor %}`), and exposes custom filters/globals cleanly. A 15-line preprocessor in `load_ruleset()` rewrites the Handlebars constructs to Jinja2 before compiling — the YAML stays Handlebars-style for the author.

## YAML schema evolution

The current `data/ruleset/example-report.yaml` is per-region. It is renamed to `data/ruleset/canton-bulletin.yaml` and restructured for canton scope.

### Unchanged blocks

- `data_sources` (warnkarte, trockenheitsdaten_numerisch)
- `references`
- `nomenclature` (cdi, niederschlag, hydro, bodenfeuchte)
- `trend.defizit`
- `handlungsempfehlungen` (levels 1–5 with fallback)

### Changed: `lead.warnstufe`

- Headline template references `canton.max_warnlevel` and `canton.max_warnlevel_info_de` (was `warnkarte.warnlevel` per region).
- New sub-block `maps:` declares the two maps rendered next to the lead:

  ```yaml
  lead:
    warnstufe:
      headline: …
      meta: …
      farben_pro_stufe: …
      maps:
        - id: cdi_current
          title: { de: "Aktueller CDI" }
          source: canton.regions[*].cdi
          style: choropleth_warnregionen
        - id: cdi_forecast_week2
          title: { de: "CDI-Prognose Woche 2" }
          source: canton.regions[*].cdi_forecast_week2
          style: choropleth_warnregionen
  ```

  Maps are declarative specs in the YAML. The renderer materialises them as `MapSpec` objects; Streamlit and the HTML exporter render them.

### Changed: `sections`

| ID | Content | Data source |
|---|---|---|
| `allgemeine-lage` | Canton-level aggregate narrative ("Im Kanton Bern weisen 4 von 6 Warnregionen ein leichtes Niederschlagsdefizit auf …") | `canton.*` aggregates |
| `handlungsoptionen` | Bullet list based on `canton.max_warnlevel` | `handlungsempfehlungen.by_gefahrenstufe[canton.max_warnlevel]` |
| `regionen` (new) | Iterates over `canton.regions` and renders the existing per-region "Allgemeine Lage" text as a sub-section | per region: `region.*`, `weekly_current_regions.*`, `weekly_forecast_regions.*` |
| `datenquellen` | Auto-generated from `data_sources` + `references` (unchanged) | the YAML itself |

### New: top-level `context` block

```yaml
context:
  scope: canton                   # was implicitly per region
  required_inputs:
    canton_id: "BFS canton ID (e.g. 2 for Bern)"
```

## Data flow

```
1. User selects canton_id = 2 (Bern) in the sidebar
   ↓
2. CANTON_TO_REGIONS[2] = {33, 34, 35, 37, 38, 41}
   ↓
3. bundle = load_data()                                # existing, cached @1h
   ↓
4. warnkarte_data = warnkarte_client.fetch_for_regions([33,34,...])
   ↑ HTTP per region, @st.cache_data(ttl=3600), fallback to data/warnkarte_fixture.json
   ↓
5. region_reports = [compute_region_report(rid, bundle, warnkarte_data[rid])
                     for rid in CANTON_TO_REGIONS[2]]
   ↑ RegionReport gains: warnlevel, warnlevel_info_de, precip_sum_1m,
     precip_sum_3m, precip_1m_index, soil_moisture_index, cdi_forecast_week2
   ↓
6. canton_report = compute_canton_report(canton_id=2, region_reports)
   ↑ CantonReport contains:
     - canton_name_de, regions, max_warnlevel, max_warnlevel_info_de
     - n_regions_by_precip_index, n_regions_by_soil_moisture_index, n_regions_by_hydro_index
     - data_timestamp, source, quality (aggregated)
   ↓
7. ruleset = load_ruleset("data/ruleset/canton-bulletin.yaml")  # session-cached
   ↓
8. doc = render_briefing(canton_report, ruleset, locale="de")
   ↑ Jinja2 env with:
       env.filters["format_date"] = format_date
       env.globals["trend"] = trend_for_indicator
       env.globals["nomenclature"] = ruleset.nomenclature
     Sections rendered in declared YAML order. MapSpecs attached to doc.lead_maps.
   ↓
9. app.py renders:
     - lead box + two maps (build_canton_map(canton_report, map_spec) for map_spec in doc.lead_maps)
     - doc.sections["allgemeine_lage"] (Markdown)
     - doc.sections["handlungsoptionen"] (Markdown bullets)
     - doc.sections["regionen"] (per-region sub-sections)
     - doc.sections["datenquellen"]
     - quality expander (canton-aggregated)
     - export button → to_html(doc, canton_report)
```

### Cache strategy

| Layer | TTL | Notes |
|---|---|---|
| `load_data()` | 1 h | unchanged |
| `warnkarte_client.fetch_for_regions()` | 1 h | small payload, network call |
| `load_ruleset()` | session | YAML changes only on deploy |

## Error handling

### Recoverable degradation (report renders, user is informed)

| Scenario | Behaviour |
|---|---|
| BAFU Warnkarte unreachable / 5xx / timeout | `WarnkarteClient` loads `data/warnkarte_fixture.json`. UI shows a 🟡 banner: "Warnstufen offline geladen, letzter Stand: DD.MM.YYYY". |
| Forecast week 2 not in the dataset | `cdi_forecast_week2 = None` for affected regions. Map shows them in grey with a tooltip; the `allgemeine-lage` wording omits the forecast sentence conditionally. |
| A region has no current CSV row | Region marked `has_data = False`. Skipped in the `regionen` section with a short "Keine Daten verfügbar". Canton aggregates ignore the region. |
| VHI = NaN (legitimate, e.g. region 37) | Display "–" instead of a number. Aggregates ignore NaN. |

### Fail fast (report does not render)

| Scenario | Behaviour |
|---|---|
| `DataBundle` cannot load | `st.error("Datengrundlage nicht verfügbar: …")`. No sections rendered. |
| Canton ID not in `CANTON_TO_REGIONS` | `st.error("Kanton X nicht unterstützt. Aktuell verfügbar: Bern.")`. |
| YAML parse error or schema mismatch | `st.error("Ruleset konnte nicht geladen werden: …")`. Pydantic-validated at load time. |
| Jinja2 `UndefinedError` | App crashes loudly with stack trace — this is a developer bug, not a runtime edge case. |

### Canton-level quality aggregation

`CantonReport.quality` is folded from per-region `QualityReport`s:

- `data_age_days = max` across regions
- `coverage_pct = mean` coverage
- `overall = worst` (any "error" → canton "error")
- `outlier_flags = union` with region prefix ("R34: SPI-3m outlier")

Surfaced in the existing quality expander, with a per-region drill-down.

### Explicitly not in scope

- No retries on API failure — the fixture fallback is faster than three timeouts.
- No partial rendering on `DataBundle` failure — confuses more than it helps.
- No external telemetry — the Streamlit logger is sufficient.

## Ruleset loader and renderer

### Module shape

```python
# src/briefing/renderer.py

class RulesetSchema(BaseModel):
    id: str
    title: str
    context: ContextSpec
    data_sources: dict[str, DataSourceSpec]
    references: dict[str, ReferenceSpec]
    nomenclature: NomenclatureSpec
    trend: dict[str, TrendSpec]
    handlungsempfehlungen: HandlungsempfehlungenSpec
    lead: LeadSpec
    sections: list[SectionSpec]
    model_config = ConfigDict(extra="forbid")

def load_ruleset(path: Path) -> RulesetSchema:
    """Load YAML, validate via Pydantic, return schema object."""

def render_briefing(
    canton_report: CantonReport,
    ruleset: RulesetSchema,
    locale: Literal["de", "fr", "it"] = "de",
) -> BriefingDocument:
    """Set up Jinja2 environment, render sections in YAML order."""
```

### Jinja2 setup (once per render)

```python
env = Environment(
    loader=BaseLoader(),          # templates come from YAML strings, not disk
    undefined=StrictUndefined,    # missing keys → loud errors
    autoescape=False,             # output is Markdown, not HTML
)
env.filters["format_date"] = _format_date
env.globals["trend"] = _make_trend_resolver(ruleset.trend, locale)
env.globals["nomenclature"] = ruleset.nomenclature
```

### Handlebars → Jinja2 adapter

The YAML uses Handlebars-style iteration. `load_ruleset()` rewrites two constructs:

- `{{#each X}} … {{/each}}` → `{% for item in X %} … {% endfor %}`
- `{{ this.field }}` → `{{ item.field }}`

A single regex pass, ~15 lines. Function calls (`{{ trend(...) }}`, `{{ format_date(...) }}`) are already valid Jinja2 syntax — no rewriting needed.

### File layout (final)

```
src/
  briefing/
    __init__.py
    renderer.py            ← NEW (replaces template.py)
    schemas.py             ← NEW (Pydantic models)
  data/
    stac_client.py         (unchanged, still a stub)
    fixture_loader.py      (unchanged)
    warnkarte_client.py    ← NEW (HTTP + fixture fallback)
  aggregation/
    regional.py            (RegionReport gains new fields)
    canton.py              ← NEW (compute_canton_report)
    indicators.py          (unchanged)
  models.py                (+ CantonReport, WarnkarteEntry, MapSpec)
data/
  ruleset/
    canton-bulletin.yaml   ← renamed from example-report.yaml
  warnkarte_fixture.json   ← NEW (seeded with current live response)
```

### Testing strategy

| Test file | Status | Coverage |
|---|---|---|
| `tests/test_renderer.py` | NEW | Snapshot test of rendered sections for a fixed `CantonReport`; edge cases (missing forecast, max_warnlevel = 1 vs. 4, etc.) |
| `tests/test_warnkarte_client.py` | NEW | Mocked HTTP responses + fixture-fallback path |
| `tests/test_canton.py` | NEW | `compute_canton_report` with region aggregates |
| `tests/test_text_blocks.py` | DELETED | Module gone |
| `tests/test_export.py` | ADAPTED | Now operates on `CantonReport` |
| `tests/test_aggregation.py` | EXTENDED | New `RegionReport` fields |
| `tests/test_quality.py` | EXTENDED | Canton-level quality folding |
| `tests/test_fixture_loader.py` | unchanged | — |

Pydantic schema validation is implicit in `load_ruleset` — no separate schema test required.

## Migration plan

Each step is a commit, lands independently, keeps the UI green except where called out:

1. **Foundation** — add `WarnkarteEntry`, `CantonReport`, `MapSpec` to `src/models.py`; extend `RegionReport`. Dataclass-construction tests.
2. **WarnkarteClient** — `src/data/warnkarte_client.py` + initial `data/warnkarte_fixture.json` (one-shot seeded from the live API). Tests with the `responses` library.
3. **Canton aggregation** — `src/aggregation/canton.py::compute_canton_report()` + extension of `regional.py`. Add to `config/settings.py`:

   ```python
   CANTON_TO_REGIONS: Final[dict[int, frozenset[int]]] = {
       2: frozenset({33, 34, 35, 37, 38, 41}),   # Bern (BFS canton ID 2)
   }
   CANTON_NAMES: Final[dict[int, str]] = {2: "Bern"}
   ```

   `BERNE_REGION_IDS` stays for backwards compatibility until step 9.
4. **YAML restructure** — rename to `data/ruleset/canton-bulletin.yaml`. Lead block switches to `canton.max_warnlevel`, `maps:` sub-block added, `sections` reordered (`allgemeine-lage` as aggregate, `regionen` as iteration). Done first so the schema in step 5 targets the final shape directly.
5. **Ruleset schema + loader** — Pydantic models in `src/briefing/schemas.py`, `load_ruleset()` in `renderer.py`. Validates the canton-bulletin.yaml shape (now on disk from step 4).
6. **Renderer** — `render_briefing()` with Jinja2, Handlebars adapter, custom filters and globals. Snapshot test against a fixed `CantonReport`.
7. **Maps** — `src/viz/maps.py::build_canton_map(canton_report, map_spec: MapSpec)` for both new maps, reusing the existing geopandas/folium code.
8. **`app.py` rewire** — sidebar mode-radio removed, region selector becomes canton selector. Pipeline: `compute_region_report` → `compute_canton_report`. Sections loop uses new keys. Quality panel uses canton aggregation. **This is the cut-over commit — first commit where the user sees the new UI.**
9. **Cleanup** — delete `text_blocks.py`, `template.py`, `tests/test_text_blocks.py`, `_TREND_LABELS`, `BERNE_REGION_IDS`.

### Validation

- Visual A/B: screenshot of region 34 (old) vs. canton Bern (new). Plausibility-check the `allgemeine-lage` aggregates against the per-region texts.
- `pytest tests/ -v` must pass fully.
- Manual: trigger a BAFU Warnkarte live call (clear cache, fetch region 34), then disable network and verify the fixture fallback.
- Open the exported HTML in a browser and verify CDI maps and texts.

## Out of scope

- Swisseo VHI dataset integration (separate TODO `add-swisseo-vhi-dataset-to-ruleset`).
- FR/IT content fully written out (schema supports it, content follows separately).
- Cantons beyond Bern (architecture is canton-agnostic; data mapping is the blocker).
- Quality-panel UI redesign (only the aggregation is rewired).

## Open questions

These should be answered before implementation starts but are not blocking for the spec sign-off:

1. **"CDI forecast Woche 2" semantics** — does this mean the second week ahead (valid_at = today + 14 d) or the 2nd entry of the forecast time series? The spec assumes the former (today + 14 d).
2. **Canton BFS ID for Bern** — the spec assumes BFS canton ID 2. To be verified against the official Swiss canton coding.
3. **Map projection / styling for `choropleth_warnregionen`** — the existing `build_map` in `src/viz/maps.py` already produces a folium map; reuse and adapt, or build a fresh one. To be decided during step 7.
4. **`warnkarte_fixture.json` refresh policy** — the fixture is seeded once and never updated by the app. Should there be a `scripts/refresh_warnkarte_fixture.py` for periodic regeneration? Probably yes, but not blocking.

## Risks

- **Jinja2 / Handlebars mismatch surprises** — edge cases beyond `{{#each}}` and `{{ this.x }}` may surface. Mitigation: the YAML is small; the snapshot tests catch divergence early.
- **Per-canton max_warnlevel may surprise stakeholders** — a single small region driving a "Stufe 4" headline for the whole canton may be misleading. Mitigation flagged as an open question to validate with the user post-launch; alternative (modal level, area-weighted) is a one-line change in `compute_canton_report`.
- **BAFU Warnkarte API breaking changes** — field renames in `feature.attributes`. Mitigation: Pydantic validates the response shape; failure cleanly degrades to fixture.

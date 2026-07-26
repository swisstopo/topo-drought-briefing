# Ruleset

Rule-based templates for drought bulletins, one YAML file per report layout. Each YAML defines:

- which data sources to pull from (BAFU APIs and CSV collections),
- which terminology to use per index level (BAFU/MeteoSchweiz nomenclature),
- the trend logic (forecast vs. current value),
- the action recommendations per warning level,
- and the section layout of the report itself.

## Layout

A report YAML uses the following top-level blocks:

| Block | Purpose |
|---|---|
| `nomenclature` | Lookup tables: index level (1–5) → text snippet per language |
| `trend` | Reusable trend logic (forecast vs. current) |
| `handlungsempfehlungen` | Recommendation texts per BAFU warning level (Gefahrenstufe) |
| `lead` | Headline block (warning-level box) rendered directly below the report title |
| `sections` | Content sections with templates and placeholders |

The YAML previously also carried `id`/`title`/`description`/`context` metadata and
`data_sources`/`references` blocks for the source list. All were unused by any renderer
or template (verified by grep) and have been removed. The site's actual "Datenquellen"
card is built from **`config/sources.yaml`**, not from this file.

## Data flow

```
                 BAFU warning-map API (warnlevel, info_de, valid_from)
                          │
                          ▼
                       lead.warnstufe ────────────────► headline box in the report
                          │
                          ▼
             handlungsempfehlungen[warnlevel] ─────────► section "Handlungsoptionen"

  BAFU drought data (STAC collection)
   ├── weekly_current_regions ──┐
   ├── weekly_forecast_regions ─┤
   ├── weekly_current_stations ─┤───► placeholders in sections (resolved per region id)
   ├── daily_reference_stations ┤
   ├── regions (master data) ───┤
   └── stations (master data) ──┘
```

## Nomenclature

Follows the BAFU/MeteoSchweiz recommendation ([U8YQGX7S.pdf](https://s3.govtech.digisus-lab.ch/govtech/uploads/14/L2SYQ/U8YQGX7S.pdf), see the header comment in `canton-bulletin.yaml`). Key rule:

> The terms "Trockenheit" and "trocken" are reserved for the **lead block** and the **CDI description**. For the contributing factors (precipitation, surface/ground water, soil moisture), use **deficit terminology** instead.

Each indicator actually referenced by a section template (`cdi`, `niederschlag`, `bodenfeuchte`, `vhi`) has a lookup with 5 levels × up to 3 languages, available in adjective and/or noun form. (A `hydro` nomenclature table existed here previously but was never read by any template — the discharge/"Abfluss" narrative in the sections is hand-written prose, not nomenclature-driven — so it was removed.)

**Style convention:** For the deficit nouns (`niederschlag.noun`, `bodenfeuchte.noun`), the indefinite article "ein" is baked into the text for levels 2–5 (e.g. "ein leichtes Niederschlagsdefizit"). Level 1 uses "kein oder geringes …" (no article needed). `cdi.adjective` does **not** embed an article — it picks one up from the surrounding sentence (`cdi.noun` existed for the same purpose but was unused and has been removed).

## Trend logic

```yaml
trend.defizit:
  rule: "delta = forecast - current"
  stable_tolerance: 0
  increase / decrease / stable  # pure infinitives, per language
```

Use in templates:

```
… wird in der kommenden Woche voraussichtlich {{ trend(forecast - current, "defizit").de }}.
```

The trend terms are pure infinitives (`zunehmen`, `abnehmen`, `unverändert bleiben`), so all three variants fit the same sentence slot — grammatically correct regardless of the sign.

## Placeholder syntax

| Expression | Example |
|---|---|
| `{{ dataset.column }}` | `{{ weekly_current_regions.precip_sum_1m }}` |
| `{{ resolved.field }}` | `{{ region.name_de }}` (resolved via the `join` in `placeholders`) |
| `{{ nomenclature.<key>.<form>[<value>].<lang> }}` | `{{ nomenclature.niederschlag.noun[weekly_current_regions.precip_1m_index].de }}` |
| `{{ trend(<expr>, "<key>").<lang> }}` | `{{ trend(forecast - current, "defizit").de }}` |
| `{{ format_date(<iso_date>, "<pattern>") }}` | `{{ format_date(warnkarte.valid_from, 'DD.MM.YYYY') }}` |
| `{{#each <collection>}} … {{ this.x }} {{/each}}` | iteration over recommendation lists or `canton.regions` |

## Sections

| Section | Content | Data basis |
|---|---|---|
| `allgemeine-lage` | Precipitation → discharge → soil moisture → vegetation. Order follows the drought cascade atmosphere → hydrosphere → pedosphere. | `weekly_current_regions`, `weekly_forecast_regions`, station aggregates |
| `regionen` | Per-region breakdown of the same indicators | `canton.regions[*]` |
| `handlungsoptionen` | Bullet list of BAFU recommendations for the current warning level | `warnkarte.warnlevel` → `handlungsempfehlungen` |

The site's "Datenquellen" (source list) card is not a ruleset section at all — it is built
directly from `config/sources.yaml` by `scripts/generate_site.py`. A `datenquellen` section
used to exist here but was always excluded from the rendered HTML and has been removed.

## Station aggregates (discharge)

Discharge/low-flow station counts (`canton.discharge`, `region.discharge`) are **not**
computed from a YAML-declared `aggregate` placeholder — there is no such construct in the
current schema. They're computed directly in Python: `src/aggregation/stations.py` classifies
each station as low/very-low by comparing its current value against
`threshold1`/`q347` from `daily_reference_stations`, and `src/aggregation/regional.py`
joins stations to regions via `data/station_region_mapping.json` (produced by
`scripts/extract_station_mappings.py` — see `data/README.md`). The resulting counts are then
available to the `allgemeine-lage`/`regionen` templates as `canton.discharge`/`this.discharge`.

## Action recommendations — fallback

BAFU only publishes explicit recommendations for levels 1, 2 and 4. Levels 3 and 5 fall back via `fallback: 2` and `fallback: 4` to the next lower level. The renderer is expected to resolve the fallback itself.

## Rendering a report

This describes the actual daily batch pipeline (not a per-request API call):

1. **Aggregate:** `scripts/aggregate.py` computes a `CantonReport`/`RegionReport` per canton/region from the raw BAFU datasets (see `ARCHITECTURE.md`) and writes `data/processed/`.
2. **Render:** `src/briefing/renderer.py`'s `render_briefing()` loads this YAML via `load_ruleset()`, then renders each `sections[].template` (Handlebars-style syntax pre-processed to Jinja2) against one `CantonReport`, per locale.
3. **Generate site:** `scripts/generate_site.py` calls `render_briefing()` for `de`/`fr`, embeds both language versions in one static HTML page per canton, and writes `site/`.

## Open points

- **API failure handling:** on network/HTTP failure, data clients (`src/data/vhi_client.py`, `src/data/warnkarte_client.py`) fall back to bundled fixture data (`data/fixtures/`, see `data/README.md`) rather than failing the pipeline.
- **FR/IT completeness:** section templates (`sections[].template`) are currently only fleshed out in `de` — no French or Italian prose exists for section bodies yet. Nomenclature entries actually in use (`cdi.adjective`, `niederschlag`, `bodenfeuchte.noun`, `vhi.noun`) do include `it`; the `lead` block (`headline`/`meta`) does not yet have Italian text. See `ARCHITECTURE.md` § Internationalization for a proposed consolidation of this file's per-language nesting.

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
| `id`, `title`, `description` | Metadata |
| `data_sources` | External data providers (REST API, STAC collection) with URL + field mapping |
| `references` | External documents (terminology PDF, recommendations web page) for the source list |
| `nomenclature` | Lookup tables: index level (1–5) → text snippet per language |
| `trend` | Reusable trend logic (forecast vs. current) |
| `handlungsempfehlungen` | Recommendation texts per BAFU warning level (Gefahrenstufe) |
| `lead` | Headline block (warning-level box) rendered directly below the report title |
| `sections` | Content sections with templates and placeholders |

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

Follows the BAFU/MeteoSchweiz recommendation (see `references.terminologie_bafu`). Key rule:

> The terms "Trockenheit" and "trocken" are reserved for the **lead block** and the **CDI description**. For the contributing factors (precipitation, surface/ground water, soil moisture), use **deficit terminology** instead.

Each indicator (`cdi`, `niederschlag`, `hydro`, `bodenfeuchte`) has a lookup with 5 levels × 3 languages, available in adjective and/or noun form.

**Style convention:** For the deficit nouns (`niederschlag.noun`, `hydro.noun`, `bodenfeuchte.noun`), the indefinite article "ein" is baked into the text for levels 2–5 (e.g. "ein leichtes Niederschlagsdefizit"). Level 1 uses "kein oder geringes …" (no article needed). `cdi.noun` does **not** embed an article — it picks one up from the surrounding sentence.

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
| `{{#each <collection>}} … {{ this.x }} {{/each}}` | iteration over recommendation lists or data sources |

## Sections

| Section | Content | Data basis |
|---|---|---|
| `allgemeine-lage` | Precipitation → discharge → lakes → soil moisture. Order follows the drought cascade atmosphere → hydrosphere → pedosphere. | `weekly_current_regions`, `weekly_forecast_regions`, station aggregates |
| `handlungsoptionen` | Bullet list of BAFU recommendations for the current warning level | `warnkarte.warnlevel` → `handlungsempfehlungen` |
| `datenquellen` | Auto-generated list from `data_sources` + `references` | the YAML itself |

## Station aggregates (discharge, lakes)

The `abfluss` and `seen` placeholders in `allgemeine-lage` are of type `aggregate`. They filter `weekly_current_stations` by `label` (Abfluss / Wasserstand) and `unit` (`masl` for lakes), join with `daily_reference_stations` via `hydro_station_id` and `doy`, and count the stations whose current value is strictly below `threshold1` and/or `q347`.

**External dependency:** the mapping `hydro_station_id → drought_region_id` is **not** part of the BAFU dataset — the renderer must provide it externally (see the filter block `region: "{{ aktuelle_region }}"`).

## Action recommendations — fallback

BAFU only publishes explicit recommendations for levels 1, 2 and 4. Levels 3 and 5 fall back via `fallback: 2` and `fallback: 4` to the next lower level. The renderer is expected to resolve the fallback itself.

## Rendering a report

1. **Input:** `drought_region_id` (e.g. 34 for Berner Mittelland)
2. **API call:** `data_sources.warnkarte.url` with the `drought_region_id` substituted → returns `warnlevel`, `info_de`, `valid_from`
3. **CSV lookups:** latest row from `weekly_current_regions` + first forecast row from `weekly_forecast_regions` for that region
4. **Joins:** `regions` (name), `weekly_current_stations` + `daily_reference_stations` (aggregates, provided that the station mapping is available)
5. **Rendering:** lead box, then sections in declared order

## Example output

`example-region-34.html` is a rendered example report for region 34 (Berner Mittelland), data as of 28.05.2026. The aggregate blocks are marked as placeholders because the station mapping is not resolved in this example.

## Open points

- **Aggregate mapping:** the station-to-region assignment must be provided by the renderer — format and location to be defined.
- **Renderer engine:** templates mix Handlebars-style syntax (`{{#each}}`) and function calls (`format_date()`, `trend()`). Concrete engine choice (e.g. Nunjucks / Liquid + custom filters) is still open.
- **API failure handling:** what happens when the BAFU warning map is unreachable? Currently unspecified (assumption: fail fast).
- **FR/IT completeness:** section templates are currently only fleshed out in `de`. The lead block and the nomenclature are already trilingual.

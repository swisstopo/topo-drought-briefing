# Canton View Map Layout Redesign

**Date:** 2026-05-29
**Status:** Approved

## Goal

Reorganise the canton view so the map is on the right side of the screen and the general overview text is on the left. Users can switch between the current CDI map and the 2-week forecast map using tabs.

## Current State

The canton view (`view_tab == "canton"` in `app.py`) currently renders:

1. Full-width title
2. Full-width warnlevel badge
3. Two side-by-side maps (one per `MapSpec` in `doc.lead_maps`) via `st.columns(2)`
4. CDI legend (full width)
5. Divider
6. All briefing sections full-width: `allgemeine-lage`, `handlungsoptionen`, `datenquellen`

## Approved Design

### Page structure (top to bottom)

```
┌──────────────────────────────────────────────────┐
│  st.title — "Trockenheitsbriefing / <Kanton>"    │
└──────────────────────────────────────────────────┘
┌───────────────────────┬──────────────────────────┐
│  LEFT COL             │  RIGHT COL               │
│                       │                          │
│  Warnlevel badge      │  ┌─────────┬──────────┐  │
│  (existing HTML block)│  │ Aktuell │ Prognose │  │
│                       │  └─────────┴──────────┘  │
│  ## Allgemeine Lage   │  [ folium map, h=300px ]  │
│  <section text>       │                          │
└───────────────────────┴──────────────────────────┘
┌──────────────────────────────────────────────────┐
│  CDI legend strip (full width — unchanged)       │
└──────────────────────────────────────────────────┘
─────────── divider ───────────────────────────────
┌──────────────────────────────────────────────────┐
│  ## Handlungsoptionen  (full width)              │
│  ## Datenquellen       (full width)              │
└──────────────────────────────────────────────────┘
```

### Column widths

`st.columns([1, 1])` — equal split. Adjust to `[1, 1.2]` if the map needs slightly more room.

### Tab switcher

`st.tabs()` driven by `doc.lead_maps` (list of `MapSpec`). Tab labels use `map_spec.title_de` or `map_spec.title_fr` depending on the selected language. Each tab renders one folium map via `st.components.v1.html(m._repr_html_(), height=300)`.

The two map specs from the YAML ruleset are:
- `cdi_current` — "Aktueller CDI" / "CDI actuel"
- `cdi_forecast_week2` — "CDI-Prognose Woche 2" / "Prévision CDI semaine 2"

### Section placement

- `allgemeine-lage` moves into the **left column** (rendered after the warnlevel badge).
- All other sections (`handlungsoptionen`, `datenquellen`) stay **full-width below**, rendered in the existing loop (with the `regionen` skip guard).

## Changes Required

### `app.py` — canton view block only

1. **Delete** `map_cols = st.columns(2)` and the `for col, map_spec in zip(map_cols, doc.lead_maps)` loop.
2. **Add** `left_col, right_col = st.columns([1, 1])` after `st.title(...)`.
3. **Left column**: move the warnlevel badge block inside `with left_col:`, followed by the `allgemeine-lage` section.
4. **Right column**: inside `with right_col:`, build tabs from `doc.lead_maps` using `st.tabs([...])`. Render one map per tab.
5. The CDI legend, divider, and remaining sections loop are **unchanged** except that the `allgemeine-lage` section must be **skipped** in the loop (it is now rendered in the left column).

### No other files change

`maps.py`, `models.py`, `renderer.py`, and the YAML ruleset are untouched. The `MapSpec` list and `build_canton_map()` call signatures stay the same.

## Out of Scope

- Sticky map positioning (Option B) — not needed.
- Changes to the Regions view (`view_tab == "regions"`).
- Changes to the HTML export (`to_html()`).
- Any mobile/responsive breakpoints.

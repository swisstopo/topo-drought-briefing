# VHI Client — Design Spec

**Date:** 2026-05-29
**Status:** Approved

## Summary

Replace the VHI values read from the STAC fixture CSV (`row["vhi"]`) with live data from the SwissEO REST endpoint. A new `vhi_client.py` follows the same live-fetch-with-fixture-fallback pattern already used by `warnkarte_client.py`.

## Data Source

- **URL:** `https://data.geo.admin.ch/ch.swisstopo.swisseo_vhi_v100/swisseo_vhi_v100/ch.swisstopo.swisseo_vhi_v100_current_vegetation-warnregions.csv`
- **Format:** Plain CSV, no authentication required
- **Columns:** `REGION_NR`, `vhi_mean`, `availability_percentage`
- `REGION_NR` maps directly to `drought_region_id`
- `vhi_mean` is on a 0–100 scale
- `availability_percentage` is ignored (not surfaced in the pipeline)

## Files

### New files

| File | Purpose |
|---|---|
| `src/data/vhi_client.py` | SwissEO fetch + fixture fallback |
| `data/vhi_fixture.csv` | Snapshot of current SwissEO CSV for offline fallback |

### Modified files

| File | Change |
|---|---|
| `config/settings.py` | Add `VHI_URL` and `VHI_FIXTURE` constants |
| `src/aggregation/regional.py` | Accept `vhi_value: float \| None = None`; use it over `row["vhi"]`; set `vhi_delta = 0.0` |
| `src/aggregation/canton.py` | Call `vhi_client.fetch_for_regions()`, pass results into `compute_region_report()` |

## `vhi_client.py` Design

```
fetch_for_regions(region_ids: list[int]) -> dict[int, float]
```

- Single GET to `VHI_URL` with a 10-second timeout
- Parses the response text as CSV; filters to requested `REGION_NR` values
- Returns `{region_id: vhi_mean}` as floats
- On any network or HTTP error: `warnings.warn(...)` and falls back to `_load_from_fixture(region_ids)`
- Fixture fallback reads `data/vhi_fixture.csv` directly (same 3-column format)

## `regional.py` Change

`compute_region_report()` gains a new parameter:

```python
vhi_value: float | None = None
```

- If provided (not `None`), used directly as `vhi`
- Otherwise falls back to `_safe(row["vhi"])` from the STAC data (backward compat)
- `vhi_delta` is hardcoded to `0.0` — week-over-week delta is dropped because SwissEO only provides a current snapshot

## `canton.py` Change

Before the region list comprehension:

```python
vhi_data = vhi_client.fetch_for_regions(region_ids)
```

Then in the comprehension:

```python
compute_region_report(rid, bundle,
    warnkarte_entry=warnkarte_data.get(rid),
    vhi_value=vhi_data.get(rid))
```

## Decisions

- **`availability_percentage` is ignored** — not surfaced in `RegionReport`, `QualityReport`, or the bulletin. Can be added later if needed.
- **`vhi_delta = 0.0`** — dropped rather than hybrid STAC+SwissEO, to keep the source of truth for VHI single and clear.
- **Fixture format** — plain CSV matching the SwissEO response exactly; no transformation needed.

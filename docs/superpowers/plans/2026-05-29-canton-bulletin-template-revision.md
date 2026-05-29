# Canton Bulletin Template Revision — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate the revised text blocks from `data/ruleset/new_template.md` into `canton-bulletin.yaml`, backed by correct calculations (station discharge stats, canton CDI situation trend, mean precip, deficit ranges, per-region deficit trends, link blocks).

**Architecture:** Extend the typed pipeline `DataBundle → RegionReport → CantonReport → renderer`. New station data flows through `fixture_loader`; a new `src/aggregation/stations.py` computes discharge stats; new computed fields land on `RegionReport`/`CantonReport`; the renderer gains a `deficit_range` global and `{{#if}}` support; the YAML holds all text.

**Tech Stack:** Python 3, pandas, pydantic, Jinja2, pytest. Run tests with `uv run pytest`.

---

## File Structure

- `config/settings.py` — add station file-name constants (modify)
- `src/models.py` — `DischargeStats` dataclass; new `DataBundle`/`RegionReport`/`CantonReport` fields (modify)
- `src/data/fixture_loader.py` — load station CSVs + region map (modify)
- `src/aggregation/stations.py` — `compute_discharge_stats` (create)
- `src/aggregation/regional.py` — forecast-index lookups, deltas, per-region discharge (modify)
- `src/aggregation/canton.py` — canton aggregates + canton discharge (modify)
- `src/briefing/schemas.py` — nomenclature `range`/`single`, `banner`, `weiterfuehrende_links` (modify)
- `src/briefing/renderer.py` — `{{#if}}` translation, `deficit_range` global, expose banner/links (modify)
- `data/ruleset/canton-bulletin.yaml` — trend.situation, nomenclature additions, banner, links, rewritten sections (modify)
- `app.py`, `src/export/report.py` — render banner + links (modify)
- `docs/index.html` — add `stations.py` to stlite file list (modify)
- Tests: `tests/test_stations.py` (create), `tests/test_fixture_loader.py`, `tests/test_aggregation.py`, `tests/test_canton.py`, `tests/test_renderer.py` (modify)

---

## Task 1: DischargeStats model + DataBundle station fields + settings

**Files:**
- Modify: `config/settings.py`
- Modify: `src/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Add settings constants**

In `config/settings.py`, after the `REFERENCE_ZIP_NAME` block:
```python
CURRENT_STATIONS_CSV: Final[str] = "weekly_current_stations.csv"
REFERENCE_STATIONS_CSV: Final[str] = "daily_reference_stations.csv"
STATION_REGION_MAP_NAME: Final[str] = "station_region_mapping.json"
```

- [ ] **Step 2: Write failing test for DischargeStats + DataBundle defaults**

In `tests/test_models.py` add:
```python
def test_discharge_stats_dataclass():
    from src.models import DischargeStats
    s = DischargeStats(n_total=4, n_low=2, n_very_low=1, pct_low=50)
    assert s.n_total == 4 and s.n_low == 2 and s.n_very_low == 1 and s.pct_low == 50


def test_databundle_station_fields_default_empty():
    import pandas as pd
    from datetime import datetime
    from src.models import DataBundle
    b = DataBundle(
        current_df=pd.DataFrame(), historic_df=pd.DataFrame(),
        reference_df=pd.DataFrame(), data_timestamp=datetime(2026, 5, 26), source="fixture",
    )
    assert b.current_stations_df.empty
    assert b.reference_stations_df.empty
    assert b.station_region_map == {}
```

- [ ] **Step 3: Run, expect fail**

Run: `uv run pytest tests/test_models.py -k "discharge_stats or station_fields" -v`
Expected: FAIL (ImportError / AttributeError).

- [ ] **Step 4: Implement model changes**

In `src/models.py`, add to `DataBundle` (after `forecast_df`):
```python
    current_stations_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    reference_stations_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    station_region_map: dict[str, int] = field(default_factory=dict)
```
Add new dataclass after `QualityReport`:
```python
@dataclass
class DischargeStats:
    n_total: int      # discharge stations with a usable reference row
    n_low: int        # current value < threshold1
    n_very_low: int   # current value < q347 (subset of n_low)
    pct_low: int      # round(n_low / n_total * 100); 0 when n_total == 0
```

- [ ] **Step 5: Run, expect pass**

Run: `uv run pytest tests/test_models.py -k "discharge_stats or station_fields" -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add config/settings.py src/models.py tests/test_models.py
git commit -m "feat: add DischargeStats model and DataBundle station fields"
```

---

## Task 2: Load station data in fixture_loader

**Files:**
- Modify: `src/data/fixture_loader.py`
- Test: `tests/test_fixture_loader.py`

- [ ] **Step 1: Write failing test**

In `tests/test_fixture_loader.py` add:
```python
def test_load_populates_station_data():
    from src.data.fixture_loader import load
    b = load()
    assert not b.current_stations_df.empty
    assert not b.reference_stations_df.empty
    assert b.station_region_map  # non-empty dict
    # IDs are strings (leading-zero IDs like "0078" must survive)
    assert b.current_stations_df["hydro_station_id"].dtype == object
    assert all(isinstance(k, str) for k in list(b.station_region_map)[:5])
    # reference has the threshold columns
    for col in ("doy", "threshold1", "q347", "label"):
        assert col in b.reference_stations_df.columns
```

- [ ] **Step 2: Run, expect fail**

Run: `uv run pytest tests/test_fixture_loader.py -k station_data -v`
Expected: FAIL.

- [ ] **Step 3: Implement loader changes**

In `src/data/fixture_loader.py`:
- Extend the settings import to include `CURRENT_STATIONS_CSV, REFERENCE_STATIONS_CSV, STATION_REGION_MAP_NAME`.
- Add `import json`.
- Add a helper to read a station CSV forcing the id column to str:
```python
def _read_stations_csv(zip_path: Path, filename: str) -> pd.DataFrame:
    df, _ = _read_csv_from_zip(zip_path, filename)
    df["hydro_station_id"] = df["hydro_station_id"].astype(str).str.strip()
    if "measured_at" in df.columns:
        df["measured_at"] = pd.to_datetime(df["measured_at"], format="%d.%m.%Y", errors="coerce")
    return df
```
- In `load()`, before the `return`, add:
```python
    current_stations_df = _read_stations_csv(DATA_DIR / CURRENT_ZIP_NAME, CURRENT_STATIONS_CSV)
    reference_stations_df = _read_stations_csv(DATA_DIR / REFERENCE_ZIP_NAME, REFERENCE_STATIONS_CSV)
    map_path = DATA_DIR / STATION_REGION_MAP_NAME
    station_region_map: dict[str, int] = {}
    if map_path.exists():
        raw_map = json.loads(map_path.read_text(encoding="utf-8"))
        station_region_map = {str(k).strip(): int(v) for k, v in raw_map.items()}
```
- Add the three fields to the `DataBundle(...)` construction.

Note: `_read_csv_from_zip` returns numeric leading-zero ids as ints; `.astype(str)` of an int loses the leading zero. Force str on read instead — change `_read_stations_csv` to read with dtype:
```python
def _read_stations_csv(zip_path: Path, filename: str) -> pd.DataFrame:
    with zipfile.ZipFile(zip_path) as z:
        with z.open(filename) as f:
            raw = f.read().decode("utf-8", errors="replace")
    data_lines = [ln for ln in raw.splitlines() if not ln.startswith("#") and ln.strip()]
    df = pd.read_csv(io.StringIO("\n".join(data_lines)), sep=";", dtype={"hydro_station_id": str})
    df["hydro_station_id"] = df["hydro_station_id"].str.strip()
    if "measured_at" in df.columns:
        df["measured_at"] = pd.to_datetime(df["measured_at"], format="%d.%m.%Y", errors="coerce")
    return df
```

- [ ] **Step 4: Run, expect pass**

Run: `uv run pytest tests/test_fixture_loader.py -k station_data -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/data/fixture_loader.py tests/test_fixture_loader.py
git commit -m "feat: load station CSVs and station-region map into DataBundle"
```

---

## Task 3: compute_discharge_stats

**Files:**
- Create: `src/aggregation/stations.py`
- Test: `tests/test_stations.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_stations.py`:
```python
from datetime import datetime

import pandas as pd

from src.aggregation.stations import compute_discharge_stats
from src.models import DataBundle


def _bundle(current_rows, ref_rows, mapping):
    return DataBundle(
        current_df=pd.DataFrame(), historic_df=pd.DataFrame(),
        reference_df=pd.DataFrame(), data_timestamp=datetime(2026, 5, 26), source="fixture",
        current_stations_df=pd.DataFrame(current_rows),
        reference_stations_df=pd.DataFrame(ref_rows),
        station_region_map=mapping,
    )


def test_counts_low_and_very_low():
    # doy for 2025-05-26 is 146
    cur = [
        {"hydro_station_id": "0078", "measured_at": datetime(2025, 5, 26), "value": 2.0, "label": "Abfluss"},  # < q347 -> very low (and low)
        {"hydro_station_id": "2009", "measured_at": datetime(2025, 5, 26), "value": 4.0, "label": "Abfluss"},  # < threshold1, > q347 -> low only
        {"hydro_station_id": "2004", "measured_at": datetime(2025, 5, 26), "value": 9.0, "label": "Abfluss"},  # ok
        {"hydro_station_id": "2007", "measured_at": datetime(2025, 5, 26), "value": 100.0, "label": "Wasserstand"},  # ignored
    ]
    ref = [
        {"hydro_station_id": "0078", "doy": 146, "threshold1": 5.0, "q347": 3.0, "label": "Abfluss"},
        {"hydro_station_id": "2009", "doy": 146, "threshold1": 5.0, "q347": 3.0, "label": "Abfluss"},
        {"hydro_station_id": "2004", "doy": 146, "threshold1": 5.0, "q347": 3.0, "label": "Abfluss"},
    ]
    mapping = {"0078": 33, "2009": 33, "2004": 33, "2007": 33}
    stats = compute_discharge_stats([33], _bundle(cur, ref, mapping))
    assert stats.n_total == 3
    assert stats.n_low == 2
    assert stats.n_very_low == 1
    assert stats.pct_low == 67  # round(2/3*100)


def test_filters_by_region():
    cur = [
        {"hydro_station_id": "0078", "measured_at": datetime(2025, 5, 26), "value": 2.0, "label": "Abfluss"},
        {"hydro_station_id": "2009", "measured_at": datetime(2025, 5, 26), "value": 2.0, "label": "Abfluss"},
    ]
    ref = [
        {"hydro_station_id": "0078", "doy": 146, "threshold1": 5.0, "q347": 3.0, "label": "Abfluss"},
        {"hydro_station_id": "2009", "doy": 146, "threshold1": 5.0, "q347": 3.0, "label": "Abfluss"},
    ]
    mapping = {"0078": 33, "2009": 41}
    stats = compute_discharge_stats([33], _bundle(cur, ref, mapping))
    assert stats.n_total == 1


def test_zero_stations():
    stats = compute_discharge_stats([99], _bundle([], [], {}))
    assert stats.n_total == 0
    assert stats.pct_low == 0
    assert stats.n_low == 0 and stats.n_very_low == 0


def test_skips_station_without_reference_row():
    cur = [{"hydro_station_id": "0078", "measured_at": datetime(2025, 5, 26), "value": 2.0, "label": "Abfluss"}]
    ref = []  # no reference -> station not counted
    stats = compute_discharge_stats([33], _bundle(cur, ref, {"0078": 33}))
    assert stats.n_total == 0
```

- [ ] **Step 2: Run, expect fail**

Run: `uv run pytest tests/test_stations.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement**

Create `src/aggregation/stations.py`:
```python
# src/aggregation/stations.py
from __future__ import annotations

from collections.abc import Collection

import pandas as pd

from src.models import DataBundle, DischargeStats

_DISCHARGE_LABEL = "Abfluss"


def compute_discharge_stats(region_ids: Collection[int], bundle: DataBundle) -> DischargeStats:
    """Count discharge stations in the given regions with low / very low flow.

    Low      = current value < threshold1 (at the station's current day-of-year).
    Very low = current value < q347 (subset of low).
    Only stations with label == "Abfluss" and a matching reference row are counted.
    """
    region_set = set(region_ids)
    current = bundle.current_stations_df
    reference = bundle.reference_stations_df
    if current.empty or reference.empty:
        return DischargeStats(n_total=0, n_low=0, n_very_low=0, pct_low=0)

    cur = current[current["label"] == _DISCHARGE_LABEL].copy()
    cur = cur[cur["hydro_station_id"].map(bundle.station_region_map).isin(region_set)]
    if cur.empty:
        return DischargeStats(n_total=0, n_low=0, n_very_low=0, pct_low=0)

    cur["doy"] = pd.to_datetime(cur["measured_at"]).dt.dayofyear

    ref = reference[reference["label"] == _DISCHARGE_LABEL][
        ["hydro_station_id", "doy", "threshold1", "q347"]
    ]
    merged = cur.merge(ref, on=["hydro_station_id", "doy"], how="inner")
    merged = merged.dropna(subset=["threshold1", "q347", "value"])

    n_total = len(merged)
    if n_total == 0:
        return DischargeStats(n_total=0, n_low=0, n_very_low=0, pct_low=0)

    n_low = int((merged["value"] < merged["threshold1"]).sum())
    n_very_low = int((merged["value"] < merged["q347"]).sum())
    pct_low = round(n_low / n_total * 100)
    return DischargeStats(n_total=n_total, n_low=n_low, n_very_low=n_very_low, pct_low=pct_low)
```

- [ ] **Step 4: Run, expect pass**

Run: `uv run pytest tests/test_stations.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/aggregation/stations.py tests/test_stations.py
git commit -m "feat: add compute_discharge_stats for station discharge bands"
```

---

## Task 4: RegionReport forecast deltas + per-region discharge

**Files:**
- Modify: `src/models.py` (RegionReport)
- Modify: `src/aggregation/regional.py`
- Test: `tests/test_aggregation.py`

- [ ] **Step 1: Write failing test**

In `tests/test_aggregation.py` add:
```python
def test_region_report_deficit_deltas_and_discharge(bundle):
    from src.models import DischargeStats
    report = compute_region_report(34, bundle)
    assert isinstance(report.precip_deficit_delta, int)
    assert isinstance(report.soil_moisture_deficit_delta, int)
    assert isinstance(report.discharge, DischargeStats)
    assert report.discharge.n_total >= 0
```

- [ ] **Step 2: Run, expect fail**

Run: `uv run pytest tests/test_aggregation.py -k deficit_deltas -v`
Expected: FAIL (AttributeError).

- [ ] **Step 3: Add RegionReport fields**

In `src/models.py` `RegionReport`, after `cdi_forecast_week2`:
```python
    precip_1m_index_forecast: int | None = None
    soil_moisture_index_forecast: int | None = None
    precip_deficit_delta: int = 0
    soil_moisture_deficit_delta: int = 0
    discharge: "DischargeStats" = field(default_factory=lambda: DischargeStats(0, 0, 0, 0))
```
(`DischargeStats` is defined above `RegionReport` in the same module, so the forward ref resolves; the default factory references it directly.)

- [ ] **Step 4: Implement regional.py**

In `src/aggregation/regional.py`:
- Import: `from src.aggregation.stations import compute_discharge_stats`.
- Generalise the forecast helper. Replace `_compute_cdi_forecast_week2` with a generic value lookup and a thin CDI wrapper:
```python
def _forecast_week2_value(bundle: DataBundle, region_id: int, column: str) -> int | None:
    """Return the week-2 (~+14d) p50 value of `column` for a region, or None."""
    forecast = bundle.forecast_df
    if forecast.empty or column not in forecast.columns:
        return None
    target_date = bundle.data_timestamp + timedelta(days=14)
    region_forecast = forecast[forecast["drought_region_id"] == region_id]
    if region_forecast.empty:
        return None
    region_forecast = region_forecast.copy()
    region_forecast["delta"] = (region_forecast["valid_at"] - target_date).abs()
    closest = region_forecast.sort_values("delta").iloc[0]
    if closest["delta"] > pd.Timedelta(days=5):
        return None
    if pd.isna(closest.get(column)):
        return None
    return int(closest[column])


def _compute_cdi_forecast_week2(bundle: DataBundle, region_id: int) -> int | None:
    return _forecast_week2_value(bundle, region_id, "cdi_p50")
```
- Before the `return RegionReport(...)`, compute deltas + discharge:
```python
    precip_1m_index_forecast = _forecast_week2_value(bundle, region_id, "precip_1m_index_p50")
    soil_moisture_index_forecast = _forecast_week2_value(bundle, region_id, "soil_moisture_index_p50")
    precip_deficit_delta = (
        precip_1m_index_forecast - precip_1m_index if precip_1m_index_forecast is not None else 0
    )
    soil_moisture_deficit_delta = (
        soil_moisture_index_forecast - soil_moisture_index
        if soil_moisture_index_forecast is not None else 0
    )
    discharge = compute_discharge_stats([region_id], bundle)
```
- Pass the five new fields into `RegionReport(...)`.

- [ ] **Step 5: Run, expect pass**

Run: `uv run pytest tests/test_aggregation.py -k deficit_deltas -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/models.py src/aggregation/regional.py tests/test_aggregation.py
git commit -m "feat: per-region deficit forecast deltas and discharge stats"
```

---

## Task 5: CantonReport aggregates + canton discharge

**Files:**
- Modify: `src/models.py` (CantonReport)
- Modify: `src/aggregation/canton.py`
- Test: `tests/test_canton.py`

- [ ] **Step 1: Write failing test**

In `tests/test_canton.py` add (adapt import of warnkarte fixture if the file has a helper; otherwise build inline like below):
```python
def test_canton_report_new_aggregates():
    from datetime import datetime
    from src.aggregation.canton import compute_canton_report
    from src.data.stac_client import load as load_data
    from src.models import DischargeStats, WarnkarteEntry

    bundle = load_data()
    wk = {
        rid: WarnkarteEntry(rid, 2, "Mässige Gefahr", "Danger limité", "-", datetime(2026, 5, 28))
        for rid in (33, 34, 35, 37, 38, 41)
    }
    c = compute_canton_report(canton_id=2, bundle=bundle, warnkarte_data=wk)
    assert 0 <= c.n_regions_dry <= len(c.regions)
    assert c.cdi_min_dry is None or 2 <= c.cdi_min_dry <= 5
    assert c.cdi_max_dry is None or 2 <= c.cdi_max_dry <= 5
    assert isinstance(c.cdi_situation_delta, int)
    assert c.mean_precip_sum_1m >= 0.0
    assert c.mean_precip_sum_3m >= 0.0
    assert 1 <= c.precip_index_min <= 5
    assert 1 <= c.precip_index_max <= 5
    assert isinstance(c.discharge, DischargeStats)
    assert 0 <= c.n_regions_with_precip_deficit <= len(c.regions)
    assert 0 <= c.n_regions_with_soil_moisture_deficit <= len(c.regions)
```

- [ ] **Step 2: Run, expect fail**

Run: `uv run pytest tests/test_canton.py -k new_aggregates -v`
Expected: FAIL (AttributeError / TypeError).

- [ ] **Step 3: Add CantonReport fields**

In `src/models.py` `CantonReport`, after `quality`, add (with defaults so existing constructions stay valid):
```python
    n_regions_dry: int = 0
    cdi_min_dry: int | None = None
    cdi_max_dry: int | None = None
    cdi_situation_delta: int = 0
    mean_precip_sum_1m: float = 0.0
    mean_precip_sum_3m: float = 0.0
    precip_index_min: int = 1
    precip_index_max: int = 1
    n_regions_with_precip_deficit: int = 0
    n_regions_with_soil_moisture_deficit: int = 0
    discharge: "DischargeStats" = field(default_factory=lambda: DischargeStats(0, 0, 0, 0))
```

- [ ] **Step 4: Implement canton.py**

In `src/aggregation/canton.py`:
- Import: `from src.aggregation.stations import compute_discharge_stats` and `from src.models import ... DischargeStats` (extend existing import).
- After `region_reports` is built and before constructing `CantonReport`, compute:
```python
    dry = [r for r in region_reports if r.cdi > 1]
    n_regions_dry = len(dry)
    cdi_min_dry = min((r.cdi for r in dry), default=None)
    cdi_max_dry = max((r.cdi for r in dry), default=None)

    sum_current_cdi = sum(r.cdi for r in region_reports)
    sum_forecast_cdi = sum(
        r.cdi_forecast_week2 if r.cdi_forecast_week2 is not None else r.cdi
        for r in region_reports
    )
    cdi_situation_delta = sum_forecast_cdi - sum_current_cdi

    mean_precip_sum_1m = round(sum(r.precip_sum_1m for r in region_reports) / len(region_reports), 1)
    mean_precip_sum_3m = round(sum(r.precip_sum_3m for r in region_reports) / len(region_reports), 1)

    precip_indices = [r.precip_1m_index for r in region_reports]
    precip_index_min = min(precip_indices)
    precip_index_max = max(precip_indices)

    n_precip_deficit = sum(1 for r in region_reports if r.precip_1m_index >= 2)
    n_soil_deficit = sum(1 for r in region_reports if r.soil_moisture_index >= 2)

    discharge = compute_discharge_stats(region_ids, bundle)
```
- Pass all new fields into `CantonReport(...)`.

- [ ] **Step 5: Run, expect pass**

Run: `uv run pytest tests/test_canton.py -k new_aggregates -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/models.py src/aggregation/canton.py tests/test_canton.py
git commit -m "feat: canton-level CDI/precip/discharge aggregates"
```

---

## Task 6: Renderer — {{#if}} support, deficit_range global, schema additions

**Files:**
- Modify: `src/briefing/schemas.py`
- Modify: `src/briefing/renderer.py`
- Test: `tests/test_renderer.py`

- [ ] **Step 1: Write failing tests**

In `tests/test_renderer.py` add:
```python
def test_handlebars_if_block_converted():
    src = "{{#if x.n}}has{{/if}}"
    out = _handlebars_to_jinja2(src)
    assert "{% if x.n %}" in out
    assert "{% endif %}" in out


def test_deficit_range_helper_via_render():
    # rendered indirectly: build a tiny template using the global
    from jinja2 import Environment, BaseLoader, StrictUndefined
    from src.briefing.renderer import _make_deficit_range_resolver, load_ruleset
    rs = load_ruleset(RULESET_PATH)
    fn = _make_deficit_range_resolver(rs.nomenclature.indicators, "de")
    assert fn(None, None, "cdi") == ""
    # single (min == max) uses the `single` template
    assert "trocken" in fn(3, 3, "cdi")
    # range uses adjectives + range template
    out = fn(2, 4, "niederschlag")
    assert "bis" in out and "Niederschlagsdefizit" in out
```

- [ ] **Step 2: Run, expect fail**

Run: `uv run pytest tests/test_renderer.py -k "if_block or deficit_range" -v`
Expected: FAIL.

- [ ] **Step 3: Schema additions**

In `src/briefing/schemas.py`:
- Add to `NomenclatureIndicatorSpec`:
```python
    range: dict[str, str] | None = None
    single: dict[str, str] | None = None
```
- Add new models:
```python
class BannerLinkSpec(BaseModel):
    label: dict[str, str]
    url: str
    model_config = ConfigDict(extra="forbid")


class WeiterfuehrendeLinkSpec(BaseModel):
    label: dict[str, str]
    url: str | dict[int, str]   # plain url, or canton-id-keyed url map
    model_config = ConfigDict(extra="forbid")
```
- Add to `RulesetSchema` (optional so older rulesets still validate):
```python
    banner: list[BannerLinkSpec] | None = None
    weiterfuehrende_links: list[WeiterfuehrendeLinkSpec] | None = None
```

- [ ] **Step 4: Renderer changes**

In `src/briefing/renderer.py`:
- Add regexes near the top:
```python
_IF_OPEN = re.compile(r"\{\{#if\s+(.+?)\s*\}\}")
_IF_CLOSE = re.compile(r"\{\{/if\}\}")
```
- In `_handlebars_to_jinja2`, before the `_THIS_INPLACE` substitution:
```python
    src = _IF_OPEN.sub(r"{% if \1 %}", src)
    src = _IF_CLOSE.sub("{% endif %}", src)
```
- Add the resolver factory:
```python
def _make_deficit_range_resolver(indicators, locale: str):
    def deficit_range(min_idx, max_idx, key):
        spec = indicators[key]
        if min_idx is None:
            return ""
        adj = spec.adjective or {}
        if min_idx == max_idx:
            template = spec.single[locale] if spec.single else "{val}"
            return template.format(val=adj[min_idx][locale])
        template = spec.range[locale] if spec.range else "{min} bis {max}"
        return template.format(min=adj[min_idx][locale], max=adj[max_idx][locale])
    return deficit_range
```
- In `render_briefing`, after the `trend` global line:
```python
    env.globals["deficit_range"] = _make_deficit_range_resolver(
        ruleset.nomenclature.indicators, locale
    )
```

- [ ] **Step 5: Run, expect pass**

Run: `uv run pytest tests/test_renderer.py -k "if_block or deficit_range" -v`
Expected: PASS. (Will pass only after the YAML in Task 7 adds `range`/`single`/`adjective`; if the `niederschlag`/`cdi` entries lack them yet, implement Task 7 first or guard with the `if spec.range` fallbacks. The fallbacks make the helper safe; the single-`cdi` assertion needs `cdi.single`, added in Task 7. Run this test again at the end of Task 7.)

- [ ] **Step 6: Commit**

```bash
git add src/briefing/schemas.py src/briefing/renderer.py tests/test_renderer.py
git commit -m "feat: renderer {{#if}} support, deficit_range global, banner/links schema"
```

---

## Task 7: YAML ruleset edits

**Files:**
- Modify: `data/ruleset/canton-bulletin.yaml`
- Test: `tests/test_renderer.py`

- [ ] **Step 1: Add `trend.situation`** (after the `trend.defizit` block, same indentation under `trend:`):
```yaml
  situation:
    rule: "delta = sum(forecast cdi) - sum(current cdi); >0 worsens"
    stable_tolerance: 0
    increase: { de: "wird sich voraussichtlich verschlechtern", fr: "devrait se détériorer",   it: "—" }
    decrease: { de: "wird sich voraussichtlich verbessern",     fr: "devrait s'améliorer",     it: "—" }
    stable:   { de: "wird voraussichtlich unverändert bleiben", fr: "devrait rester stable",   it: "—" }
```

- [ ] **Step 2: Extend `cdi` nomenclature** — add `range` + `single` keys (under `nomenclature.cdi`):
```yaml
    range:  { de: "{min} bis {max}", fr: "{min} à {max}" }
    single: { de: "{val}",           fr: "{val}" }
```

- [ ] **Step 3: Extend `niederschlag` nomenclature** — add `adjective`, `range`, `single` (under `nomenclature.niederschlag`):
```yaml
    adjective:
      1: { de: "geringes",    fr: "faible",   it: "scarso" }
      2: { de: "leichtes",    fr: "léger",    it: "leggero" }
      3: { de: "erhebliches", fr: "modéré",   it: "notevole" }
      4: { de: "grosses",     fr: "élevé",    it: "grande" }
      5: { de: "extremes",    fr: "extrême",  it: "estremo" }
    range:  { de: "ein {min} bis {max} Niederschlagsdefizit", fr: "un déficit pluviométrique {min} à {max}" }
    single: { de: "ein {val} Niederschlagsdefizit",           fr: "un déficit pluviométrique {val}" }
```

- [ ] **Step 4: Add `banner` block** (top-level, after `references:`):
```yaml
banner:
  - label: { de: "Trockenheitsportal", fr: "Portail sécheresse" }
    url: "https://www.trockenheit.admin.ch"
  - label: { de: "Waldbrandgefahr", fr: "Danger d'incendie de forêt" }
    url: "https://www.waldbrandgefahr.ch"
  - label: { de: "Naturgefahrenportal", fr: "Portail des dangers naturels" }
    url: "https://www.naturgefahren.ch"

weiterfuehrende_links:
  - label: { de: "Grundwasserdaten Kanton Bern", fr: "Données des eaux souterraines canton de Berne" }
    url:
      2: "https://www.bvd.be.ch/de/start/themen/wasser/hydrologische-daten/regionale-grundwasserauswertung.html"
  - label: { de: "Vegetationszustand (VHI)", fr: "État de la végétation (VHI)" }
    url: "https://www.trockenheit.admin.ch/de/faktoren/vegetation/vegetationszustand-vhi"
```

- [ ] **Step 5: Rewrite `allgemeine-lage` template** (replace the `template:` de/fr bodies):
```yaml
    template:
      de: |
        Im Kanton {{ canton.canton_name_de }} sind aktuell {{ canton.n_regions_dry }} von {{ canton.regions|length }} Regionen trocken{{#if canton.cdi_min_dry}} ({{ deficit_range(canton.cdi_min_dry, canton.cdi_max_dry, "cdi") }}){{/if}}. Die Situation {{ trend(canton.cdi_situation_delta, "situation") }}.

        In den vergangenen 30 Tagen sind durchschnittlich rund {{ canton.mean_precip_sum_1m }} mm Niederschlag gefallen (3-Monats-Summe: {{ canton.mean_precip_sum_3m }} mm). Im langjährigen Vergleich bedeutet dies regional {{ deficit_range(canton.precip_index_min, canton.precip_index_max, "niederschlag") }}.

        {{#if canton.discharge.n_total}}{{ canton.discharge.pct_low }} % der Abflussmessstationen im Kanton weisen aktuell einen niedrigen Abfluss (7-Tages-Mittel) auf. Davon liegen {{ canton.discharge.n_very_low }} Stationen im sehr niedrigen Bereich.{{/if}}{{#if not canton.discharge.n_total}}Im Kanton liegen keine Abflussmessstationen vor.{{/if}}

        Bei der Bodenfeuchte weisen {{ canton.n_regions_with_soil_moisture_deficit }} von {{ canton.regions|length }} Warnregionen ein Defizit auf.
      fr: |
        Dans le canton de {{ canton.canton_name_fr }}, {{ canton.n_regions_dry }} régions sur {{ canton.regions|length }} sont actuellement en situation de sécheresse{{#if canton.cdi_min_dry}} ({{ deficit_range(canton.cdi_min_dry, canton.cdi_max_dry, "cdi") }}){{/if}}. La situation {{ trend(canton.cdi_situation_delta, "situation") }}.

        Au cours des 30 derniers jours, il est tombé en moyenne environ {{ canton.mean_precip_sum_1m }} mm de précipitations (cumul sur 3 mois : {{ canton.mean_precip_sum_3m }} mm). En comparaison pluriannuelle, cela représente régionalement {{ deficit_range(canton.precip_index_min, canton.precip_index_max, "niederschlag") }}.

        {{#if canton.discharge.n_total}}{{ canton.discharge.pct_low }} % des stations de mesure du débit du canton présentent actuellement un débit faible (moyenne sur 7 jours). Parmi elles, {{ canton.discharge.n_very_low }} stations se situent dans la plage très basse.{{/if}}{{#if not canton.discharge.n_total}}Le canton ne dispose d'aucune station de mesure du débit.{{/if}}

        Concernant l'humidité du sol, {{ canton.n_regions_with_soil_moisture_deficit }} régions sur {{ canton.regions|length }} présentent un déficit.
```

- [ ] **Step 6: Rewrite `regionen` template** (replace the `template:` de/fr bodies):
```yaml
    template:
      de: |
        {{#each canton.regions}}
        ### {{ this.region_name_de }}

        In den vergangenen 30 Tagen sind in der Region {{ this.region_name_de }} rund {{ this.precip_sum_1m }} mm Niederschlag gefallen (3-Monats-Summe: {{ this.precip_sum_3m }} mm). Die Region weist damit aktuell {{ nomenclature.niederschlag.noun[this.precip_1m_index].de }} auf. Das Defizit wird in nächster Zeit tendenziell {{ trend(this.precip_deficit_delta, "defizit") }}.

        {{#if this.discharge.n_total}}{{ this.discharge.pct_low }} % der Abflussmessstationen weisen aktuell einen niedrigen Abfluss (7-Tages-Mittel) auf. Davon liegen {{ this.discharge.n_very_low }} Stationen im sehr niedrigen Bereich.{{/if}}{{#if not this.discharge.n_total}}In dieser Region liegen keine Abflussmessstationen vor.{{/if}}

        Es besteht zurzeit {{ nomenclature.bodenfeuchte.noun[this.soil_moisture_index].de }}. Das Defizit wird in nächster Zeit tendenziell {{ trend(this.soil_moisture_deficit_delta, "defizit") }}.

        {{/each}}
      fr: |
        {{#each canton.regions}}
        ### {{ this.region_name_de }}

        Au cours des 30 derniers jours, environ {{ this.precip_sum_1m }} mm de précipitations sont tombés dans la région {{ this.region_name_de }} (cumul sur 3 mois : {{ this.precip_sum_3m }} mm). La région présente actuellement {{ nomenclature.niederschlag.noun[this.precip_1m_index].fr }}. Le déficit va probablement {{ trend(this.precip_deficit_delta, "defizit") }} prochainement.

        {{#if this.discharge.n_total}}{{ this.discharge.pct_low }} % des stations de mesure du débit présentent actuellement un débit faible (moyenne sur 7 jours). Parmi elles, {{ this.discharge.n_very_low }} stations se situent dans la plage très basse.{{/if}}{{#if not this.discharge.n_total}}Cette région ne dispose d'aucune station de mesure du débit.{{/if}}

        Concernant l'humidité du sol, il y a actuellement {{ nomenclature.bodenfeuchte.noun[this.soil_moisture_index].fr }}. Le déficit va probablement {{ trend(this.soil_moisture_deficit_delta, "defizit") }} prochainement.

        {{/each}}
```

- [ ] **Step 7: Run renderer tests**

Run: `uv run pytest tests/test_renderer.py -v`
Expected: PASS (incl. the deficit_range/if tests from Task 6 and the existing integration tests, which still assert "Bern"/"Mässige Gefahr" are present — note the new allgemeine-lage no longer contains "Mässige Gefahr"; update those assertions: replace `assert "Mässige Gefahr" in doc.sections["allgemeine-lage"]` with `assert "Bern" in doc.sections["allgemeine-lage"]` and the FR equivalent with `"Berne"`).

- [ ] **Step 8: Commit**

```bash
git add data/ruleset/canton-bulletin.yaml tests/test_renderer.py
git commit -m "feat: integrate revised text blocks into canton-bulletin.yaml"
```

---

## Task 8: Render banner + weiterfuehrende_links in app + export

**Files:**
- Modify: `src/models.py` (BriefingDocument), `src/briefing/renderer.py`
- Modify: `app.py`, `src/export/report.py`
- Test: `tests/test_renderer.py`, `tests/test_export.py`

- [ ] **Step 1: Write failing test**

In `tests/test_renderer.py` add:
```python
def test_render_exposes_banner_and_links(_bern_canton):
    canton, ruleset = _bern_canton
    doc = render_briefing(canton, ruleset, locale="de")
    assert any(b["label"] == "Trockenheitsportal" for b in doc.banner)
    assert any("VHI" in l["label"] for l in doc.weiterfuehrende_links)
    # canton-keyed url resolved to a plain string for canton 2
    gw = next(l for l in doc.weiterfuehrende_links if "Grundwasser" in l["label"])
    assert gw["url"].startswith("https://www.bvd.be.ch")
```

- [ ] **Step 2: Run, expect fail**

Run: `uv run pytest tests/test_renderer.py -k banner_and_links -v`
Expected: FAIL.

- [ ] **Step 3: Add BriefingDocument fields**

In `src/models.py` `BriefingDocument`:
```python
    banner: list = field(default_factory=list)                 # list[dict]: {label, url}
    weiterfuehrende_links: list = field(default_factory=list)   # list[dict]: {label, url}
```

- [ ] **Step 4: Populate in renderer**

In `src/briefing/renderer.py` `render_briefing`, build localized, canton-resolved lists and pass to `BriefingDocument`:
```python
    banner = [
        {"label": b.label.get(locale, b.label.get("de", "")), "url": b.url}
        for b in (ruleset.banner or [])
    ]
    links = []
    for l in (ruleset.weiterfuehrende_links or []):
        url = l.url
        if isinstance(url, dict):
            url = url.get(canton.canton_id)
        if url is None:
            continue  # link not available for this canton
        links.append({"label": l.label.get(locale, l.label.get("de", "")), "url": url})
```
Add `banner=banner, weiterfuehrende_links=links` to the `BriefingDocument(...)` return.

- [ ] **Step 5: Run, expect pass**

Run: `uv run pytest tests/test_renderer.py -k banner_and_links -v`
Expected: PASS.

- [ ] **Step 6: Render in app.py**

In `app.py`, after the lead box `st.markdown(...)` (before `st.divider()` at line ~114), add a banner link row:
```python
if doc.banner:
    banner_html = " · ".join(
        f'<a href="{b["url"]}" target="_blank">{b["label"]}</a>' for b in doc.banner
    )
    st.markdown(banner_html, unsafe_allow_html=True)
```
After the text-sections loop (after line ~154), add the links:
```python
if doc.weiterfuehrende_links:
    st.markdown("#### " + ("Weiterführende Links" if lang == "de" else "Liens complémentaires"))
    for l in doc.weiterfuehrende_links:
        st.markdown(f"- [{l['label']}]({l['url']})")
```

- [ ] **Step 7: Render in export/report.py**

In `src/export/report.py`, build a banner string from `doc.banner` and a links list from `doc.weiterfuehrende_links` (HTML-escaped) and inject into the `<main>` HTML (banner before sections, links after). Add:
```python
    banner_html = " · ".join(
        f'<a href="{html.escape(b["url"])}">{html.escape(b["label"])}</a>' for b in doc.banner
    )
    links_html = "".join(
        f'<li><a href="{html.escape(l["url"])}">{html.escape(l["label"])}</a></li>'
        for l in doc.weiterfuehrende_links
    )
    links_block = f"<ul>{links_html}</ul>" if links_html else ""
```
and change the `<main>` line to:
```python
f'<main>{f"<p>{banner_html}</p>" if banner_html else ""}{sections_html}{links_block}</main>'
```

- [ ] **Step 8: Run export tests**

Run: `uv run pytest tests/test_export.py -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/models.py src/briefing/renderer.py app.py src/export/report.py tests/test_renderer.py
git commit -m "feat: render banner and weiterführende links in app and export"
```

---

## Task 9: stlite file list + full suite

**Files:**
- Modify: `docs/index.html`

- [ ] **Step 1: Add stations.py to stlite list**

In `docs/index.html`, in the explicit source-file list, add `"src/aggregation/stations.py"` next to the other `src/aggregation/*.py` entries. (Grep: `grep -n "aggregation/" docs/index.html`.)

- [ ] **Step 2: Run full suite**

Run: `uv run pytest tests/ -v`
Expected: ALL PASS.

- [ ] **Step 3: Commit**

```bash
git add docs/index.html
git commit -m "chore: register stations.py in stlite build"
```

---

## Self-review notes

- Spec coverage: station loading (T2), discharge stats incl. zero-station (T3, T7 phrasing), canton CDI situation trend (T5/T7), mean precip (T5), deficit ranges cdi+niederschlag (T6/T7), per-region deficit trends (T4/T7), banner+links canton-keyed (T6/T8), `{{#if}}` (T6). All covered.
- Type consistency: `DischargeStats(n_total, n_low, n_very_low, pct_low)` used identically across T1/T3/T4/T5. `_forecast_week2_value(bundle, region_id, column)` defined once (T4) and reused. `deficit_range(min, max, key)` signature consistent T6/T7.
- French strings are first-draft; flagged for user review (spec follow-up).

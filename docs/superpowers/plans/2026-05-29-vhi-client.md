# VHI Client Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace VHI values read from the STAC fixture CSV with live data from the SwissEO endpoint, using a new `vhi_client.py` that mirrors the `warnkarte_client.py` pattern.

**Architecture:** A new `src/data/vhi_client.py` fetches a single CSV from the SwissEO URL and returns `dict[int, float]` keyed by `drought_region_id`. `canton.py` calls it alongside `warnkarte_client`, passing each region's VHI float into `compute_region_report()` via a new `vhi_value` parameter. `vhi_delta` is hardcoded to `0.0` because the SwissEO source is a current-snapshot-only API with no history.

**Tech Stack:** `requests`, `pandas`, `responses` (test mocking — already used in `test_warnkarte_client.py`)

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Modify | `config/settings.py` | Add `VHI_URL` and `VHI_FIXTURE` constants |
| Create | `data/vhi_fixture.csv` | Offline fallback snapshot of SwissEO CSV |
| Create | `src/data/vhi_client.py` | Fetch SwissEO VHI + fixture fallback |
| Create | `tests/test_vhi_client.py` | Unit tests for `vhi_client` |
| Modify | `src/aggregation/regional.py` | Accept `vhi_value: float \| None`; set `vhi_delta = 0.0` |
| Modify | `src/aggregation/canton.py` | Call `vhi_client.fetch_for_regions()`, pass result through |

---

## Task 1: Add constants to `config/settings.py`

**Files:**
- Modify: `config/settings.py`

- [ ] **Step 1: Add `VHI_URL` and `VHI_FIXTURE` below the existing STAC constants**

  Open `config/settings.py`. After the `STAC_COLLECTION` line (line 44), add:

  ```python
  VHI_URL: Final[str] = (
      "https://data.geo.admin.ch/ch.swisstopo.swisseo_vhi_v100"
      "/swisseo_vhi_v100"
      "/ch.swisstopo.swisseo_vhi_v100_current_vegetation-warnregions.csv"
  )
  VHI_FIXTURE: Final[Path] = DATA_DIR / "vhi_fixture.csv"
  ```

- [ ] **Step 2: Verify the file parses without errors**

  ```bash
  uv run python -c "from config.settings import VHI_URL, VHI_FIXTURE; print(VHI_URL); print(VHI_FIXTURE)"
  ```

  Expected output:
  ```
  https://data.geo.admin.ch/ch.swisstopo.swisseo_vhi_v100/swisseo_vhi_v100/ch.swisstopo.swisseo_vhi_v100_current_vegetation-warnregions.csv
  /home/.../data/vhi_fixture.csv
  ```

- [ ] **Step 3: Commit**

  ```bash
  git add config/settings.py
  git commit -m "feat: add VHI_URL and VHI_FIXTURE constants"
  ```

---

## Task 2: Download the VHI fixture file

**Files:**
- Create: `data/vhi_fixture.csv`

- [ ] **Step 1: Download the current SwissEO CSV as the fixture**

  ```bash
  curl -o data/vhi_fixture.csv \
    "https://data.geo.admin.ch/ch.swisstopo.swisseo_vhi_v100/swisseo_vhi_v100/ch.swisstopo.swisseo_vhi_v100_current_vegetation-warnregions.csv"
  ```

- [ ] **Step 2: Verify the file contains the expected columns**

  ```bash
  head -3 data/vhi_fixture.csv
  ```

  Expected output (header + two data rows):
  ```
  REGION_NR,vhi_mean,availability_percentage
  31,68,99.2
  32,79,99.0
  ```

- [ ] **Step 3: Verify Berne region IDs are present (33, 34, 35, 37, 38, 41)**

  ```bash
  uv run python -c "
  import pandas as pd
  df = pd.read_csv('data/vhi_fixture.csv')
  berne = df[df['REGION_NR'].isin([33,34,35,37,38,41])]
  print(berne.to_string(index=False))
  "
  ```

  Expected: 6 rows, one per Berne region, all with non-NaN `vhi_mean`.

- [ ] **Step 4: Commit**

  ```bash
  git add data/vhi_fixture.csv
  git commit -m "feat: add SwissEO VHI fixture for offline fallback"
  ```

---

## Task 3: Create `src/data/vhi_client.py` (TDD)

**Files:**
- Create: `tests/test_vhi_client.py`
- Create: `src/data/vhi_client.py`

- [ ] **Step 1: Write the failing tests**

  Create `tests/test_vhi_client.py`:

  ```python
  # tests/test_vhi_client.py
  import io

  import pytest
  import responses

  from src.data.vhi_client import _parse_csv, fetch_for_regions

  _VHI_URL = (
      "https://data.geo.admin.ch/ch.swisstopo.swisseo_vhi_v100"
      "/swisseo_vhi_v100"
      "/ch.swisstopo.swisseo_vhi_v100_current_vegetation-warnregions.csv"
  )
  _CSV_BODY = (
      "REGION_NR,vhi_mean,availability_percentage\n"
      "33,61.8,99.9\n"
      "34,68.0,96.8\n"
      "35,82.0,80.5\n"
      "99,50.0,90.0\n"
  )


  def test_parse_csv_returns_requested_regions():
      result = _parse_csv(io.StringIO(_CSV_BODY), [33, 34])
      assert result == {33: pytest.approx(61.8), 34: pytest.approx(68.0)}
      assert 35 not in result
      assert 99 not in result


  def test_parse_csv_ignores_availability_percentage():
      result = _parse_csv(io.StringIO(_CSV_BODY), [33])
      assert set(result.keys()) == {33}


  @responses.activate
  def test_fetch_for_regions_live_path():
      responses.add(
          responses.GET,
          _VHI_URL,
          body=_CSV_BODY,
          status=200,
          content_type="text/csv",
      )
      out = fetch_for_regions([33, 34])
      assert out[33] == pytest.approx(61.8)
      assert out[34] == pytest.approx(68.0)
      assert 99 not in out


  @responses.activate
  def test_fetch_for_regions_falls_back_to_fixture_on_error(recwarn):
      responses.add(responses.GET, _VHI_URL, status=503)
      out = fetch_for_regions([33])
      assert 33 in out
      assert out[33] > 0
      assert any("VHI fetch failed" in str(w.message) for w in recwarn.list)


  @responses.activate
  def test_fetch_for_regions_warns_on_network_error(recwarn):
      responses.add(responses.GET, _VHI_URL, body=ConnectionError("timeout"))
      out = fetch_for_regions([33])
      assert 33 in out
      assert any("VHI fetch failed" in str(w.message) for w in recwarn.list)
  ```

- [ ] **Step 2: Run tests to confirm they fail**

  ```bash
  uv run pytest tests/test_vhi_client.py -v
  ```

  Expected: `ModuleNotFoundError: No module named 'src.data.vhi_client'` or similar — all 5 tests fail.

- [ ] **Step 3: Implement `src/data/vhi_client.py`**

  Create `src/data/vhi_client.py`:

  ```python
  # src/data/vhi_client.py
  """
  Fetches current VHI (Vegetation Health Index) per drought Warnregion
  from the SwissEO REST endpoint.

  On any network or HTTP error, falls back to data/vhi_fixture.csv.
  Same pattern as src/data/warnkarte_client.py.

  Endpoint:
    https://data.geo.admin.ch/ch.swisstopo.swisseo_vhi_v100/...
  """
  from __future__ import annotations

  import io
  import logging
  import warnings
  from pathlib import Path
  from typing import Union

  import pandas as pd

  from config.settings import VHI_FIXTURE, VHI_URL

  logger = logging.getLogger(__name__)

  _TIMEOUT_SECONDS = 10


  def fetch_for_regions(region_ids: list[int]) -> dict[int, float]:
      """
      Return {drought_region_id: vhi_mean} for each requested region.
      Falls back to data/vhi_fixture.csv on any network or HTTP error.
      """
      try:
          return _fetch_live(region_ids)
      except Exception as exc:
          warnings.warn(
              f"VHI fetch failed ({exc!r}); using bundled fixture data.",
              stacklevel=2,
          )
          return _load_from_fixture(region_ids)


  def _fetch_live(region_ids: list[int]) -> dict[int, float]:
      import requests

      response = requests.get(VHI_URL, timeout=_TIMEOUT_SECONDS)
      response.raise_for_status()
      return _parse_csv(io.StringIO(response.text), region_ids)


  def _load_from_fixture(region_ids: list[int]) -> dict[int, float]:
      return _parse_csv(VHI_FIXTURE, region_ids)


  def _parse_csv(
      source: Union[str, Path, io.StringIO],
      region_ids: list[int],
  ) -> dict[int, float]:
      df = pd.read_csv(source)
      df = df[df["REGION_NR"].isin(region_ids)]
      return {int(row["REGION_NR"]): float(row["vhi_mean"]) for _, row in df.iterrows()}
  ```

- [ ] **Step 4: Run tests to confirm they pass**

  ```bash
  uv run pytest tests/test_vhi_client.py -v
  ```

  Expected: all 5 tests `PASSED`.

- [ ] **Step 5: Commit**

  ```bash
  git add src/data/vhi_client.py tests/test_vhi_client.py
  git commit -m "feat: add vhi_client with SwissEO fetch and fixture fallback"
  ```

---

## Task 4: Update `regional.py` to accept `vhi_value`

**Files:**
- Modify: `src/aggregation/regional.py`
- Modify: `tests/test_aggregation.py`

- [ ] **Step 1: Write the failing test**

  Add this test to `tests/test_aggregation.py`:

  ```python
  def test_vhi_value_param_overrides_row_vhi(bundle):
      report = compute_region_report(34, bundle, vhi_value=42.5)
      assert report.vhi == pytest.approx(42.5)


  def test_vhi_delta_is_zero_when_vhi_value_provided(bundle):
      report = compute_region_report(34, bundle, vhi_value=42.5)
      assert report.vhi_delta == 0.0
  ```

  Also add `import pytest` to the imports at the top of `tests/test_aggregation.py` if not already present.

- [ ] **Step 2: Run to verify the tests fail**

  ```bash
  uv run pytest tests/test_aggregation.py::test_vhi_value_param_overrides_row_vhi tests/test_aggregation.py::test_vhi_delta_is_zero_when_vhi_value_provided -v
  ```

  Expected: `FAILED` — `compute_region_report() got an unexpected keyword argument 'vhi_value'`.

- [ ] **Step 3: Update the signature and body of `compute_region_report` in `src/aggregation/regional.py`**

  Change the function signature (line 15) to:

  ```python
  def compute_region_report(
      region_id: int,
      bundle: DataBundle,
      warnkarte_entry: WarnkarteEntry | None = None,
      vhi_value: float | None = None,
  ) -> RegionReport:
  ```

  Change the `vhi` assignment (currently `vhi = _safe(row["vhi"])`):

  ```python
  vhi = float(vhi_value) if vhi_value is not None else _safe(row["vhi"])
  ```

  In the trends block, remove the `prior_vhi` lines and set `vhi_delta = 0.0` unconditionally. Replace the entire `if prior_row is not None:` block with:

  ```python
  if prior_row is not None:
      prior_cdi = int(prior_row["cdi"]) if not pd.isna(prior_row["cdi"]) else cdi
      prior_spi = _safe(prior_row["spi_3m"])
      cdi_trend = compute_trend(cdi, prior_cdi)
      spi_3m_delta = spi_3m - prior_spi if not math.isnan(spi_3m) and not math.isnan(prior_spi) else 0.0
  else:
      cdi_trend = 0
      spi_3m_delta = 0.0
  vhi_delta = 0.0
  ```

- [ ] **Step 4: Run the new tests and the full aggregation suite**

  ```bash
  uv run pytest tests/test_aggregation.py -v
  ```

  Expected: all tests `PASSED`.

- [ ] **Step 5: Commit**

  ```bash
  git add src/aggregation/regional.py tests/test_aggregation.py
  git commit -m "feat: compute_region_report accepts vhi_value override; vhi_delta always 0.0"
  ```

---

## Task 5: Wire `vhi_client` into `canton.py`

**Files:**
- Modify: `src/aggregation/canton.py`
- Modify: `tests/test_canton.py`

- [ ] **Step 1: Write the failing integration test**

  Add this test to `tests/test_canton.py`:

  ```python
  import pytest
  import responses

  _VHI_URL = (
      "https://data.geo.admin.ch/ch.swisstopo.swisseo_vhi_v100"
      "/swisseo_vhi_v100"
      "/ch.swisstopo.swisseo_vhi_v100_current_vegetation-warnregions.csv"
  )
  _VHI_CSV = (
      "REGION_NR,vhi_mean,availability_percentage\n"
      "33,55.0,99.9\n34,60.0,96.8\n35,70.0,80.5\n"
      "37,45.0,99.9\n38,80.0,95.0\n41,65.0,77.6\n"
  )


  @responses.activate
  def test_canton_report_uses_swisseo_vhi():
      responses.add(
          responses.GET,
          _VHI_URL,
          body=_VHI_CSV,
          status=200,
          content_type="text/csv",
      )
      bundle = load_data()
      warnkarte = {rid: _make_warnkarte(rid, 2) for rid in [33, 34, 35, 37, 38, 41]}
      canton = compute_canton_report(canton_id=2, bundle=bundle, warnkarte_data=warnkarte)
      region_34 = next(r for r in canton.regions if r.region_id == 34)
      assert region_34.vhi == pytest.approx(60.0)
  ```

- [ ] **Step 2: Run to verify the test fails**

  ```bash
  uv run pytest tests/test_canton.py::test_canton_report_uses_swisseo_vhi -v
  ```

  Expected: `FAILED` — region_34.vhi is not `60.0` (canton.py doesn't call vhi_client yet).

- [ ] **Step 3: Update `src/aggregation/canton.py`**

  Add the import at the top (alongside existing imports):

  ```python
  from src.data import vhi_client
  ```

  In `compute_canton_report`, add the VHI fetch before the list comprehension. Replace:

  ```python
  region_ids = sorted(CANTON_TO_REGIONS[canton_id])
  region_reports = [
      compute_region_report(rid, bundle, warnkarte_entry=warnkarte_data.get(rid))
      for rid in region_ids
  ]
  ```

  With:

  ```python
  region_ids = sorted(CANTON_TO_REGIONS[canton_id])
  vhi_data = vhi_client.fetch_for_regions(list(region_ids))
  region_reports = [
      compute_region_report(
          rid,
          bundle,
          warnkarte_entry=warnkarte_data.get(rid),
          vhi_value=vhi_data.get(rid),
      )
      for rid in region_ids
  ]
  ```

- [ ] **Step 4: Run all canton tests**

  ```bash
  uv run pytest tests/test_canton.py -v
  ```

  Expected: all tests `PASSED`.

- [ ] **Step 5: Commit**

  ```bash
  git add src/aggregation/canton.py tests/test_canton.py
  git commit -m "feat: wire vhi_client into canton report; VHI now sourced from SwissEO"
  ```

---

## Task 6: Full test suite

- [ ] **Step 1: Run the complete test suite**

  ```bash
  uv run pytest tests/ -v
  ```

  Expected: all tests `PASSED`. If any fail, investigate and fix before proceeding.

- [ ] **Step 2: Smoke-test the app**

  ```bash
  make up
  ```

  Open `http://localhost:8501` and verify the Berne briefing loads without errors. Check that VHI values appear (not NaN) for all six Berne regions. Stop the app when done.

  ```bash
  make down
  ```

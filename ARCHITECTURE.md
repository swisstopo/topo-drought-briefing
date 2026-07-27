# ARCHITECTURE.md

# Drought Briefing Architecture

Version: 1.0

Status: Target Architecture

---

# Overview

The Drought Briefing platform is a fully static web application generated from automated daily data processing workflows.

The architecture follows a strict separation between:

1. Data Acquisition
2. Data Processing
3. Rule Evaluation
4. Static Content Generation
5. Website Publication

The frontend never performs scientific calculations.

All drought assessments are generated during the build process.

---

# High-Level Architecture

```text
External Data Sources
          │
          ▼
 GitHub Actions
          │
          ▼
 Data Download                      (scripts/download.py)
          │
          ▼
 Spatial Aggregation + Rule         (scripts/aggregate.py — currently one
 Evaluation + JSON Generation        script; see § Processing Layer)
          │
          ▼
 Data Validation                    (scripts/validate.py, validates the
          │                          JSON written by aggregate.py)
          ▼
 Static Website Generation          (scripts/generate_site.py)
          │
          ▼
 GitHub Pages
```

Note the actual order: validation runs **after** aggregation, checking the
generated JSON against the schema contract — not before, against raw
downloads, as an earlier version of this diagram implied. See § Validation
Module below.

---

# Repository Structure

```text
drought-briefing/

├── config/            YAML/Python configuration (see below)
│
├── data/
│   ├── raw/           gitignored — live downloads, written by scripts/download.py
│   ├── processed/     gitignored — aggregate.py output, read by generate_site.py
│   ├── fixtures/       committed — offline fallback data
│   └── ruleset/        committed — drought rules/templates (canton-bulletin.yaml)
│
├── scripts/           pipeline entry points (see Processing Layer)
│
├── src/               pipeline library code: aggregation/, briefing/, data/, i18n/, quality/, viz/
│
├── site/              gitignored — generate_site.py output, published to GitHub Pages
│
├── tests/
│
└── .github/
    └── workflows/     daily-update.yml, int-preview.yml
```

`data/raw/` and `data/processed/` are build artifacts, not checked into the
repository (see `.gitignore`) — they exist only during/after a pipeline run.
`src/` is the current implementation's actual library layer and is the
largest part of the codebase; earlier revisions of this document omitted it
entirely.

---

# Configuration Layer

All operational configuration shall be stored in YAML where practical.

**Current implementation:**

```text
config/

  sources.yaml     — data source list shown on the site (config/sources.yaml)
  rules.yaml       — drought thresholds (loaded via rules_loader.py)
  rules_loader.py  — validates and exposes rules.yaml as RULES
  settings.py      — canton/region master data, derived constants (Python,
                     not YAML — see § Internationalization for why this is
                     a known gap, not the target state)
  schemas/         — JSON Schema for data/processed/ output validation
```

Region/canton master data and templates currently live outside `config/`:
canton↔region mapping in `data/kantone_warnregionen.json`
(read by `settings.py`), and bulletin rules/templates/nomenclature in
`data/ruleset/canton-bulletin.yaml`. A standalone `regions.yaml`,
`messages.yaml`, `translations.yaml`, or `site.yaml` does not exist today —
see § Internationalization for the proposed consolidation of the
translation-relevant parts of this gap.

Configuration must be editable by non-programmers.

No drought thresholds shall be hardcoded in Python.

---

# Configuration Responsibilities

## sources.yaml

Defines the data sources shown on the site's "Datenquellen" card (this part
*is* implemented — actual shape below, from `config/sources.yaml`):

```yaml
data_sources:
  - title:
      de: "Trockenheitswarnkarte"
      fr: "Carte d'alerte à la sécheresse"
    url: "https://api3.geo.admin.ch/rest/services/api/MapServer/ch.bafu.trockenheitswarnkarte"
    provider: "BAFU"
```

Note this is a source *listing* for display, not an enable/disable switch
per indicator as the earlier illustrative example below suggested — there is
no `sources.vhi.enabled` construct. That illustrative shape was never
implemented:

```yaml
sources:

  vhi:
    enabled: true

  groundwater:
    enabled: true

  precipitation:
    enabled: true
```

---

## regions.yaml

Defines aggregation regions. **Not implemented as a standalone file today**
— canton↔region master data currently lives in `data/kantone_warnregionen.json`
(read by `config/settings.py`), and the canton-level curated override lives
in `config/settings.py`'s `CANTON_TO_REGIONS`.

Target example:

```yaml
regions:

  national:
    enabled: true

  cantons:
    enabled: true

  warning_regions:
    enabled: true
```

---

## rules.yaml

Defines drought classifications.

Actual current shape (`config/rules.yaml`, VHI section) — an index→float
threshold map plus a separate "counts as stressed" cutoff, not named bands:

```yaml
vhi:
  stress_index_min: 2   # index >= this counts a region as "stressed"

  # Classify a VHI float (0-100) into a stress index 1-5.
  thresholds:
    1: 40   # Normal / Good / Excellent
    2: 30   # Slightly Stressed
    3: 20   # Stressed
    4: 10   # Very Stressed
    5: 0    # Extremely Stressed
```

Loaded and validated by `config/rules_loader.py`, exposed as `RULES`.

---

## messages.yaml

Contains multilingual drought messages. **Not implemented as a standalone
file today** — translatable text is currently spread across
`config/settings.py`, `config/sources.yaml`, and
`data/ruleset/canton-bulletin.yaml` instead. See § Internationalization below
for the current state and a proposed consolidation.

Target example:

```yaml
messages:

  severe:

    de: Critical drought conditions.

    fr: Conditions de sécheresse critiques.

    it: Condizioni di siccità critiche.
```

---

# Internationalization

> **Status: proposal only.** This section documents a centralized translation
> design as a target to migrate towards. It is **not implemented** —
> `config/settings.py`, `data/ruleset/canton-bulletin.yaml`, `src/models.py`,
> and `config/sources.yaml` still use their current, inconsistent per-language
> patterns described below. Implementing this migration is a separate,
> future plan, not part of the work that introduced this section.

## The problem

Translatable strings are currently duplicated across the codebase in at
least four different shapes, with no single source of truth:

- **`config/settings.py`** mixes two nesting conventions for what is
  conceptually the same kind of data (a name lookup by id):
  `CANTON_NAMES` is `dict[canton_id, dict[lang, name]]` (nested by id), while
  `REGION_NAMES_DE`/`REGION_NAMES_FR` and `CDI_LABELS`/`CDI_LABELS_FR` are
  flat, separate per-language dicts (and neither pair has an `_IT` variant).
  This inconsistency already causes silent rot: `CANTON_NAMES[2]` (Bern) has
  a populated `"it": "Berna"` entry, but nothing downstream ever reads it —
  `src/aggregation/canton.py` only looks up `names["de"]`/`names["fr"]`, and
  `CantonReport` (`src/models.py`) has no `canton_name_it` field at all. The
  Italian name has been sitting there, unused and unreachable, since it was
  added.
- **`config/sources.yaml`** duplicates `title: {de, fr}` per source entry by
  hand, with a comment mandating both languages be filled in — no Italian,
  no shared/derived string.
- **`data/ruleset/canton-bulletin.yaml`** uses three different nesting shapes
  for the same underlying concept (translatable text) in one file: per-level
  lookup tables (`nomenclature.*.adjective`/`noun`, keyed `dict[level,
  dict[lang, str]]`), flat labels (`banner[].label`, `lead.warnstufe.headline`),
  and full duplicated prose blocks as sibling keys (`sections[].template.de`
  / `.fr`) — the heaviest maintenance burden, since these are independent
  paragraphs that must be kept semantically in sync by hand. Section prose
  is, in practice, only fleshed out in `de` today.
- **`src/models.py`** has five duplicated-field groups spread across four
  dataclasses (`RegionReport.warnlevel_info_de`/`_fr`,
  `CantonReport.canton_name_de`/`_fr`, `CantonReport.max_warnlevel_info_de`/
  `_fr`, `WarnkarteEntry.info_de`/`_fr`/`_it`, `MapSpec.title_de`/`_fr`) —
  plus one outright inconsistency: `RegionReport.region_name_de` has no
  `_fr` counterpart at all; French region names are instead looked up
  separately, by id, via `config.settings.REGION_NAMES_FR`.
- **`src/i18n/strings.py`** is the best pattern already in the codebase: one
  `UI_STRINGS: dict[lang, dict[key, str]]` dict, with a single `t(key, lang)`
  accessor and a defined German-fallback chain. But it still has no Italian,
  and it re-exports `config.settings`'s `CDI_LABELS`/`REGION_NAMES_DE`/`_FR`
  directly — coupling this otherwise-disciplined module to the less
  disciplined dicts above, rather than replacing them.

Per this project's config-first principle, none of this should require a
Python code change to add a language or edit a string — but today, several
of these paths do.

## Proposed shape

Adopt one canonical shape everywhere: `{key: {lang: value}}`, matching
`src/i18n/strings.py`'s existing `t(key, lang)` accessor — it is already
implemented, already the most disciplined of the existing patterns, and
needs the least new machinery to extend.

Mapping each current pain point onto it:

- Canton names, region names, and CDI labels fold into one consolidated
  translation catalog (e.g. `config/translations/catalog.yaml`), each entry
  keyed once with a `{lang: value}` map — replacing `CANTON_NAMES`,
  `REGION_NAMES_DE`/`_FR`, `CDI_LABELS`/`_FR` with a single, uniform lookup.
- `config/sources.yaml` entries reference a translation key
  (e.g. `title_key: source.warnkarte.title`) instead of inlining `{de, fr}`.
- `canton-bulletin.yaml`'s prose sections remain genuinely per-language
  (that part is unavoidable — the paragraphs really are different text), but
  converge on the same `{key: {lang: ...}}` nesting depth as everything else,
  instead of three different ad hoc shapes in one file.
- `src/models.py`'s `_de`/`_fr`/`_it` field explosion is replaced by a single
  translation-key field per model, resolved against the catalog at render
  time (rather than a field per language baked in at aggregation time) — this
  keeps translatable text out of Python data structures entirely, consistent
  with this project's "no hardcoded domain knowledge in Python" principle.

## Why this matters for future languages

Under this design, adding Italian (or any future language) becomes: add one
key to the catalog, per entry that needs it. No Python code changes, no new
dataclass fields, no new per-language dict. The `CANTON_NAMES[2]["it"]`
example above is the concrete illustration of the current cost: that Italian
name has existed in the codebase for some time, and is still unreachable,
because reaching it would require a new `canton_name_it` field on
`CantonReport`, a new read in `src/aggregation/canton.py`, and a new render
path in `scripts/generate_site.py` — three code changes for one string. Under
the proposed catalog, the same addition is one YAML line.

## Migration path (future work, not scoped here)

This is a proposal for a **future migration**, split into independent,
lower-risk-first steps:

1. `config/settings.py`'s dicts — simplest and most self-contained, no
   renderer involvement.
2. `config/sources.yaml` — small, isolated.
3. `data/ruleset/canton-bulletin.yaml` and `src/models.py` — higher risk,
   since these touch `src/briefing/renderer.py` and the JSON schema contract
   (`config/schemas/*.json`); do these last, and verify byte-identical
   generated output at each step, per this project's refactoring rules.

---

# Data Layer

## Raw Data

Downloaded datasets.

Location:

```text
data/raw/
```

Purpose:

* temporary processing
* validation input

Raw data must never be consumed by the frontend.

---

## Processed Data

Location:

```text
data/processed/
```

Purpose:

* website input
* public API-like data products

---

# Processed Data Structure

Actual current output (files named by numeric BFS canton ID / drought
region ID, not by abbreviation — `CANTON_ABBREV`/`region_name_de` are looked
up separately for display). There is no `national.json` today.

```text
data/processed/

  cantons/

      1.json
      2.json
      3.json
      ...

  warning_regions/

      31.json
      32.json
      33.json
      ...
```

---

# JSON Data Contract

All generated region and canton files shall follow a common schema, enforced
by JSON Schema files and checked by `scripts/validate.py` (see
`config/schemas/README.md`).

The actual current contract (`config/schemas/region.json`,
`config/schemas/canton.json`) is considerably larger and differently shaped
than a simple `{status, indicators, messages}` illustration would suggest —
language-specific text is flattened into suffixed fields
(`warnlevel_info_de`/`_fr`, matching `RegionReport` in `src/models.py`)
rather than a nested `messages: {de, fr, it}` dict, there is no generic
`status`/`indicators` grouping, and neither schema has an `it` field
anywhere yet (see § Internationalization). Refer to the schema files
themselves — each field already carries a `description` — rather than a
simplified example here, since a hand-written example would drift out of
sync with the real, larger contract.

This schema shall be considered stable.

Frontend components depend on it.

---

# Processing Layer

Location:

```text
scripts/
```

Modules (actual, `scripts/`):

```text
download.py

aggregate.py

validate.py

generate_site.py
```

Each module shall have a single responsibility. **Current gap:** `aggregate.py`
currently performs both spatial aggregation and rule evaluation together (it
imports `RULES` from `config.rules_loader` directly and applies thresholds
inline, e.g. `src/aggregation/canton.py`/`regional.py`) — there is no
separate `evaluate.py`, contrary to what an earlier version of this document
implied. Splitting rule evaluation into its own module remains a reasonable
future refactor, not something already done.

---

# Download Module

Purpose:

Download source datasets.

Responsibilities:

* download files
* verify availability
* store raw data

Output:

```text
data/raw/
```

---

# Validation Module

Purpose:

Verify the **generated JSON output**, after aggregation — not the raw
downloaded datasets (see the corrected pipeline order above).

Checks (actual, `scripts/validate.py`):

* every file in `data/processed/warning_regions/` and `data/processed/cantons/`
  validates against `config/schemas/region.json` / `canton.json` respectively
  (JSON Schema — required fields, types, ranges; no geometry validation, since
  the output is plain JSON, not GIS geometry)

Failure:

Workflow stops (`sys.exit(1)`; both GitHub Actions workflows run this step
before `generate_site.py`).

---

# Aggregation Module

Purpose:

Generate regional and canton statistics, **and** apply drought-rule
thresholds from `config/rules.yaml` (see the note above about this being one
module today, not two).

Input:

```text
data/raw/  (or data/fixtures/ as fallback — see data/README.md)
```

Output:

```text
data/processed/
```

Aggregation logic shall remain equivalent to the current implementation.

---

# Site Generation Module

Purpose:

Generate static website assets.

Input:

```text
data/processed/
config/
```

Output:

```text
site/
```

---

# Frontend Layer

Location:

```text
site/
```

Technology:

* HTML
* CSS
* Vanilla JavaScript

No frontend framework.

---

# Frontend Responsibilities

**Current implementation note:** the frontend does not load JSON or switch
languages at runtime. `scripts/generate_site.py` pre-renders **both** German
and French text into the same static HTML page at build time (e.g.
`<h1 class="page-title lang-de">...</h1><h1 class="page-title lang-fr">...</h1>`
side by side), and the browser only toggles CSS visibility between them
(`html[lang="fr"] .lang-de { display: none }` and the reverse) via a small
`switchLang()` JS function. There is no client-side JSON fetch/parse. This is
still a valid way to satisfy "the frontend may not calculate drought
classes" below — it just means "load JSON" is not literally how language
switching or content display works today.

The frontend may:

* render pages (pre-rendered per-locale content, toggled via CSS)
* switch languages (CSS visibility toggle, not a data reload)
* display indicators
* display maps

The frontend may not:

* calculate drought classes
* evaluate thresholds
* perform aggregation

---

# Design System

Frontend shall use:

Swiss Confederation Design System

**Current implementation:** `site/assets/style.css` is a custom, hand-written
stylesheet labeled "Swiss Confederation Design System" in its header comment
and generated inline by `scripts/generate_site.py` — it is not built from an
imported official SCDS component library or package (no `@swiss-confederation`
or similar dependency exists in this repo). It follows the visual language by
convention, not by importing the design system itself.

Objectives:

* responsive layout
* accessibility
* official visual identity
* multilingual navigation

Custom styling should be minimal.

---

# GitHub Actions Architecture

Workflows:

```text
.github/workflows/

  daily-update.yml   — scheduled + manual, deploys to the production site (/)
  int-preview.yml    — on push to INT, deploys a preview to /int/
```

Execution (both workflows, same pipeline — see the corrected step order):

1. Checkout repository
2. Install dependencies
3. Download datasets (`download.py`)
4. Aggregate + apply rules + generate JSON (`aggregate.py`)
5. Validate the generated JSON (`validate.py`)
6. Generate website (`generate_site.py`)
7. Publish to GitHub Pages (`peaceiris/actions-gh-pages`)

---

# Deployment Architecture

Deployment Target:

GitHub Pages

Published Content:

```text
site/
```

No runtime infrastructure required.

No server required.

No database required.

---

# Testing Architecture

Location:

```text
tests/
```

Actual current test modules (`tests/`):

```text
test_aggregate_script.py   test_models.py
test_aggregation.py        test_pipeline.py
test_canton.py             test_quality.py
test_fixture_loader.py     test_renderer.py
test_i18n.py               test_rules.py
                            test_schema.py
                            test_settings_cantons.py
                            test_site_generation.py
                            test_stations.py
                            test_vhi_client.py
                            test_warnkarte_client.py
```

There is no dedicated `test_download.py` — `download.py`'s network calls are
not currently unit-tested (its logic is thin: fetch and write bytes).
`test_schema.py` covers JSON schema validation; `test_rules.py` and
`test_aggregation.py`/`test_canton.py` cover rule evaluation and aggregation
logic respectively.

Coverage focus:

* rule evaluation
* aggregation logic
* YAML validation
* JSON schema validation

---

# Extensibility Principles

Future contributors shall be able to:

* add indicators
* add regions
* add languages
* add briefing products

without modifying core architecture.

Changes should primarily occur in:

```text
config/
```

rather than:

```text
scripts/
```

---

# Architectural Constraints

Mandatory:

* static website
* GitHub Pages deployment
* GitHub Actions automation
* YAML-based configuration
* multilingual support
* open-source operation

Forbidden:

* backend services
* databases
* runtime APIs
* frontend drought calculations
* hardcoded drought thresholds

---

# Success Criteria

The architecture is considered successful when:

* outputs match the current Drought-Briefing implementation
* daily updates run automatically
* deployment is automatic
* non-programmers can maintain content
* scientific logic remains transparent
* operational costs remain effectively zero
* the entire platform can be hosted from a single GitHub repository

```
```

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
 Data Download
          │
          ▼
 Data Validation
          │
          ▼
 Spatial Aggregation
          │
          ▼
 Rule Evaluation
          │
          ▼
 JSON Generation
          │
          ▼
 Static Website Generation
          │
          ▼
 GitHub Pages
```

---

# Repository Structure

```text
drought-briefing/

├── config/
│
├── data/
│   ├── raw/
│   └── processed/
│
├── scripts/
│
├── site/
│
├── tests/
│
├── docs/
│
└── .github/
    └── workflows/
```

---

# Configuration Layer

All operational configuration shall be stored in YAML.

```text
config/

  sources.yaml

  regions.yaml

  rules.yaml

  messages.yaml

  translations.yaml

  site.yaml
```

Configuration must be editable by non-programmers.

No drought thresholds shall be hardcoded in Python.

---

# Configuration Responsibilities

## sources.yaml

Defines all data sources.

Example:

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

Defines aggregation regions.

Example:

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

Example:

```yaml
vhi:

  normal:
    min: 40

  watch:
    min: 30
    max: 39

  warning:
    min: 20
    max: 29

  severe:
    max: 19
```

---

## messages.yaml

Contains multilingual drought messages.

Example:

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

```text
data/processed/

  national.json

  cantons/

      AG.json
      AI.json
      AR.json
      BE.json
      BL.json
      BS.json

  warning_regions/

      region_001.json
      region_002.json
```

---

# JSON Data Contract

All generated region files shall follow a common schema.

Example:

```json
{
  "region_id": "BE",
  "region_name": "Bern",

  "status": "warning",

  "indicators": {
    "vhi": 22,
    "precipitation": 35,
    "groundwater": 41
  },

  "messages": {
    "de": "Trockenheitssituation angespannt",
    "fr": "Situation de sécheresse tendue",
    "it": "Situazione di siccità tesa"
  },

  "updated_at": "2026-06-22T00:30:00Z"
}
```

This schema shall be considered stable.

Frontend components depend on it.

---

# Processing Layer

Location:

```text
scripts/
```

Modules:

```text
download.py

validate.py

aggregate.py

evaluate.py

generate_site.py
```

Each module shall have a single responsibility.

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

Verify downloaded datasets.

Checks:

* file exists
* schema validity
* geometry validity
* expected attributes

Failure:

Workflow stops.

---

# Aggregation Module

Purpose:

Generate regional statistics.

Input:

```text
data/raw/
```

Output:

```text
data/processed/
```

Aggregation logic shall remain equivalent to the current implementation.

---

# Evaluation Module

Purpose:

Apply drought rules.

Input:

```text
rules.yaml
```

Output:

Drought classifications.

No hardcoded thresholds allowed.

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

The frontend may:

* load JSON
* render pages
* switch languages
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

Objectives:

* responsive layout
* accessibility
* official visual identity
* multilingual navigation

Custom styling should be minimal.

---

# GitHub Actions Architecture

Workflow:

```text
.github/workflows/

  daily-update.yml
```

Execution:

1. Checkout repository
2. Install dependencies
3. Download datasets
4. Validate datasets
5. Aggregate indicators
6. Apply rules
7. Generate JSON
8. Generate website
9. Publish GitHub Pages

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

Required tests:

```text
test_download.py

test_validation.py

test_aggregation.py

test_rules.py

test_site_generation.py
```

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

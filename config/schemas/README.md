# config/schemas/

JSON Schema definitions used to validate the pipeline's processed output.
Both files already carry a `description` on every field — this README is
about how they fit into the pipeline, not what each field means.

| Schema | Validates |
|---|---|
| `region.json` | `data/processed/warning_regions/*.json` (one `RegionReport` per warning region) |
| `canton.json` | `data/processed/cantons/*.json` (one `CantonReport` per canton, embedding its regions) |

`scripts/validate.py` loads both schemas and validates every generated file
against them. In both GitHub Actions workflows, this runs after
`scripts/aggregate.py` and before `scripts/generate_site.py` — if validation
fails, the site is not (re)generated from bad data.

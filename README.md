# Drought Briefing BETA 

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/swisstopo/topo-drought-briefing) [![Daily Drought Briefing Update](https://github.com/swisstopo/topo-drought-briefing/actions/workflows/daily-update.yml/badge.svg)](https://github.com/swisstopo/topo-drought-briefing/actions/workflows/daily-update.yml) [![GitHub commit](https://img.shields.io/github/last-commit/swisstopo/topo-drought-briefing)](https://github.com/swisstopo/topo-drought-briefing/commits/main)

Automated drought situation reports for Swiss authorities.

The system downloads federal open data every day, applies drought rules, and publishes a static website.
No server is needed. Everything runs on GitHub.

Live site: [swisstopo.github.io/topo-drought-briefing](https://swisstopo.github.io/topo-drought-briefing): published via GitHub Pages (see Settings > Pages in this repository).

---

## How the system works

Every day, GitHub Actions runs a pipeline:

1. Downloads drought data from federal open data portals (BAFU, SwissEO, swisstopo).
2. Calculates indicators per warning region and per canton.
3. Applies drought rules from a YAML file to produce warning levels and text.
4. Generates a static website with one page per canton.
5. Publishes the website to GitHub Pages.

All drought thresholds, classification rules, and bulletin texts live in YAML files under `data/ruleset/` and `config/`.
No Python knowledge is needed to update them.

---

## Cookbook

### How to change a drought threshold (US-01)

Domain experts can change the thresholds that determine warning levels without touching any code.

1. Open the file `data/ruleset/canton-bulletin.yaml` in GitHub (click the file, then the pencil icon).
2. Find the section you want to change. Example: the CDI threshold for warning level 3.
3. Edit the number directly.
4. Scroll down, write a short description of your change (e.g. "Adjust CDI threshold for level 3"), and click "Commit changes".
5. GitHub Actions will run within a few minutes and publish the updated site.

Tip: Each threshold in the YAML file has a comment explaining what it controls. Read the comment before changing the value.

---

### How to update bulletin texts and translations (US-02)

All texts shown on the website are stored in YAML files. You do not need to edit HTML or JavaScript.

**To change recommendation texts (German and French):**

1. Open `data/ruleset/canton-bulletin.yaml`.
2. Find the `recommendations` section for the warning level you want to update.
3. Edit the German (`de`) and French (`fr`) texts.
4. Commit your change. The site will update automatically.

**To change UI labels (buttons, table headers, etc.):**

1. Open `src/i18n/strings.py`.
2. Find the label you want to change in the `"de"` block (German) and the `"fr"` block (French).
3. Edit the text string.
4. Commit your change.

Note: If you are not sure which key controls which label, look at the label on the published site, then search for that text in the file using GitHub's search (Ctrl+F in the browser).

---

### How to manage daily automation (US-03 — for administrators)

The daily pipeline runs automatically using GitHub Actions.

**To check whether the latest run succeeded:**

1. Click the "Actions" tab in this repository.
2. The most recent workflow run is shown at the top.
3. A green check mark means success. A red cross means it failed.
4. Click the run to see the log and find the error.

**To run the pipeline manually (for example, after a configuration change):**

1. Click the "Actions" tab.
2. Select the workflow named "Daily update" (or similar).
3. Click "Run workflow" on the right side, then confirm.

**To change the schedule (for example, to run at a different time):**

1. Open `.github/workflows/daily.yml` (or the workflow file listed under Actions).
2. Find the `schedule:` section and edit the cron expression.
3. Commit your change.

**If the pipeline fails because data is unavailable:**

The pipeline falls back to fixture data automatically. The published site will show a data quality warning, but it will not go offline. Check the Actions log for details.

---

### How to manage "Weiterführende Links" per canton (US-05)

Every canton page has a "Weiterführende Links / Liens complémentaires" section. The links are defined in `data/ruleset/canton-bulletin.yaml` under the `weiterfuehrende_links` key.

**To add a link that appears on every canton page:**

```yaml
weiterfuehrende_links:
  - label:
      de: "Link-Titel auf Deutsch"
      fr: "Titre du lien en français"
    url: "https://example.com/page"
```

**To add a link that appears only for a specific canton** (using the BFS canton number):

```yaml
weiterfuehrende_links:
  - label:
      de: "Grundwasserdaten Kanton Bern"
      fr: "Données des eaux souterraines canton de Berne"
    url:
      2: "https://www.bvd.be.ch/..."   # 2 = Bern
```

The BFS numbers for all 26 cantons are listed in `config/settings.py` under `CANTON_ABBREV`.

Links where the URL is not defined for the current canton are automatically hidden for that canton.

### You need other Changes to make?

Then type your question [![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/swisstopo/topo-drought-briefing)

---

### How to access the drought briefings as a public user (US-04)

The website is accessible at the GitHub Pages URL for this repository.

1. Go to the repository's Settings > Pages to find the published URL.
2. Open the URL in any web browser. No login is required.
3. Select a canton from the overview page.
4. Switch between German and French using the DE / FR buttons in the top right corner.
5. To save a PDF, use your browser's print function (Ctrl+P or Cmd+P) and choose "Save as PDF".
6. To share a link in a specific language, click "Link kopieren" / "Copier le lien" in the header. The link includes the language parameter.

---

## Integration branch (INT) and preview deployment

Changes should **not** go directly to `main`. Use the `INT` branch as a shared staging area:

```
your-branch  →  INT  →  main
   (PR)         (PR, squash merge)
```

### Workflow

1. Create a branch from `INT` (not from `main`) and make your changes.
2. Open a pull request targeting `INT`.
3. Every push to `INT` automatically deploys a preview to:
   **`https://swisstopo.github.io/topo-drought-briefing/int/`**
4. Review the preview. If the output looks correct, open a pull request from `INT` → `main` and merge it with **squash merge** to keep the main history clean.

### Why squash merge?

During integration, `INT` may accumulate many small commits ("fix typo", "try again", etc.). Squash merge collapses them into one clean commit on `main`, so the production history stays readable.

### Who can do what

| Role | What you can do |
|---|---|
| Maintainer (all team members) | push branches, open PRs, merge PRs into INT |
| Administrator (Joan, David) | merge INT → main, change repo settings |

### Preview URL vs. production URL

| Branch | URL |
|---|---|
| `main` | `https://swisstopo.github.io/topo-drought-briefing/` |
| `INT` | `https://swisstopo.github.io/topo-drought-briefing/int/` |

Both are served from the same repository — no second repo needed.

> **One-time setup (administrators only):** After the first workflow run, go to  
> *Settings → Pages → Source* and set it to **"Deploy from a branch: `gh-pages`"**.  
> The `gh-pages` branch is created automatically on first deploy.

---

## Repository structure

```
config/
  settings.py         — canton and region definitions, colour codes
  sources.yaml        — list of data source URLs shown on the website

data/
  ruleset/
    canton-bulletin.yaml   — drought rules, thresholds, and bulletin texts

scripts/
  aggregate.py        — downloads data and computes canton reports
  generate_site.py    — builds the static HTML website from JSON outputs

src/
  aggregation/        — indicator calculation per region and canton
  briefing/           — applies YAML rules to produce structured briefing documents
  data/               — data clients (STAC, warnkarte, VHI, hydro)
  i18n/               — multilingual UI strings

tests/                — automated tests (run via GitHub Actions or locally)

.github/
  workflows/          — GitHub Actions pipeline definitions
```

---

## Running locally

Requirements: Python 3.11 or later, and the `uv` package manager.

```
uv sync
uv run pytest tests/ -v
uv run python scripts/download.py
uv run python scripts/aggregate.py
uv run python scripts/generate_site.py
```

The generated site is written to `site/`. Open `site/index.html` in a browser to preview it.

---

## Data sources

| Source | What is used |
|---|---|
| BGDI STAC `ch.bafu.trockenheitsdaten-numerisch` | CDI, SPI, soil moisture, precipitation, hydro indices per warning region |
| geo.admin.ch REST API `ch.bafu.trockenheitswarnkarte` | BAFU warning level per region |
| SwissEO VHI endpoint | Vegetation Health Index per region |
| hydrodaten.admin.ch | Discharge per hydro station with low-flow thresholds |

---

## Contributing

Contributions are welcome.

For questions about drought methodology, contact BAFU.

For technical issues, open a GitHub issue.

To propose a change to thresholds or texts: create a branch, edit the relevant YAML file, and open a pull request. An administrator will review and merge it.

---

## Team

Fabia Huesler, Christopher Boodnee, Lea Stauber, Benjamin Meyer, Luca Huesler, Simon Jaun, Chantal Camenisch, David Oesch, Joan Sturm, 

Built at GovTech Hackathon 2026 in partnership with swisstopo, BAFU, and MeteoSwiss.

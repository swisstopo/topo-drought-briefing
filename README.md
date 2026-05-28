# Drought-Briefing

## Next Steps

### UI/UX

- **Handlungsoptionen:** Use the current drought platform wording depending on the Gefahrenstufe. The maximum level is taken per Canton.
-  **Subregions section – recommendation based:**
  - [ ] *Allgemeine Lage:* Define the template text per Gefahrenstufe.

### Ruleset

-  **Terminology-based ruleset:** Combine indicator terminology with threshold values.
- [ ] **Define thresholds** following the approach used in *Beurteilung der aktuellen Lage*, provide a yaml e.g.:
  > Im Juni sind nur 25 Prozent und im Juli bisher nur 10 Prozent der normal üblichen Niederschlagsmengen gefallen. Die jährlichen Niederschlagssummen liegen bis 220 mm unter dem saisonal üblichen Mittel. Der Pegelstand des Bodensees liegt 80 cm und der Pegelstand des Walensees 95 cm unter dem saisonal üblichen Mittel und damit im Bereich des saisonalen Minimums.

### Data Ingest / Framework

- **Framework decision:** Use Streamlit as the application framework.
- **Ruleset configuration:** Define and maintain thresholds in a YAML file.

# tests/test_renderer.py
from pathlib import Path

from src.briefing.renderer import load_ruleset, _handlebars_to_jinja2
from src.briefing.schemas import RulesetSchema


RULESET_PATH = Path(__file__).resolve().parent.parent / "data/ruleset/canton-bulletin.yaml"


def test_load_ruleset_returns_schema_instance():
    ruleset = load_ruleset(RULESET_PATH)
    assert isinstance(ruleset, RulesetSchema)
    assert ruleset.id == "canton-bulletin"
    assert "warnkarte" in ruleset.data_sources
    assert "niederschlag" in ruleset.nomenclature.indicators


def test_handlebars_each_block_converted():
    src = "{{#each items}}- {{ this.name }}\n{{/each}}"
    out = _handlebars_to_jinja2(src)
    assert "{% for item in items %}" in out
    assert "{{ item.name }}" in out
    assert "{% endfor %}" in out


def test_handlebars_no_each_unchanged():
    src = "Hello {{ canton.canton_name_de }}."
    assert _handlebars_to_jinja2(src) == src


from datetime import datetime

from src.aggregation.canton import compute_canton_report
from src.briefing.renderer import render_briefing
from src.data.stac_client import load as load_data
from src.models import WarnkarteEntry


def test_render_briefing_de_section_keys():
    bundle = load_data()
    warnkarte = {
        rid: WarnkarteEntry(
            drought_region_id=rid,
            warnlevel=2,
            info_de="Mässige Gefahr",
            info_fr="Danger limité",
            info_it="-",
            valid_from=datetime(2026, 5, 28),
        )
        for rid in [33, 34, 35, 37, 38, 41]
    }
    canton = compute_canton_report(canton_id=2, bundle=bundle, warnkarte_data=warnkarte)
    ruleset = load_ruleset(RULESET_PATH)

    doc = render_briefing(canton, ruleset, locale="de")

    assert set(doc.sections.keys()) >= {"allgemeine-lage", "handlungsoptionen", "regionen"}
    assert "Bern" in doc.sections["allgemeine-lage"]
    assert "Mässige Gefahr" in doc.sections["allgemeine-lage"]
    # Maps spec preserved
    assert len(doc.lead_maps) == 2
    assert {m.id for m in doc.lead_maps} == {"cdi_current", "cdi_forecast_week2"}


def test_render_briefing_fr_uses_french_strings():
    bundle = load_data()
    warnkarte = {
        rid: WarnkarteEntry(
            drought_region_id=rid,
            warnlevel=2,
            info_de="Mässige Gefahr",
            info_fr="Danger limité",
            info_it="-",
            valid_from=datetime(2026, 5, 28),
        )
        for rid in [33, 34, 35, 37, 38, 41]
    }
    canton = compute_canton_report(canton_id=2, bundle=bundle, warnkarte_data=warnkarte)
    ruleset = load_ruleset(RULESET_PATH)

    doc = render_briefing(canton, ruleset, locale="fr")

    assert "Berne" in doc.sections["allgemeine-lage"]
    assert "Danger limité" in doc.sections["allgemeine-lage"]

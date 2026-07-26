# tests/test_renderer.py
from datetime import datetime
from pathlib import Path

import pytest

from src.aggregation.canton import compute_canton_report
from src.briefing.renderer import _handlebars_to_jinja2, load_ruleset, render_briefing
from src.briefing.schemas import RulesetSchema
from src.data.stac_client import load as load_data
from src.models import WarnkarteEntry


RULESET_PATH = Path(__file__).resolve().parent.parent / "data/ruleset/canton-bulletin.yaml"


def test_load_ruleset_returns_schema_instance():
    ruleset = load_ruleset(RULESET_PATH)
    assert isinstance(ruleset, RulesetSchema)
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


def test_handlebars_if_block_converted():
    src = "{{#if x.n}}has{{/if}}"
    out = _handlebars_to_jinja2(src)
    assert "{% if x.n %}" in out
    assert "{% endif %}" in out


def test_plural_helper():
    from src.briefing.renderer import _plural
    assert _plural(1, "Station", "Stationen") == "Station"
    assert _plural(0, "Station", "Stationen") == "Stationen"
    assert _plural(2, "Station", "Stationen") == "Stationen"


def test_deficit_range_helper_via_ruleset():
    from src.briefing.renderer import _make_deficit_range_resolver
    rs = load_ruleset(RULESET_PATH)
    fn = _make_deficit_range_resolver(rs.nomenclature.indicators, "de")
    assert fn(None, None, "cdi") == ""
    # single (min == max) uses the `single` template
    assert "trocken" in fn(3, 3, "cdi")
    # range uses adjectives + range template
    out = fn(2, 4, "niederschlag")
    assert "bis" in out and "Niederschlagsdefizit" in out


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def warnkarte_data():
    return {
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


@pytest.fixture
def _bern_canton(warnkarte_data):
    bundle = load_data()
    canton = compute_canton_report(canton_id=2, bundle=bundle, warnkarte_data=warnkarte_data)
    ruleset = load_ruleset(RULESET_PATH)
    return canton, ruleset


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

def test_render_briefing_de_section_keys(_bern_canton):
    canton, ruleset = _bern_canton
    doc = render_briefing(canton, ruleset, locale="de")

    assert set(doc.sections.keys()) >= {"allgemeine-lage", "handlungsoptionen", "regionen"}
    assert "Bern" in doc.sections["allgemeine-lage"]
    assert "Bodenfeuchte" in doc.sections["allgemeine-lage"]
    # Maps spec preserved
    assert len(doc.lead_maps) == 2
    assert {m.id for m in doc.lead_maps} == {"cdi_current", "cdi_forecast_week2"}


def test_render_briefing_fr_uses_french_strings(_bern_canton):
    canton, ruleset = _bern_canton
    doc = render_briefing(canton, ruleset, locale="fr")

    assert "Berne" in doc.sections["allgemeine-lage"]
    assert "humidité du sol" in doc.sections["allgemeine-lage"]
    assert doc.locale == "fr"
    assert "Mässige" not in doc.lead_headline  # FR headline shouldn't contain German
    assert "Danger limité" in doc.lead_headline or doc.lead_headline != ""
    assert doc.lead_meta != ""


def test_render_exposes_banner_and_links(_bern_canton):
    canton, ruleset = _bern_canton
    doc = render_briefing(canton, ruleset, locale="de")
    assert any(b["label"] == "Trockenheitsportal" for b in doc.banner)
    assert any("VHI" in l["label"] for l in doc.weiterfuehrende_links)
    # canton-keyed url resolved to a plain string for canton 2 (Bern)
    gw = next(l for l in doc.weiterfuehrende_links if "Grundwasser" in l["label"])
    assert gw["url"].startswith("https://www.bvd.be.ch")


def test_render_briefing_handlungsoptionen_falls_back_for_level_3():
    bundle = load_data()
    warnkarte = {
        rid: WarnkarteEntry(
            drought_region_id=rid,
            warnlevel=(3 if rid == 34 else 2),  # 34 drives the max to 3
            info_de="Erhebliche Gefahr",
            info_fr="Danger marqué",
            info_it="-",
            valid_from=datetime(2026, 5, 28),
        )
        for rid in [33, 34, 35, 37, 38, 41]
    }
    canton = compute_canton_report(canton_id=2, bundle=bundle, warnkarte_data=warnkarte)
    ruleset = load_ruleset(RULESET_PATH)
    doc = render_briefing(canton, ruleset, locale="de")
    # Level 3 falls back to level 2 — must render the level-2 bullets, not crash
    assert doc.sections["handlungsoptionen"].strip() != ""
    assert "www.trockenheit.ch" in doc.sections["handlungsoptionen"]


def test_render_briefing_handlungsoptionen_falls_back_for_level_5():
    bundle = load_data()
    warnkarte = {
        rid: WarnkarteEntry(
            drought_region_id=rid,
            warnlevel=(5 if rid == 34 else 1),
            info_de="Sehr grosse Gefahr",
            info_fr="Danger très fort",
            info_it="-",
            valid_from=datetime(2026, 5, 28),
        )
        for rid in [33, 34, 35, 37, 38, 41]
    }
    canton = compute_canton_report(canton_id=2, bundle=bundle, warnkarte_data=warnkarte)
    ruleset = load_ruleset(RULESET_PATH)
    doc = render_briefing(canton, ruleset, locale="de")
    # Level 5 falls back to level 4 — must mention waldbrand or wasserverbote
    assert doc.sections["handlungsoptionen"].strip() != ""
    assert "Waldbrand" in doc.sections["handlungsoptionen"] or "Wasser" in doc.sections["handlungsoptionen"]

# src/briefing/renderer.py
from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

import yaml
from jinja2 import BaseLoader, Environment, StrictUndefined

from src.briefing.schemas import RulesetSchema
from src.models import BriefingDocument, CantonReport, MapSpec

_EACH_OPEN = re.compile(r"\{\{#each\s+([^\s}]+)\s*\}\}")
_EACH_CLOSE = re.compile(r"\{\{/each\}\}")
_IF_OPEN = re.compile(r"\{\{#if\s+(.+?)\s*\}\}")
_IF_CLOSE = re.compile(r"\{\{/if\}\}")
_THIS_FIELD = re.compile(r"\{\{\s*this\.([^\s}]+)\s*\}\}")
_THIS_BARE = re.compile(r"\{\{\s*this\s*\}\}")
# Also replaces `this.field` inside other expressions (e.g. subscripts like [this.field])
_THIS_INPLACE = re.compile(r"\bthis\.")


def _handlebars_to_jinja2(src: str) -> str:
    src = _EACH_OPEN.sub(r"{% for item in \1 %}", src)
    src = _EACH_CLOSE.sub("{% endfor %}", src)
    src = _IF_OPEN.sub(r"{% if \1 %}", src)
    src = _IF_CLOSE.sub("{% endif %}", src)
    src = _THIS_FIELD.sub(r"{{ item.\1 }}", src)
    src = _THIS_BARE.sub(r"{{ item }}", src)
    # Replace any remaining `this.` references inside Jinja2 expressions
    src = _THIS_INPLACE.sub("item.", src)
    return src


def load_ruleset(path: Path) -> RulesetSchema:
    """Load YAML, validate via Pydantic, return the schema object."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))

    if not isinstance(raw, dict):
        raise ValueError(f"Expected a YAML mapping at the top level, got {type(raw).__name__}")

    # NomenclatureSpec wraps the raw mapping under an `indicators` key for type clarity.
    if "nomenclature" in raw and "indicators" not in raw["nomenclature"]:
        raw["nomenclature"] = {"indicators": raw["nomenclature"]}

    return RulesetSchema.model_validate(raw)


def _format_date(value: datetime | str, pattern: str) -> str:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    mapping = {
        "DD.MM.YYYY": "%d.%m.%Y",
        "YYYY-MM-DD": "%Y-%m-%d",
    }
    if pattern not in mapping:
        raise ValueError(f"Unsupported date pattern: {pattern!r}. Known: {sorted(mapping)}")
    return value.strftime(mapping[pattern])


def _resolve_handlungsempfehlungen_fallback(spec):
    """
    Return a copy of the by_gefahrenstufe dict where fallback levels are replaced
    by the empfehlungen of their target level (chain-resolved).
    """
    resolved = {}
    for level, entry in spec.by_gefahrenstufe.items():
        current = entry
        # Follow fallback chain until we find one with empfehlungen
        seen = set()
        while current.empfehlungen is None and current.fallback is not None:
            if current.fallback in seen:
                raise ValueError(f"Cyclic fallback chain at level {level}")
            seen.add(current.fallback)
            current = spec.by_gefahrenstufe[current.fallback]
        if current.empfehlungen is None:
            raise ValueError(f"Level {level} has no empfehlungen and no resolvable fallback")
        resolved[level] = current
    return resolved


def _pick_template(template, locale: str, section_id: str) -> str:
    if isinstance(template, str):
        return template
    if locale in template:
        return template[locale]
    if "de" in template:
        logger.warning(
            "Section %s missing locale=%r; falling back to 'de'", section_id, locale
        )
        return template["de"]
    raise ValueError(f"Section {section_id} has no usable template for locale={locale!r}")


def _plural(n: int, singular: str, plural: str) -> str:
    """Return `singular` when n == 1, else `plural`. Used for noun/verb agreement."""
    return singular if n == 1 else plural


def _make_region_phrase(locale: str):
    """
    Return a callable region_phrase(n, total, noun_de, noun_fr) that converts a
    raw count into natural language:
      all   → "alle Regionen" / "toutes les régions"
      most  → "die Mehrzahl der …" / "la majorité des …"
      half  → "die Hälfte der …" / "la moitié des …"
      few   → "wenige …" / "quelques …"
      one   → "1 von {total} …" / "1 … sur {total}"
      none  → "keine …" / "aucune …"
    """
    def region_phrase(
        n: int,
        total: int,
        noun_de: str = "Regionen",
        noun_fr: str = "régions",
    ) -> str:
        n = int(n)
        total = int(total)
        noun = noun_de if locale == "de" else noun_fr
        if total == 0 or n == 0:
            return ("keine " + noun_de) if locale == "de" else ("aucune " + noun)
        if n == total:
            return ("alle " + noun) if locale == "de" else ("toutes les " + noun)
        if n * 2 > total:          # strict majority
            return ("die Mehrzahl der " + noun) if locale == "de" else ("la majorité des " + noun)
        if n * 2 == total:         # exactly half
            return ("die Hälfte der " + noun) if locale == "de" else ("la moitié des " + noun)
        if n > 1:                  # small minority
            return ("wenige " + noun) if locale == "de" else ("quelques " + noun)
        # n == 1
        noun_fr_sg = noun_fr.rstrip("s") or noun_fr
        return f"1 von {total} {noun_de}" if locale == "de" else f"1 {noun_fr_sg} sur {total}"
    return region_phrase


def _make_pct_stations(locale: str):
    """
    Return a callable pct_stations(pct, noun_de, noun_fr) that converts a
    station percentage into natural language:
      100 % → "alle Abflussmessstationen" / "toutes les stations de mesure du débit"
        0 % → "keine der …"              / "aucune des …"
      other → "X % der …"               / "X % des …"
    """
    def pct_stations(
        pct: float,
        noun_de: str = "Abflussmessstationen",
        noun_fr: str = "stations de mesure du débit",
    ) -> str:
        pct_i = int(round(float(pct)))
        noun = noun_de if locale == "de" else noun_fr
        if pct_i >= 100:
            return ("alle " + noun) if locale == "de" else ("toutes les " + noun)
        if pct_i == 0:
            return ("keine der " + noun) if locale == "de" else ("aucune des " + noun)
        return f"{pct_i}\xa0% der {noun}" if locale == "de" else f"{pct_i}\xa0% des {noun}"
    return pct_stations


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


def _make_trend_resolver(trend_spec, locale: str):
    def trend(delta, key):
        spec = trend_spec[key]
        if abs(delta) <= spec.stable_tolerance:
            return spec.stable[locale]
        return (spec.increase if delta > 0 else spec.decrease)[locale]
    return trend


def render_briefing(
    canton: CantonReport,
    ruleset: RulesetSchema,
    locale: Literal["de", "fr"] = "de",
) -> BriefingDocument:
    env = Environment(
        loader=BaseLoader(),
        undefined=StrictUndefined,
        autoescape=False,
    )
    env.filters["format_date"] = _format_date
    env.filters["ucfirst"] = lambda s: (s[0].upper() + s[1:]) if s else s
    env.globals["format_date"] = _format_date
    env.globals["trend"] = _make_trend_resolver(ruleset.trend, locale)
    env.globals["deficit_range"] = _make_deficit_range_resolver(
        ruleset.nomenclature.indicators, locale
    )
    env.globals["plural"] = _plural
    env.globals["region_phrase"] = _make_region_phrase(locale)
    env.globals["pct_stations"] = _make_pct_stations(locale)
    env.globals["nomenclature"] = ruleset.nomenclature.indicators
    # Resolve fallback chains so the template never sees None.empfehlungen
    resolved_he = type(ruleset.handlungsempfehlungen).model_construct(
        source_ref=ruleset.handlungsempfehlungen.source_ref,
        by_gefahrenstufe=_resolve_handlungsempfehlungen_fallback(ruleset.handlungsempfehlungen),
    )
    env.globals["handlungsempfehlungen"] = resolved_he
    env.globals["canton"] = canton
    # Expose data_sources and references as lists so Handlebars-style each loops work
    env.globals["data_sources"] = list(ruleset.data_sources.values())
    env.globals["references"] = list(ruleset.references.values())

    sections: dict[str, str] = {}
    for sec in ruleset.sections:
        tmpl_src = _pick_template(sec.template, locale, sec.id)
        tmpl_src = _handlebars_to_jinja2(tmpl_src)
        sections[sec.id] = env.from_string(tmpl_src).render().strip()

    # Lead
    lead = ruleset.lead.warnstufe
    headline = env.from_string(_handlebars_to_jinja2(lead.headline[locale])).render()
    meta = env.from_string(_handlebars_to_jinja2(lead.meta[locale])).render()
    lead_maps = [
        MapSpec(
            id=m.id,
            title_de=m.title.get("de", ""),
            title_fr=m.title.get("fr", ""),
            source=m.source,
            style=m.style,
        )
        for m in lead.maps
    ]

    banner = [
        {"label": b.label.get(locale, b.label.get("de", "")), "url": b.url}
        for b in (ruleset.banner or [])
    ]
    links = []
    for link in (ruleset.weiterfuehrende_links or []):
        url = link.url
        if isinstance(url, dict):
            url = url.get(canton.canton_id)
        if url is None:
            continue  # link not available for this canton
        links.append({"label": link.label.get(locale, link.label.get("de", "")), "url": url})

    return BriefingDocument(
        sections=sections,
        report=canton,
        locale=locale,
        generated_at=datetime.now(),
        lead_maps=lead_maps,
        lead_headline=headline,
        lead_meta=meta,
        banner=banner,
        weiterfuehrende_links=links,
    )

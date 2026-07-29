# src/briefing/schemas.py
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class NomenclatureIndicatorSpec(BaseModel):
    field: str | None = None
    fields: list[str] | None = None
    scope: str | None = None
    note: str | None = None
    adjective: dict[int, dict[str, str]] | None = None
    noun: dict[int, dict[str, str]] | None = None
    range: dict[str, str] | None = None
    single: dict[str, str] | None = None
    model_config = ConfigDict(extra="forbid")


class NomenclatureSpec(BaseModel):
    indicators: dict[str, NomenclatureIndicatorSpec]
    model_config = ConfigDict(extra="forbid")


class TrendSpec(BaseModel):
    rule: str
    stable_tolerance: float
    increase: dict[str, str]
    decrease: dict[str, str]
    stable: dict[str, str]
    model_config = ConfigDict(extra="forbid")


class HandlungsempfehlungenLevel(BaseModel):
    empfehlungen: dict[str, list[str]] | None = None
    fallback: int | None = None
    model_config = ConfigDict(extra="forbid")


class HandlungsempfehlungenSpec(BaseModel):
    source_ref: str
    by_gefahrenstufe: dict[int, HandlungsempfehlungenLevel]
    model_config = ConfigDict(extra="forbid")


class BannerLinkSpec(BaseModel):
    label: dict[str, str]
    url: str
    model_config = ConfigDict(extra="forbid")


class WeiterfuehrendeLinkSpec(BaseModel):
    label: dict[str, str]
    url: str | dict[int, str]   # plain url, or canton-id-keyed url map
    model_config = ConfigDict(extra="forbid")


class MapSpecSchema(BaseModel):
    id: str
    title: dict[str, str]
    source: str
    style: str
    model_config = ConfigDict(extra="forbid")


class LeadWarnstufe(BaseModel):
    headline: dict[str, str]
    meta: dict[str, str]
    farben_pro_stufe: dict[int, dict[str, str]]
    maps: list[MapSpecSchema]
    placeholders: list[dict[str, Any]] | None = None
    model_config = ConfigDict(extra="forbid")


class LeadSpec(BaseModel):
    warnstufe: LeadWarnstufe
    model_config = ConfigDict(extra="forbid")


class SectionSpec(BaseModel):
    id: str
    title: dict[str, str]
    locale: str | None = None
    # str = single-locale (use only when locale is set on the section); dict[str, str] = multilingual
    template: dict[str, str] | str
    placeholders: list[dict[str, Any]] | None = None
    notes: list[str] | None = None
    model_config = ConfigDict(extra="forbid")


class RulesetSchema(BaseModel):
    nomenclature: NomenclatureSpec
    trend: dict[str, TrendSpec]
    handlungsempfehlungen: HandlungsempfehlungenSpec
    lead: LeadSpec
    sections: list[SectionSpec]
    banner: list[BannerLinkSpec] | None = None
    weiterfuehrende_links: list[WeiterfuehrendeLinkSpec] | None = None
    model_config = ConfigDict(extra="forbid")

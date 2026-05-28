# app.py
"""One Click Drought Briefing — Streamlit entry point for Kanton Bern."""
from __future__ import annotations

from pathlib import Path
import streamlit as st

from config.settings import CANTON_NAMES, CANTON_TO_REGIONS
from src.aggregation.canton import compute_canton_report
from src.briefing.renderer import load_ruleset, render_briefing
from src.data.stac_client import load as load_data
from src.data.warnkarte_client import fetch_for_regions
from src.export.report import to_html
from src.i18n.strings import t
from src.models import DataBundle
from src.viz.maps import build_canton_map

st.set_page_config(
    page_title="Trockenheitsbriefing / Bulletin sécheresse",
    page_icon="💧",
    layout="wide",
)


@st.cache_data(ttl=3600, show_spinner="Daten werden geladen…")
def _load_bundle() -> DataBundle:
    return load_data()


@st.cache_data(ttl=3600, show_spinner="Warnstufen werden geladen…")
def _load_warnkarte(region_ids: tuple[int, ...]):
    return fetch_for_regions(list(region_ids))


@st.cache_resource
def _ruleset():
    return load_ruleset(Path("data/ruleset/canton-bulletin.yaml"))


def _warnstufe_palette(level: int) -> tuple[str, str]:
    """Return (background, text) colour pair for a warning level (1–5)."""
    palette = {
        1: ("#6bbd50", "#ffffff"),
        2: ("#f7e84c", "#1a1a1a"),
        3: ("#ff8c00", "#ffffff"),
        4: ("#e02020", "#ffffff"),
        5: ("#8b0000", "#ffffff"),
    }
    return palette.get(level, ("#cccccc", "#1a1a1a"))


# ── Sidebar ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title(t("sidebar_title", lang))
    st.caption(t("sidebar_caption", lang))
    st.divider()

    lang = st.radio(
        "Sprache / Langue",
        options=["de", "fr"],
        format_func=lambda l: "Deutsch" if l == "de" else "Français",
        horizontal=True,
        index=0,
    )

    canton_options = sorted(CANTON_TO_REGIONS.keys())
    selected_canton_id = st.selectbox(
        t("canton_label", lang),
        options=canton_options,
        format_func=lambda cid: CANTON_NAMES[cid].get(lang, CANTON_NAMES[cid]["de"]),
        index=0,
    )

    st.divider()

    bundle = _load_bundle()
    st.caption(f"{t('data_status', lang)}: {bundle.data_timestamp.strftime('%d.%m.%Y')}")
    st.caption(f"{t('source', lang)}: {bundle.source}")

    st.divider()
    st.subheader(t("export_header", lang))
    export_placeholder = st.empty()


# ── Pipeline ───────────────────────────────────────────────────────────────
region_ids = tuple(sorted(CANTON_TO_REGIONS[selected_canton_id]))
warnkarte = _load_warnkarte(region_ids)
canton = compute_canton_report(
    canton_id=selected_canton_id,
    bundle=bundle,
    warnkarte_data=warnkarte,
)
rs = _ruleset()
doc = render_briefing(canton, rs, locale=lang)

# ── Header / Lead box ──────────────────────────────────────────────────────
canton_label = canton.canton_name_de if lang == "de" else canton.canton_name_fr
st.title(f"{t('export_doc_title', lang)} {canton_label}")
bg, text_colour = _warnstufe_palette(canton.max_warnlevel)
st.markdown(
    f"""<div style="background:{bg};border-radius:8px;padding:18px;color:{text_colour};">
    <div style="font-size:11px;opacity:.85;">{t("current_warnlevel", lang)}</div>
    <div style="font-size:28px;font-weight:700;">{doc.lead_headline}</div>
    <div style="font-size:12px;opacity:.85;">{doc.lead_meta}</div>
    </div>""",
    unsafe_allow_html=True,
)

st.divider()

# ── Two side-by-side maps ──────────────────────────────────────────────────
map_cols = st.columns(2)
for col, map_spec in zip(map_cols, doc.lead_maps):
    with col:
        st.subheader(map_spec.title_de if lang == "de" else map_spec.title_fr)
        m = build_canton_map(canton, map_spec)
        st.components.v1.html(m._repr_html_(), height=300)

st.divider()

# ── Text sections ──────────────────────────────────────────────────────────
for sec in rs.sections:
    title = sec.title.get(lang, sec.title.get("de", sec.id))
    st.markdown(f"## {title}")
    st.markdown(doc.sections[sec.id])
    st.write("")

# ── Quality panel ──────────────────────────────────────────────────────────
with st.expander(t("quality_expander", lang)):
    q = canton.quality
    q_colour = {"ok": "🟢", "warning": "🟡", "error": "🔴"}.get(q.overall, "⚪")
    st.markdown(
        f"{q_colour} **{q.overall.upper()}** — "
        f"{t('data_age', lang)}: {q.data_age_days} {t('days', lang)} — "
        f"{t('coverage', lang)}: {q.coverage_pct:.0%}"
    )
    if q.missing_columns:
        st.warning(f"{t('quality_missing_cols', lang)}: {', '.join(q.missing_columns)}")
    if q.outlier_flags:
        st.warning(f"{t('quality_outliers', lang)}: {', '.join(q.outlier_flags)}")
    # Per-region drill-down
    for r in canton.regions:
        st.caption(
            f"R{r.region_id} ({r.region_name_de}): "
            f"{r.quality.overall} — {t('coverage', lang)} {r.quality.coverage_pct:.0%}"
        )

# ── Export buttons ─────────────────────────────────────────────────────────
with export_placeholder:
    html_str = to_html(doc, canton, rs)
    st.download_button(
        label=t("btn_html", lang),
        data=html_str.encode("utf-8"),
        file_name=f"trockenheit_{canton.data_timestamp.strftime('%Y%m%d')}.html",
        mime="text/html",
    )

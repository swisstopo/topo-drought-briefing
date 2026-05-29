# app.py
"""One Click Drought Briefing — Streamlit entry point for Kanton Bern."""
from __future__ import annotations

import logging
import math
import re
from pathlib import Path
import streamlit as st

from config.settings import CANTON_NAMES, CANTON_TO_REGIONS, CDI_COLOURS
from src.aggregation.canton import compute_canton_report
from src.briefing.renderer import load_ruleset, render_briefing
from src.data.stac_client import load as load_data
from src.data.warnkarte_client import fetch_for_regions
from src.export.report import to_html
from src.i18n.strings import get_cdi_labels, get_region_names, t
from src.models import DataBundle
from src.viz.charts import build_timeseries
from src.viz.maps import build_canton_map

st.set_page_config(
    page_title="Trockenheitsbriefing / Bulletin sécheresse",
    page_icon="💧",
    layout="wide",
)

# Initialize session state for expert notes
if "expert_notes" not in st.session_state:
    st.session_state.expert_notes = {}

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

DROUGHT_LEGEND = {
    "de": ["Nicht trocken", "Leicht trocken", "Trocken", "Sehr trocken", "Extrem trocken"],
    "fr": ["Pas sec", "Légèrement sec", "Sec", "Très sec", "Extrêmement sec"],
}
DROUGHT_COLOURS = ["#97E8CB", "#F9E5AE", "#F1B981", "#D18C47", "#8A5A42"]

# ── Sidebar ────────────────────────────────────────────────────────────────
with st.sidebar:
    lang = st.radio(
        "Sprache / Langue",
        options=["de", "fr"],
        format_func=lambda l: "Deutsch" if l == "de" else "Français",
        horizontal=True,
        index=0,
        key="lang_selector"
    )

    st.title(t("sidebar_title", lang))
    st.caption(t("sidebar_caption", lang))
    st.divider()

    canton_options = sorted(CANTON_TO_REGIONS.keys())
    selected_canton_id = st.selectbox(
        t("canton_label", lang),
        options=canton_options,
        format_func=lambda cid: CANTON_NAMES[cid].get(lang, CANTON_NAMES[cid]["de"]),
        index=0,
        key="canton_selector"
    )
    
    st.divider()
    
    view_tab = st.radio(
        "Navigation",
        options=["canton", "regions"],
        format_func=lambda x: t(f"tab_{x}", lang),
        label_visibility="collapsed",
        key="view_tab_selector"
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

canton_label = canton.canton_name_de if lang == "de" else canton.canton_name_fr


# ── Tab 1: Allgemeine Lage (Kanton) ────────────────────────────────────────
if view_tab == "canton":
    st.title(f"{t('export_doc_title', lang)} {canton_label}")

    # ── Two-column hero: overview text left, map tabs right ────────────────
    left_col, right_col = st.columns([1, 1])

    with left_col:
        bg, text_colour = _warnstufe_palette(canton.max_warnlevel)
        st.markdown(
            f"""<div style="background:{bg};border-radius:8px;padding:18px;color:{text_colour};">
            <div style="font-size:11px;opacity:.85;">{t("current_warnlevel", lang)}</div>
            <div style="font-size:28px;font-weight:700;">{doc.lead_headline}</div>
            <div style="font-size:12px;opacity:.85;">{doc.lead_meta}</div>
            </div>""",
            unsafe_allow_html=True,
        )
        allg_sec = next((s for s in rs.sections if s.id == "allgemeine-lage"), None)
        if allg_sec:
            title = allg_sec.title.get(lang, allg_sec.title.get("de", allg_sec.id))
            st.markdown(f"## {title}")
            st.markdown(doc.sections.get("allgemeine-lage", ""))

    with right_col:
        if doc.lead_maps:
            tab_labels = [
                (map_spec.title_de if lang == "de" else map_spec.title_fr)
                for map_spec in doc.lead_maps
            ]
            tabs = st.tabs(tab_labels)
            for tab, map_spec in zip(tabs, doc.lead_maps):
                with tab:
                    m = build_canton_map(canton, map_spec)
                    st.components.v1.html(m._repr_html_(), height=300)

    # ── CDI legend (full width) ────────────────────────────────────────────
    labels = DROUGHT_LEGEND[lang]
    items_html = "".join(
        f"""<span style="display:inline-flex;align-items:center;margin-right:18px;white-space:nowrap;">
            <span style="display:inline-block;width:14px;height:14px;background:{colour};
                         border-radius:2px;margin-right:6px;flex-shrink:0;"></span>
            <span style="font-size:13px;">{label}</span>
        </span>"""
        for colour, label in zip(DROUGHT_COLOURS, labels)
    )
    st.markdown(
        f'<div style="display:flex;flex-wrap:wrap;align-items:center;'
        f'margin-top: 10px; padding: 0; gap: 8px;">'
        f'{items_html}</div>',
        unsafe_allow_html=True,
    )

    st.divider()

    for sec in rs.sections:
        if sec.id in ("regionen", "allgemeine-lage"):
            continue

        title = sec.title.get(lang, sec.title.get("de", sec.id))
        st.markdown(f"## {title}")
        st.markdown(doc.sections[sec.id])
        st.write("")

# ── Tab 2: Regionale Lage ──────────────────────────────────────────────────
elif view_tab == "regions":
    st.title(f"{t('tab_regions', lang)}: {canton_label}")
    st.divider()
    
    # Extract narratives from the generated Markdown
    regional_narratives = {}
    if "regionen" in doc.sections:
        parts = re.split(r'^###\s+(.*)$', doc.sections["regionen"], flags=re.MULTILINE)
        for i in range(1, len(parts), 2):
            r_name = parts[i].strip()
            r_text = parts[i+1].strip().replace('\n', '<br/>')
            regional_narratives[r_name] = r_text

    regionen_sec = next((s for s in rs.sections if s.id == "regionen"), None)
    col_allg_lage = regionen_sec.title.get(lang, "Allgemeine Lage") if regionen_sec else "Allgemeine Lage"
    col_expert = t("col_canton_recs", lang)
    
    # Render Table Header using Streamlit Columns
    h_col1, h_col2, h_col3, h_col4, h_col5 = st.columns([1, 1.5, 2.5, 3.5, 2.5])
    h_col1.markdown(f"**{t('col_warnstufe', lang)}**")
    h_col2.markdown(f"**{t('col_region', lang)}**")
    h_col3.markdown(f"**{t('col_situation', lang)}**")
    h_col4.markdown(f"**{col_allg_lage}**")
    h_col5.markdown(f"**{col_expert}**")
    
    st.markdown("<hr style='margin-top: 0px; margin-bottom: 10px;'/>", unsafe_allow_html=True)

    # Render Rows
    for r in canton.regions:
        c1, c2, c3, c4, c5 = st.columns([1, 1.5, 2.5, 3.5, 2.5])
        
        # 1. Warnstufe Badge
        bg, fg = _warnstufe_palette(r.warnlevel)
        badge = f"<div style='background:{bg}; color:{fg}; padding:6px; border-radius:6px; text-align:center; font-weight:bold; width:max-content; min-width:30px;'>{r.warnlevel}</div>"
        
        # 2. Region Name
        name = get_region_names(lang).get(r.region_id, r.region_name_de)
        
        # 3. Situation (Hydro Station Data)
        if r.hydro_stations:
            hydro_lines = []
            for hs in r.hydro_stations:
                val_str = f"{hs.current_value:.1f}" if not math.isnan(hs.current_value) else "–"
                t1_str = f"{hs.threshold1:.1f}" if not math.isnan(hs.threshold1) else "–"
                min_str = f"{hs.min_value:.1f}" if not math.isnan(hs.min_value) else "–"
                
                hydro_lines.append(
                    f"<b>{hs.station_name} ({hs.station_id})</b><br/>" 
                    f"<span style='color:#555; font-size:13px; line-height: 1.3;'>"
                    f"Abfluss: {val_str}<br/>"
                    f"T1: {t1_str} | Min: {min_str}"
                    f"</span>"
                )
            situation = "<br/><br/>".join(hydro_lines)
        else:
            situation = "<span style='color:#999; font-size: 13px;'>Keine Stationen/Daten</span>"
        
        # 4. Allgemeine Lage (Narrative)
        narrative_text = regional_narratives.get(r.region_name_de, "–")
        narrative_html = f"<span style='font-size: 14px; color: #333; line-height: 1.4;'>{narrative_text}</span>"

        with c1:
            st.markdown(badge, unsafe_allow_html=True)
        with c2:
            st.markdown(f"**{name}**")
        with c3:
            st.markdown(situation, unsafe_allow_html=True)
        with c4:
            st.markdown(narrative_html, unsafe_allow_html=True)
        with c5:
            # 5. Expert Input Widget
            expert_key = f"expert_{r.region_id}"
            
            # Sync value from session_state if it exists
            current_val = st.session_state.expert_notes.get(expert_key, "")
            
            # Update session state on change
            def update_note(key=expert_key):
                st.session_state.expert_notes[key] = st.session_state[f"widget_{key}"]

            st.text_area(
                t("expert_input_label", lang), 
                value=current_val, 
                key=f"widget_{expert_key}", 
                label_visibility="collapsed",
                on_change=update_note,
                placeholder=t("expert_input_placeholder", lang)
            )
            
        st.markdown("<hr style='margin-top: 10px; margin-bottom: 10px; border-top: 1px solid #eee;'/>", unsafe_allow_html=True)

# ── Global Footer (Applies to both tabs) ───────────────────────────────────
st.divider()

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
    
    for r in canton.regions:
        st.caption(
            f"R{r.region_id} ({r.region_name_de}): "
            f"{r.quality.overall} — {t('coverage', lang)} {r.quality.coverage_pct:.0%}"
        )

with export_placeholder:
    html_str = to_html(
        doc=doc, 
        canton_report=canton, 
        ruleset=rs, 
        expert_notes=st.session_state.expert_notes
    )
    
    st.download_button(
        label=t("btn_html", lang),
        data=html_str.encode("utf-8"),
        file_name=f"trockenheit_{canton.data_timestamp.strftime('%Y%m%d')}.html",
        mime="text/html",
    )
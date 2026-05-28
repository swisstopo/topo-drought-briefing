# app.py
"""One Click Drought Briefing — Streamlit entry point for Kanton Bern."""
from __future__ import annotations

import logging
import math
import streamlit as st

from config.settings import BERNE_REGION_IDS, CDI_COLOURS
from src.aggregation.regional import compute_region_report
from src.briefing.template import build_briefing
from src.data.stac_client import load as load_data
from src.export.report import to_html
from src.i18n.strings import get_cdi_labels, get_region_names, t
from src.models import DataBundle
from src.viz.charts import build_timeseries
from src.viz.maps import build_map

st.set_page_config(
    page_title="Trockenheitsbriefing / Bulletin sécheresse",
    page_icon="💧",
    layout="wide",
)


@st.cache_data(ttl=3600, show_spinner="Daten werden geladen…")
def _load_bundle() -> DataBundle:
    return load_data()


# ── Sidebar ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("💧 Trockenheitsbriefing")
    st.caption("Kanton Bern · trockenheit.admin.ch")
    st.divider()

    lang = st.radio(
        "Sprache / Langue",
        options=["de", "fr"],
        format_func=lambda l: "Deutsch" if l == "de" else "Français",
        horizontal=True,
        index=0,
    )

    mode = st.radio(
        t("mode_label", lang),
        options=["behoerden", "bulletin"],
        format_func=lambda m: t("mode_behoerden", lang) if m == "behoerden" else t("mode_bulletin", lang),
        index=0,
    )

    region_options = sorted(BERNE_REGION_IDS)
    selected_region_id = st.selectbox(
        t("region_label", lang),
        options=region_options,
        format_func=lambda rid: get_region_names(lang).get(rid, str(rid)),
        index=1,
    )

    st.divider()

    bundle = _load_bundle()
    st.caption(f"{t('data_status', lang)}: {bundle.data_timestamp.strftime('%d.%m.%Y')}")
    st.caption(f"{t('source', lang)}: {bundle.source}")

    st.divider()
    st.subheader(t("export_header", lang))
    export_placeholder = st.empty()


# ── Pipeline ───────────────────────────────────────────────────────────────
all_reports = [compute_region_report(rid, bundle) for rid in BERNE_REGION_IDS]
report = next(r for r in all_reports if r.region_id == selected_region_id)
doc = build_briefing(report, mode, lang=lang)

mode_label = t("mode_behoerden", lang) if mode == "behoerden" else t("mode_bulletin", lang)

# ── Header ─────────────────────────────────────────────────────────────────
cdi_colour = CDI_COLOURS.get(report.cdi, "#cccccc")
cdi_label = get_cdi_labels(lang).get(report.cdi, t("unknown", lang))

col_title, col_badge = st.columns([4, 1])
with col_title:
    st.title(f"{mode_label}: {t('briefing_title', lang)}")
    st.caption(
        f"**{get_region_names(lang).get(report.region_id, report.region_name_de)}** · Kanton Bern · "
        f"{t('stand', lang)}: {report.data_timestamp.strftime('%d.%m.%Y')} · "
        f"{t('source', lang)}: {report.source}"
    )
with col_badge:
    st.markdown(
        f"""<div style="background:{cdi_colour};border-radius:10px;padding:12px;text-align:center;">
        <div style="font-size:11px;color:rgba(255,255,255,0.8);">CDI</div>
        <div style="font-size:36px;font-weight:bold;color:white;">{report.cdi}</div>
        <div style="font-size:11px;color:rgba(255,255,255,0.9);">{cdi_label}</div>
        </div>""",
        unsafe_allow_html=True,
    )

st.divider()

# ── Indicators ─────────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric(t("metric_spi", lang), f"{report.spi_3m:.2f}", delta=f"{report.spi_3m_delta:+.2f}/Wo")
with c2:
    st.metric(
        t("metric_soil", lang),
        f"{report.soil_moisture_pct:.0f}%",
        help=t("metric_spi_help", lang).format(percentile=report.spi_3m_percentile),
    )
with c3:
    vhi_val = f"{report.vhi:.1f}" if not math.isnan(report.vhi) else "–"
    vhi_delta_str = f"{report.vhi_delta:+.1f}" if not math.isnan(report.vhi_delta) else None
    st.metric(t("metric_vhi", lang), vhi_val, delta=vhi_delta_str)
with c4:
    st.metric(
        t("metric_critical", lang),
        f"{report.pct_critical * 100:.0f}%",
        help=t("metric_critical_help", lang),
    )

# ── Map + Chart ────────────────────────────────────────────────────────────
map_col, chart_col = st.columns(2)

with map_col:
    st.subheader(t("section_map", lang))
    folium_map = build_map(report, all_reports)
    st.components.v1.html(folium_map._repr_html_(), height=300)

with chart_col:
    st.subheader(t("section_chart", lang))
    fig = build_timeseries(bundle.historic_df, selected_region_id, lang=lang)
    st.plotly_chart(fig, use_container_width=True)

# ── Text sections ──────────────────────────────────────────────────────────
st.divider()
for section_key in ["lage", "entwicklung", "einordnung"]:
    st.markdown(f"**{t('section_' + section_key, lang)}**")
    st.markdown(doc.sections[section_key])
    st.write("")

# ── Quality panel ──────────────────────────────────────────────────────────
with st.expander(t("quality_expander", lang)):
    q = report.quality
    q_colour = {"ok": "🟢", "warning": "🟡", "error": "🔴"}.get(q.overall, "⚪")
    st.markdown(
        f"{q_colour} **{q.overall.upper()}** — "
        f"{t('data_age', lang)}: {q.data_age_days} Tage — "
        f"{t('coverage', lang)}: {q.coverage_pct:.0%}"
    )
    if q.missing_columns:
        st.warning(f"{t('quality_missing_cols', lang)}: {', '.join(q.missing_columns)}")
    if q.outlier_flags:
        st.warning(f"{t('quality_outliers', lang)}: {', '.join(q.outlier_flags)}")
    st.caption(doc.sections["datengrundlage"])

# ── Export buttons ─────────────────────────────────────────────────────────
with export_placeholder:
    html_str = to_html(doc, report, chart_fig=fig, map_obj=folium_map, lang=lang)

    st.info("💡 PDF: Datei → Drucken → Als PDF speichern (Ctrl+P)")
    st.download_button(
        label=t("btn_html", lang),
        data=html_str.encode("utf-8"),
        file_name=f"trockenheit_{report.region_name_de.replace(' ', '_')}_{report.data_timestamp.strftime('%Y%m%d')}.html",
        mime="text/html",
    )

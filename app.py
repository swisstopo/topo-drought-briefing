# app.py
"""One Click Drought Briefing — Streamlit entry point for Kanton Bern."""
from __future__ import annotations

import math
import streamlit as st
from streamlit_folium import st_folium

from config.settings import BERNE_REGION_IDS, BERNE_REGION_NAMES, CDI_COLOURS, CDI_LABELS
from src.aggregation.regional import compute_region_report
from src.briefing.template import build_briefing
from src.data.stac_client import load as load_data
from src.export.report import to_html, to_pdf
from src.models import DataBundle
from src.viz.charts import build_timeseries
from src.viz.maps import build_export_map, build_map

st.set_page_config(
    page_title="Trockenheitsbriefing Kanton Bern",
    page_icon="💧",
    layout="wide",
)

# ── Data loading (cached) ──────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner="Daten werden geladen…")
def _load_bundle() -> DataBundle:
    return load_data()


# ── Sidebar ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("💧 Trockenheitsbriefing")
    st.caption("Kanton Bern · trockenheit.admin.ch")
    st.divider()

    mode = st.radio(
        "Ausgabemodus",
        options=["behoerden", "bulletin"],
        format_func=lambda m: "⚖ Behördenbriefing" if m == "behoerden" else "📰 Mein Trockenheitsbulletin",
        index=0,
    )

    region_options = sorted(BERNE_REGION_IDS)
    selected_region_id = st.selectbox(
        "Warnregion (Kanton Bern)",
        options=region_options,
        format_func=lambda rid: BERNE_REGION_NAMES.get(rid, str(rid)),
        index=1,  # default: Berner Mittelland (34)
    )

    st.divider()

    bundle = _load_bundle()
    st.caption(f"🟢 Datenstand: {bundle.data_timestamp.strftime('%d.%m.%Y')}")
    st.caption(f"Quelle: {bundle.source}")

    st.divider()
    st.subheader("Export")
    export_placeholder = st.empty()


# ── Pipeline ───────────────────────────────────────────────────────────────
all_reports = [compute_region_report(rid, bundle) for rid in BERNE_REGION_IDS]
report = next(r for r in all_reports if r.region_id == selected_region_id)
doc = build_briefing(report, mode)

mode_label = "Behördenbriefing" if mode == "behoerden" else "Mein Trockenheitsbulletin"

# ── Header ─────────────────────────────────────────────────────────────────
cdi_colour = CDI_COLOURS.get(report.cdi, "#cccccc")
cdi_label = CDI_LABELS.get(report.cdi, "Unbekannt")

col_title, col_badge = st.columns([4, 1])
with col_title:
    st.title(f"{mode_label}: Trockenheit")
    st.caption(
        f"**{report.region_name_de}** · Kanton Bern · "
        f"Stand: {report.data_timestamp.strftime('%d.%m.%Y')} · Quelle: {report.source}"
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
    st.metric("SPI-3m", f"{report.spi_3m:.2f}", delta=f"{report.spi_3m_delta:+.2f}/Wo")
with c2:
    st.metric("Bodenfeuchte (% nFK)", f"{report.soil_moisture_pct:.0f}%",
              help=f"{report.spi_3m_percentile}. Perzentil (Ref. 1961–2020)")
with c3:
    vhi_val = f"{report.vhi:.1f}" if not math.isnan(report.vhi) else "–"
    vhi_delta_str = f"{report.vhi_delta:+.1f}" if not math.isnan(report.vhi_delta) else None
    st.metric("VHI", vhi_val, delta=vhi_delta_str)
with c4:
    st.metric("% krit. Wochen", f"{report.pct_critical * 100:.0f}%",
              help="Anteil Wochen mit CDI ≥ 3 in den letzten 52 Wochen")

# ── Map + Chart ────────────────────────────────────────────────────────────
map_col, chart_col = st.columns(2)

with map_col:
    st.subheader("CDI-Karte Kanton Bern")
    folium_map = build_map(report, all_reports)
    st_folium(folium_map, width=None, height=300, returned_objects=[])

with chart_col:
    st.subheader("Zeitreihe — letzte 52 Wochen")
    fig = build_timeseries(bundle.historic_df, selected_region_id)
    st.plotly_chart(fig, use_container_width=True)

# ── Text sections ──────────────────────────────────────────────────────────
st.divider()
for section_key, section_title in [
    ("lage", "Lage"),
    ("entwicklung", "Entwicklung"),
    ("einordnung", "Einordnung"),
]:
    st.markdown(f"**{section_title}**")
    st.markdown(doc.sections[section_key])
    st.write("")

# ── Quality panel ──────────────────────────────────────────────────────────
with st.expander("Qualität & Datengrundlage"):
    q = report.quality
    q_colour = {"ok": "🟢", "warning": "🟡", "error": "🔴"}.get(q.overall, "⚪")
    st.markdown(f"{q_colour} **{q.overall.upper()}** — Aktualität: {q.data_age_days} Tage — Abdeckung: {q.coverage_pct:.0%}")
    if q.missing_columns:
        st.warning(f"Fehlende Spalten: {', '.join(q.missing_columns)}")
    if q.outlier_flags:
        st.warning(f"Ausreisser-Warnung: {', '.join(q.outlier_flags)}")
    st.caption(doc.sections["datengrundlage"])

# ── Export buttons ─────────────────────────────────────────────────────────
with export_placeholder:
    map_png = build_export_map(report, all_reports)
    html_str = to_html(doc, report, chart_fig=fig, map_png=map_png)

    st.download_button(
        label="⬇ PDF exportieren",
        data=to_pdf(html_str),
        file_name=f"trockenheit_{report.region_name_de.replace(' ', '_')}_{report.data_timestamp.strftime('%Y%m%d')}.pdf",
        mime="application/pdf",
    )
    st.download_button(
        label="⬇ HTML exportieren",
        data=html_str.encode("utf-8"),
        file_name=f"trockenheit_{report.region_name_de.replace(' ', '_')}_{report.data_timestamp.strftime('%Y%m%d')}.html",
        mime="text/html",
    )

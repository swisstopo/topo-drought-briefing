# src/export/report.py
from __future__ import annotations

import html

import plotly.io as pio

from config.settings import CDI_COLOURS
from src.i18n.strings import get_cdi_labels, get_region_names, t
from src.models import BriefingDocument, RegionReport


_CSS = """
body { font-family: 'Helvetica Neue', Arial, sans-serif; background: #fff; color: #1a1a2e; margin: 0; padding: 0; }
.page { max-width: 800px; margin: 0 auto; padding: 32px; }
h1 { font-size: 22px; color: #1a1a2e; margin-bottom: 4px; }
.subtitle { color: #555; font-size: 13px; margin-bottom: 24px; }
.cdi-badge { display: inline-block; padding: 6px 18px; border-radius: 6px; font-size: 28px;
             font-weight: bold; color: white; margin-bottom: 20px; }
.indicators { display: flex; gap: 16px; margin-bottom: 24px; }
.indicator { flex: 1; border: 1px solid #ddd; border-radius: 8px; padding: 12px; text-align: center; }
.indicator .label { font-size: 10px; color: #888; text-transform: uppercase; }
.indicator .value { font-size: 22px; font-weight: bold; color: #1a1a2e; }
.indicator .delta { font-size: 11px; color: #888; }
.section { margin-bottom: 20px; }
.section h2 { font-size: 12px; text-transform: uppercase; letter-spacing: 1px; color: #888; margin-bottom: 6px; }
.section p { font-size: 13px; line-height: 1.7; color: #333; margin: 0; }
.visuals { display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }
.visual-box { flex: 1; min-width: 300px; }
.visual-box img { width: 100%; border-radius: 8px; }
.quality-bar { background: #f5f5f5; border-radius: 6px; padding: 10px 16px;
               font-size: 11px; color: #666; margin-top: 24px; }
.quality-bar strong { color: #333; }

@media print {
    body { background: white; }
    .page { padding: 0; max-width: 100%; }
    .visuals { page-break-inside: avoid; }
}
"""


def to_html(
    doc: BriefingDocument,
    report: RegionReport,
    chart_fig=None,
    map_obj=None,
    lang: str = "de",
) -> str:
    cdi_colour = CDI_COLOURS.get(report.cdi, "#cccccc")
    cdi_label = get_cdi_labels(lang).get(report.cdi, t("unknown", lang))
    region_name = get_region_names(lang).get(report.region_id, report.region_name_de)
    doc_title = t("export_doc_title", lang)
    mode_label = t("mode_behoerden", lang) if doc.mode == "behoerden" else t("mode_bulletin", lang)

    def fmt(v, fmt_str=".1f", fallback="--"):
        try:
            return format(v, fmt_str)
        except Exception:
            return fallback

    def delta_arrow(v):
        if v > 0:
            return f"+{v:.2f}"
        if v < 0:
            return f"-{abs(v):.2f}"
        return "0.00"

    chart_html = ""
    if chart_fig is not None:
        chart_html = pio.to_html(chart_fig, full_html=False, include_plotlyjs="inline")

    map_html = ""
    if map_obj is not None:
        folium_raw_html = map_obj.get_root().render()
        escaped_folium = html.escape(folium_raw_html)
        map_html = f'<iframe srcdoc="{escaped_folium}" style="width:100%; height:400px; border:none; border-radius:8px;"></iframe>'

    quality_colour = {"ok": "#2ecc71", "warning": "#f1c40f", "error": "#e74c3c"}.get(
        report.quality.overall, "#ccc"
    )

    html_str = f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{doc_title}: {region_name}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="page">
  <h1>{mode_label}: {doc_title} - {region_name}</h1>
  <div class="subtitle">Kanton Bern - Datenstand: {report.data_timestamp.strftime("%d.%m.%Y")} - Quelle: {report.source}</div>

  <div class="cdi-badge" style="background:{cdi_colour}">CDI {report.cdi} - {cdi_label}</div>

  <div class="indicators">
    <div class="indicator">
      <div class="label">{t("export_metric_spi", lang)}</div>
      <div class="value">{fmt(report.spi_3m, ".2f")}</div>
      <div class="delta">{delta_arrow(report.spi_3m_delta)}/Woche</div>
    </div>
    <div class="indicator">
      <div class="label">{t("export_metric_soil", lang)}</div>
      <div class="value">{fmt(report.soil_moisture_pct, ".0f")}%</div>
      <div class="delta">{report.spi_3m_percentile}. Perz.</div>
    </div>
    <div class="indicator">
      <div class="label">{t("export_metric_vhi", lang)}</div>
      <div class="value">{fmt(report.vhi, ".1f")}</div>
      <div class="delta">{delta_arrow(report.vhi_delta)}</div>
    </div>
    <div class="indicator">
      <div class="label">{t("export_metric_critical", lang)}</div>
      <div class="value">{report.pct_critical * 100:.0f}%</div>
    </div>
  </div>

  <div class="visuals">
    <div class="visual-box">{map_html}</div>
    <div class="visual-box">{chart_html}</div>
  </div>

  <div class="section">
    <h2>{t("export_section_lage", lang)}</h2>
    <p>{doc.sections["lage"]}</p>
  </div>
  <div class="section">
    <h2>{t("export_section_entwicklung", lang)}</h2>
    <p>{doc.sections["entwicklung"]}</p>
  </div>
  <div class="section">
    <h2>{t("export_section_einordnung", lang)}</h2>
    <p>{doc.sections["einordnung"]}</p>
  </div>
  <div class="section">
    <h2>{t("export_section_datengrundlage", lang)}</h2>
    <p>{doc.sections["datengrundlage"]}</p>
  </div>

  <div class="quality-bar">
    <strong>Qualität:</strong>
    <span style="color:{quality_colour}">● {report.quality.overall.upper()}</span>
    &nbsp;|&nbsp; {t("export_quality_age", lang)}: {report.quality.data_age_days} Tage
    &nbsp;|&nbsp; {t("export_quality_coverage", lang)}: {report.quality.coverage_pct:.0%}
    {(" &nbsp;|&nbsp; Ausreisser: " + ", ".join(report.quality.outlier_flags)) if report.quality.outlier_flags else ""}
    {(" &nbsp;|&nbsp; Fehlend: " + ", ".join(report.quality.missing_columns)) if report.quality.missing_columns else ""}
  </div>
</div>
</body>
</html>"""
    return html_str
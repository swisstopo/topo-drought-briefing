# src/export/report.py
"""
Export pipeline:
  to_html(doc, report, chart_fig, map_png) -> self-contained HTML string (all CSS inline)
  to_pdf(html_str) -> PDF bytes via WeasyPrint
"""
from __future__ import annotations

import base64

import plotly.io as pio

from config.settings import CDI_COLOURS, CDI_LABELS
from src.models import BriefingDocument, RegionReport


def _chart_to_png_b64(fig) -> str:
    img_bytes = pio.to_image(fig, format="png", width=700, height=300, scale=2)
    return base64.b64encode(img_bytes).decode()


def _map_to_b64(png_bytes: bytes) -> str:
    return base64.b64encode(png_bytes).decode()


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
.visuals { display: flex; gap: 16px; margin-bottom: 24px; }
.visual-box { flex: 1; }
.visual-box img { width: 100%; border-radius: 8px; }
.quality-bar { background: #f5f5f5; border-radius: 6px; padding: 10px 16px;
               font-size: 11px; color: #666; margin-top: 24px; }
.quality-bar strong { color: #333; }
"""


def to_html(
    doc: BriefingDocument,
    report: RegionReport,
    chart_fig=None,
    map_png: bytes | None = None,
) -> str:
    cdi_colour = CDI_COLOURS.get(report.cdi, "#cccccc")
    cdi_label = CDI_LABELS.get(report.cdi, "Unbekannt")
    mode_label = "Behoerdenbriefing" if doc.mode == "behoerden" else "Mein Trockenheitsbulletin"

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
        b64 = _chart_to_png_b64(chart_fig)
        chart_html = f'<img src="data:image/png;base64,{b64}" alt="Zeitreihe">'

    map_html = ""
    if map_png is not None:
        b64 = _map_to_b64(map_png)
        map_html = f'<img src="data:image/png;base64,{b64}" alt="CDI-Karte">'

    quality_colour = {"ok": "#2ecc71", "warning": "#f1c40f", "error": "#e74c3c"}.get(
        report.quality.overall, "#ccc"
    )

    html = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{mode_label}: {report.region_name_de}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="page">
  <h1>{mode_label}: Trockenheit - {report.region_name_de}</h1>
  <div class="subtitle">Kanton Bern - Datenstand: {report.data_timestamp.strftime("%d.%m.%Y")} - Quelle: {report.source}</div>

  <div class="cdi-badge" style="background:{cdi_colour}">CDI {report.cdi} - {cdi_label}</div>

  <div class="indicators">
    <div class="indicator">
      <div class="label">SPI-3m</div>
      <div class="value">{fmt(report.spi_3m, ".2f")}</div>
      <div class="delta">{delta_arrow(report.spi_3m_delta)}/Woche</div>
    </div>
    <div class="indicator">
      <div class="label">Bodenfeuchte</div>
      <div class="value">{fmt(report.soil_moisture_pct, ".0f")}%</div>
      <div class="delta">nFK - {report.spi_3m_percentile}. Perz.</div>
    </div>
    <div class="indicator">
      <div class="label">VHI</div>
      <div class="value">{fmt(report.vhi, ".1f")}</div>
      <div class="delta">{delta_arrow(report.vhi_delta)}</div>
    </div>
    <div class="indicator">
      <div class="label">% krit. Wochen</div>
      <div class="value">{report.pct_critical * 100:.0f}%</div>
      <div class="delta">letzte 52 Wochen</div>
    </div>
  </div>

  <div class="visuals">
    <div class="visual-box">{map_html}</div>
    <div class="visual-box">{chart_html}</div>
  </div>

  <div class="section">
    <h2>Lage</h2>
    <p>{doc.sections["lage"]}</p>
  </div>
  <div class="section">
    <h2>Entwicklung</h2>
    <p>{doc.sections["entwicklung"]}</p>
  </div>
  <div class="section">
    <h2>Einordnung</h2>
    <p>{doc.sections["einordnung"]}</p>
  </div>
  <div class="section">
    <h2>Datengrundlage</h2>
    <p>{doc.sections["datengrundlage"]}</p>
  </div>

  <div class="quality-bar">
    <strong>Qualitaet:</strong>
    <span style="color:{quality_colour}">● {report.quality.overall.upper()}</span>
    &nbsp;|&nbsp; Aktualitaet: {report.quality.data_age_days} Tage
    &nbsp;|&nbsp; Abdeckung: {report.quality.coverage_pct:.0%}
    {(" &nbsp;|&nbsp; Ausreisser: " + ", ".join(report.quality.outlier_flags)) if report.quality.outlier_flags else ""}
    {(" &nbsp;|&nbsp; Fehlend: " + ", ".join(report.quality.missing_columns)) if report.quality.missing_columns else ""}
  </div>
</div>
</body>
</html>"""
    return html


def to_pdf(html_str: str) -> bytes:
    """Convert HTML string to PDF bytes via WeasyPrint."""
    import weasyprint
    return weasyprint.HTML(string=html_str).write_pdf()

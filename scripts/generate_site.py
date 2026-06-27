"""
scripts/generate_site.py

Purpose : Read pre-computed JSON from data/processed/cantons/, apply the
          briefing ruleset, and write a fully static website to site/.
          No drought computation is performed here — the site consumes
          pre-built JSON only.
Inputs  : data/processed/cantons/{canton_id}.json  – per-canton reports
          data/ruleset/canton-bulletin.yaml          – briefing ruleset
Outputs : site/
            index.html                – bilingual overview of all cantons
            canton/{id}/index.html    – bilingual canton briefing page
            data/cantons/{id}.json    – processed JSON (copied for transparency)
            assets/style.css          – Swiss Confederation Design System styles
            assets/app.js             – language switcher (vanilla JS)
"""
from __future__ import annotations

import html as _html
import json
import logging
import math
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import yaml

from config.settings import CANTON_ABBREV
from src.briefing.renderer import load_ruleset, render_briefing
from src.i18n.strings import get_region_names, t
from src.models import (
    CantonReport,
    DischargeStats,
    HydroStationReport,
    QualityReport,
    RegionReport,
)

PROCESSED_DIR = _REPO_ROOT / "data" / "processed"
RULESET_PATH = _REPO_ROOT / "data" / "ruleset" / "canton-bulletin.yaml"
SOURCES_PATH = _REPO_ROOT / "config" / "sources.yaml"
SITE_DIR = _REPO_ROOT / "site"

_FAVICON_URL = "https://www.admin.ch/favicon.ico"

_WARNSTUFE_COLOURS: dict[int, tuple[str, str]] = {
    1: ("#6bbd50", "#ffffff"),
    2: ("#f7e84c", "#1a1a1a"),
    3: ("#ff8c00", "#ffffff"),
    4: ("#e02020", "#ffffff"),
    5: ("#8b0000", "#ffffff"),
}

# Legend colours for the CDI scale — matching the exact colours used by the
# BAFU trockenheit.admin.ch WMS layer (extracted from the live map legend).
_CDI_LEGEND_COLOURS: dict[int, str] = {
    1: "#97e8cb",  # rgb(151, 232, 203) — nicht trocken
    2: "#f9e5ae",  # rgb(249, 229, 174) — leicht trocken
    3: "#f1b981",  # rgb(241, 185, 129) — trocken
    4: "#d18c47",  # rgb(209, 140, 71)  — sehr trocken
    5: "#8a5a42",  # rgb(138, 90, 66)   — extrem trocken
}

# Short adjective labels that match the BAFU map legend (not the long noun form).
# CDI 0 (no drought at all) is intentionally omitted — the map shows only 1-5.
_CDI_LEGEND_LABELS: dict[int, str] = {
    1: "Nicht trocken",
    2: "Leicht trocken",
    3: "Trocken",
    4: "Sehr trocken",
    5: "Extrem trocken",
}
_CDI_LEGEND_LABELS_FR: dict[int, str] = {
    1: "Pas sec",
    2: "Légèrement sec",
    3: "Sec",
    4: "Très sec",
    5: "Extrêmement sec",
}

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Static assets: Swiss Confederation Design System
# ---------------------------------------------------------------------------

_CSS = """\
/* Drought Briefing — Swiss Confederation Design System */
:root {
  --blue:   #003F6B;
  --red:    #DC0000;
  --text:   #1A1A1A;
  --muted:  #666;
  --bg:     #F5F5F5;
  --white:  #fff;
  --border: #D0D0D0;
  --shadow: 0 1px 3px rgba(0,0,0,.08);
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{font-family:Arial,Helvetica,'Noto Sans',sans-serif;font-size:15px;line-height:1.55;color:var(--text);background:var(--bg)}
a{color:var(--blue)}
.container{max-width:1100px;margin:0 auto;padding:0 1.25rem}

/* Header */
.site-header{background:var(--white);border-top:4px solid var(--red);border-bottom:1px solid var(--border);padding:.75rem 0;position:sticky;top:0;z-index:100}
.header-inner{display:flex;align-items:center;justify-content:space-between}
.site-brand{display:flex;align-items:center;gap:.5rem;text-decoration:none;color:var(--blue);font-weight:700;font-size:1.05rem}
.site-brand:hover{text-decoration:underline}

/* Language toggle */
.lang-toggle{display:flex;border:1px solid var(--border);border-radius:4px;overflow:hidden}
.lang-btn{border:none;background:transparent;color:var(--muted);padding:.3rem .7rem;font-size:.85rem;cursor:pointer;font-weight:700;font-family:inherit;transition:background .1s,color .1s}
.lang-btn+.lang-btn{border-left:1px solid var(--border)}
.lang-btn.active{background:var(--blue);color:var(--white)}
.lang-btn:hover:not(.active){background:var(--bg)}

/* Language visibility */
html[lang="fr"] .lang-de{display:none!important}
html[lang="de"] .lang-fr{display:none!important}

/* Main */
main{padding:2rem 0 3rem}
.page-header{margin-bottom:2rem}
.page-title{font-size:1.9rem;font-weight:700;color:var(--blue)}
.page-subtitle{color:var(--muted);font-size:.9rem;margin-top:.2rem}

/* Lead card */
.lead-card{border-radius:6px;padding:1.25rem 1.5rem;margin-bottom:1.75rem;display:flex;align-items:flex-start;gap:1.25rem}
.lead-content{flex:1;min-width:0}
.lead-headline{font-size:1.35rem;font-weight:700;margin-bottom:.3rem}
.lead-meta{font-size:.88rem;opacity:.85}
.badge-large{font-size:1.8rem;font-weight:700;width:3.2rem;height:3.2rem;display:flex;align-items:center;justify-content:center;border-radius:6px;background:rgba(255,255,255,.25);flex-shrink:0}

/* Warnlevel badges */
.wl{display:inline-block;border-radius:4px;font-weight:700;padding:.15rem .5rem;min-width:2rem;text-align:center}
.wl-1{background:#6bbd50;color:#fff}
.wl-2{background:#f7e84c;color:#1a1a1a}
.wl-3{background:#ff8c00;color:#fff}
.wl-4{background:#e02020;color:#fff}
.wl-5{background:#8b0000;color:#fff}

/* Cards */
.card{background:var(--white);border:1px solid var(--border);border-radius:6px;padding:1.25rem 1.5rem;margin-bottom:1.25rem;box-shadow:var(--shadow)}
.card h2{font-size:1rem;font-weight:700;color:var(--blue);padding-bottom:.6rem;margin-bottom:.9rem;border-bottom:2px solid var(--bg)}
.card-text{white-space:pre-line;font-size:.9rem}

/* Region table */
.region-table{width:100%;border-collapse:collapse;font-size:.88rem;margin-top:.5rem}
.region-table th{padding:.55rem .5rem;background:var(--bg);border-bottom:2px solid var(--border);text-align:left;font-weight:700;color:var(--blue)}
.region-table td{padding:.7rem .5rem;border-bottom:1px solid var(--border);vertical-align:top}
.region-table tr:last-child td{border-bottom:none}

/* Canton grid (index) */
.canton-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:1rem}
.canton-card{display:flex;align-items:center;gap:1rem;background:var(--white);border:1px solid var(--border);border-radius:6px;padding:1rem 1.25rem;text-decoration:none;color:inherit;box-shadow:var(--shadow);transition:border-color .15s,box-shadow .15s}
.canton-card:hover{border-color:var(--blue);box-shadow:0 2px 8px rgba(0,63,107,.18)}
.canton-card-info{flex:1;min-width:0}
.canton-name{font-weight:700}
.canton-ts{font-size:.78rem;color:var(--muted)}

/* Footer + quality */
.site-footer{background:var(--white);border-top:1px solid var(--border);padding:1.25rem 0;font-size:.8rem;color:var(--muted)}
.site-footer p{margin:0}
.site-footer .impressum{margin-top:.6rem;font-size:.72rem;line-height:1.5;border-top:1px solid var(--border);padding-top:.6rem}
.quality-bar{margin-top:2rem;padding-top:1rem;border-top:1px solid var(--border);color:var(--muted);font-size:.82rem}
.banner-links{margin-bottom:1rem;font-size:.85rem}
.banner-links a{margin-right:.75rem}
.further-links{margin-top:1rem}
.further-links ul{list-style:none}
.further-links li{padding:.2rem 0}
.further-links li::before{content:"\\2192  ";color:var(--blue)}

/* Responsive */
@media(max-width:600px){
  .lead-card{flex-direction:column}
  .canton-grid{grid-template-columns:1fr}
  .page-title{font-size:1.5rem}
  .region-table{font-size:.78rem}
}

/* BETA badge */
.beta-badge{color:var(--red);font-size:.6rem;font-weight:900;letter-spacing:.08em;text-transform:uppercase;border:1.5px solid var(--red);padding:.05rem .3rem;border-radius:2px;line-height:1;flex-shrink:0;align-self:center}

/* Action buttons (export / permalink) */
.header-actions{display:flex;align-items:center;gap:.5rem;flex-wrap:wrap}
.action-btn{border:1px solid var(--border);background:var(--white);color:var(--blue);padding:.3rem .65rem;font-size:.82rem;cursor:pointer;border-radius:4px;font-family:inherit;font-weight:700;transition:background .1s,color .1s}
.action-btn:hover{background:var(--blue);color:var(--white)}

/* Canton recommendation textarea */
.canton-rec{width:100%;min-height:72px;resize:vertical;border:1px solid var(--border);border-radius:4px;padding:.35rem .45rem;font-family:inherit;font-size:.82rem;color:var(--text);background:var(--white)}
.canton-rec:focus{outline:2px solid var(--blue);outline-offset:1px;border-color:var(--blue)}
.canton-rec-print{display:none}
.map-print-label{display:none}

/* Map + Allgemeine Lage side-by-side grid */
.map-lage-grid{display:grid;grid-template-columns:1fr 1fr;gap:1.25rem;align-items:stretch;margin-bottom:1.25rem}
@media(max-width:700px){.map-lage-grid{grid-template-columns:1fr}}
.map-lage-grid .map-card,.map-lage-grid .lage-card{margin-bottom:0;height:100%}

/* Map card */
.map-card{background:var(--white);border:1px solid var(--border);border-radius:6px;padding:1.25rem 1.5rem;margin-bottom:1.25rem;box-shadow:var(--shadow)}
.map-card h2{font-size:1rem;font-weight:700;color:var(--blue);padding-bottom:.6rem;margin-bottom:.9rem;border-bottom:2px solid var(--bg)}
.map-controls{display:flex;align-items:center;gap:1.5rem;margin-bottom:.75rem;flex-wrap:wrap}
.map-radio-group{display:flex;gap:1rem}
.map-radio-group label{display:flex;align-items:center;gap:.35rem;font-size:.88rem;cursor:pointer}
.map-radio-group input[type=radio]{accent-color:var(--blue)}
.map-frame{width:100%;height:420px;border:1px solid var(--border);border-radius:4px}
.map-unavailable{padding:2rem;text-align:center;color:var(--muted);background:var(--bg);border-radius:4px;font-size:.88rem;border:1px dashed var(--border)}

/* CDI legend */
.cdi-legend{display:flex;flex-wrap:wrap;gap:.4rem .75rem;margin-top:.75rem}
.cdi-legend-item{display:flex;align-items:center;gap:.4rem;font-size:.8rem}
.cdi-swatch{width:1rem;height:1rem;border-radius:2px;border:1px solid rgba(0,0,0,.1);flex-shrink:0}

/* Print */
@media print{
  .site-header{position:static}
  .header-actions{display:none!important}
  .lang-toggle{display:none!important}
  /* Show only the active map iframe; hide radio controls */
  .map-frame{display:none!important}
  .map-frame-active{display:block!important;height:260px;width:100%}
  .map-controls{display:none!important}
  /* Label showing which CDI layer is displayed */
  .map-print-label{display:block!important;font-size:.82rem;font-style:italic;color:var(--muted);margin:.3rem 0 .5rem}
  /* Swap textarea for its sibling div so all text is visible (no scroll cutoff) */
  .canton-rec{display:none!important}
  .canton-rec-print{display:block!important;white-space:pre-wrap;word-break:break-word;font-size:.82rem;color:var(--text);padding:.35rem 0;min-height:1em}
  .card,.map-card,.lage-card{box-shadow:none;break-inside:avoid}
  .map-lage-grid{grid-template-columns:7fr 3fr}
  .site-footer{display:none}
  .quality-bar{break-before:page}
  /* Preserve background colours in print (H) */
  .lead-card,.badge-large,.wl,.wl-1,.wl-2,.wl-3,.wl-4,.wl-5,.cdi-swatch{
    -webkit-print-color-adjust:exact;print-color-adjust:exact
  }
}
"""

_JS = """\
/* Drought Briefing — language switcher, permalink, export, map toggle, canton recs */
(function () {
  'use strict';

  /* ---- language switcher ---- */
  function switchLang(lang) {
    if (lang !== 'de' && lang !== 'fr') return;
    document.documentElement.lang = lang;
    document.querySelectorAll('.lang-btn').forEach(function (btn) {
      btn.classList.toggle('active', btn.dataset.lang === lang);
    });
    try { localStorage.setItem('droughtLang', lang); } catch (_) {}
    _updateBrandHref();
  }

  /* ---- permalink: copy URL + ?lang=XX to clipboard, show toast ---- */
  function _showToast(msg) {
    var t = document.createElement('div');
    t.textContent = msg;
    t.style.cssText = 'position:fixed;bottom:1.2rem;left:50%;transform:translateX(-50%);background:#333;color:#fff;padding:.45rem 1rem;border-radius:4px;font-size:.82rem;z-index:9999;pointer-events:none;opacity:1;transition:opacity .4s';
    document.body.appendChild(t);
    setTimeout(function() { t.style.opacity = '0'; }, 1400);
    setTimeout(function() { t.parentNode && t.parentNode.removeChild(t); }, 1900);
  }

  window.copyPermalink = function () {
    var base = window.location.href.split('?')[0];
    var lang = document.documentElement.lang || 'de';
    var link = base + '?lang=' + lang;
    var msg = lang === 'fr' ? 'Lien copié !' : 'Link kopiert!';
    function done() { _showToast(msg); }
    function fallback() {
      var ta = document.createElement('textarea');
      ta.value = link; ta.style.cssText = 'position:fixed;opacity:0';
      document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); } catch (_) {}
      document.body.removeChild(ta);
      done();
    }
    if (navigator.clipboard) {
      navigator.clipboard.writeText(link).then(done).catch(fallback);
    } else { fallback(); }
  };

  /* ---- keep brand link lang-aware so navigating back preserves language ---- */
  function _updateBrandHref() {
    var lang = document.documentElement.lang || 'de';
    document.querySelectorAll('.site-brand').forEach(function (a) {
      var href = a.getAttribute('href') || '';
      a.href = href.split('?')[0] + '?lang=' + lang;
    });
  }

  /* ---- map radio toggle: switch between CDI1 / CDI2 iframes ---- */
  function initMapToggle() {
    /* Mark the initially-checked frame as active (for print CSS) */
    var checked = document.querySelector('.map-radio-btn:checked');
    if (checked) {
      var init = document.getElementById(checked.value);
      if (init) init.classList.add('map-frame-active');
    }
    document.querySelectorAll('.map-radio-btn').forEach(function (radio) {
      radio.addEventListener('change', function () {
        var container = this.closest('.map-card');
        if (!container) return;
        container.querySelectorAll('.map-frame').forEach(function (f) {
          f.style.display = 'none';
          f.classList.remove('map-frame-active');
        });
        var target = document.getElementById(this.value);
        if (target) { target.style.display = 'block'; target.classList.add('map-frame-active'); }
      });
    });
  }

  /* ---- helpers shared by exportBriefing() and beforeprint ---- */
  function _getActiveMapLabel() {
    var checked = document.querySelector('.map-radio-btn:checked');
    if (!checked) return '';
    var label = checked.closest('label');
    if (!label) return '';
    var lang = document.documentElement.lang || 'de';
    var span = label.querySelector('.lang-' + lang);
    return span ? span.textContent.trim() : '';
  }
  function _notifyIframe(frame) {
    if (!frame) return;
    try { frame.contentWindow.dispatchEvent(new Event('beforeprint')); } catch (e) {}
    try { frame.contentWindow.postMessage('drought:beforeprint', '*'); } catch (e) {}
  }
  function _setMapPrintLabel() {
    var el = document.getElementById('map-print-label');
    if (el) el.textContent = _getActiveMapLabel();
  }

  /*
   * exportBriefing():
   *   1. Force the active map iframe to A4-print dimensions NOW (while still
   *      in screen mode) so that Leaflet refits to the right viewport size.
   *   2. Notify the iframe → Leaflet calls invalidateSize + fitBounds.
   *   3. After 900 ms (enough for tiles to load) open the print dialog.
   *   4. On afterprint, remove the forced dimensions.
   *
   * This avoids the race where print CSS shrinks the iframe AFTER Leaflet
   * already rendered for screen dimensions.
   */
  window.exportBriefing = function () {
    _setMapPrintLabel();
    var active = document.querySelector('.map-frame-active');
    if (active) {
      /* Map column is 30 % of A4 content width in print.
         A4 content ≈ 680 px at 96 dpi → 30 % ≈ 204 px. */
      var printW = Math.round(680 * 0.30);
      active.style.width  = printW + 'px';
      active.style.height = '260px';
      /* Let the browser apply the new dimensions, then tell Leaflet */
      requestAnimationFrame(function () {
        _notifyIframe(active);
        setTimeout(window.print, 900);
      });
    } else {
      setTimeout(window.print, 100);
    }
  };

  /* ---- before print (Ctrl+P path) — best-effort, no pre-resize possible ---- */
  window.addEventListener('beforeprint', function () {
    _setMapPrintLabel();
    _notifyIframe(document.querySelector('.map-frame-active'));
  });

  window.addEventListener('afterprint', function () {
    /* Restore any inline styles set by exportBriefing */
    var active = document.querySelector('.map-frame-active');
    if (active) { active.style.width = ''; active.style.height = ''; }
    var el = document.getElementById('map-print-label');
    if (el) el.textContent = '';
  });

  /* ---- canton recommendation textareas (no persistence — always start empty) ---- */
  function initCantonRecs() {
    document.querySelectorAll('.canton-rec').forEach(function (ta) {
      var printDiv = document.getElementById('canton-rec-print-' + ta.dataset.regionId);
      ta.addEventListener('input', function () {
        if (printDiv) printDiv.textContent = ta.value;
      });
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    /* language: URL param > localStorage > default de */
    var params = new URLSearchParams(window.location.search);
    var saved = null;
    try { saved = localStorage.getItem('droughtLang'); } catch (_) {}
    switchLang(params.get('lang') || saved || 'de');

    document.querySelectorAll('.lang-btn').forEach(function (btn) {
      btn.addEventListener('click', function () { switchLang(btn.dataset.lang); });
    });

    initMapToggle();
    initCantonRecs();
  });
}());
"""


def _write_assets(site_dir: Path) -> None:
    assets = site_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "style.css").write_text(_CSS, encoding="utf-8")
    (assets / "app.js").write_text(_JS, encoding="utf-8")
    log.info("  assets/style.css  assets/app.js")


# ---------------------------------------------------------------------------
# Deserialization: JSON dict → dataclass instances
# ---------------------------------------------------------------------------

def _float_or_nan(v: object) -> float:
    """Return float(v), or float('nan') when v is None (JSON null)."""
    return float("nan") if v is None else float(v)


def _quality_from_dict(d: dict) -> QualityReport:
    return QualityReport(
        data_age_days=int(d["data_age_days"]),
        coverage_pct=float(d["coverage_pct"]),
        missing_columns=list(d["missing_columns"]),
        outlier_flags=list(d["outlier_flags"]),
        is_stale=bool(d["is_stale"]),
        overall=d["overall"],
    )


def _discharge_from_dict(d: dict) -> DischargeStats:
    return DischargeStats(
        n_total=int(d["n_total"]),
        n_low=int(d["n_low"]),
        n_very_low=int(d["n_very_low"]),
        pct_low=int(d["pct_low"]),
    )


def _hydro_station_from_dict(d: dict) -> HydroStationReport:
    return HydroStationReport(
        station_id=str(d["station_id"]),
        station_name=str(d["station_name"]),
        current_value=_float_or_nan(d["current_value"]),
        threshold1=_float_or_nan(d["threshold1"]),
        min_value=_float_or_nan(d["min_value"]),
    )


def _region_from_dict(d: dict) -> RegionReport:
    return RegionReport(
        region_id=int(d["region_id"]),
        region_name_de=str(d["region_name_de"]),
        data_timestamp=datetime.fromisoformat(d["data_timestamp"]),
        source=d["source"],
        cdi=int(d["cdi"]),
        spi_3m=_float_or_nan(d["spi_3m"]),
        soil_moisture_pct=_float_or_nan(d["soil_moisture_pct"]),
        vhi=_float_or_nan(d["vhi"]),
        cdi_trend=int(d["cdi_trend"]),
        spi_3m_delta=float(d["spi_3m_delta"]),
        vhi_delta=float(d["vhi_delta"]),
        pct_critical=float(d["pct_critical"]),
        spi_3m_percentile=int(d["spi_3m_percentile"]),
        quality=_quality_from_dict(d["quality"]),
        precip_sum_1m=_float_or_nan(d["precip_sum_1m"]),
        precip_sum_3m=_float_or_nan(d["precip_sum_3m"]),
        precip_1m_index=int(d["precip_1m_index"]),
        soil_moisture_index=int(d["soil_moisture_index"]),
        hydro_index=int(d["hydro_index"]),
        warnlevel=int(d["warnlevel"]),
        warnlevel_info_de=str(d["warnlevel_info_de"]),
        warnlevel_info_fr=str(d["warnlevel_info_fr"]),
        cdi_forecast_week2=(
            int(d["cdi_forecast_week2"]) if d["cdi_forecast_week2"] is not None else None
        ),
        precip_1m_index_forecast=(
            int(d["precip_1m_index_forecast"])
            if d["precip_1m_index_forecast"] is not None
            else None
        ),
        soil_moisture_index_forecast=(
            int(d["soil_moisture_index_forecast"])
            if d["soil_moisture_index_forecast"] is not None
            else None
        ),
        precip_deficit_delta=int(d["precip_deficit_delta"]),
        soil_moisture_deficit_delta=int(d["soil_moisture_deficit_delta"]),
        discharge=_discharge_from_dict(d["discharge"]),
        hydro_stations=[_hydro_station_from_dict(s) for s in d["hydro_stations"]],
    )


def canton_from_dict(d: dict) -> CantonReport:
    """Reconstruct a CantonReport from a deserialized JSON dict."""
    return CantonReport(
        canton_id=int(d["canton_id"]),
        canton_name_de=str(d["canton_name_de"]),
        canton_name_fr=str(d["canton_name_fr"]),
        data_timestamp=datetime.fromisoformat(d["data_timestamp"]),
        source=d["source"],
        regions=[_region_from_dict(r) for r in d["regions"]],
        max_warnlevel=int(d["max_warnlevel"]),
        max_warnlevel_info_de=str(d["max_warnlevel_info_de"]),
        max_warnlevel_info_fr=str(d["max_warnlevel_info_fr"]),
        n_regions_by_precip_index={int(k): int(v) for k, v in d["n_regions_by_precip_index"].items()},
        n_regions_by_soil_moisture_index={
            int(k): int(v) for k, v in d["n_regions_by_soil_moisture_index"].items()
        },
        n_regions_by_hydro_index={int(k): int(v) for k, v in d["n_regions_by_hydro_index"].items()},
        quality=_quality_from_dict(d["quality"]),
        n_regions_dry=int(d["n_regions_dry"]),
        cdi_min_dry=int(d["cdi_min_dry"]) if d["cdi_min_dry"] is not None else None,
        cdi_max_dry=int(d["cdi_max_dry"]) if d["cdi_max_dry"] is not None else None,
        cdi_situation_delta=int(d["cdi_situation_delta"]),
        mean_precip_sum_1m=_float_or_nan(d["mean_precip_sum_1m"]),
        mean_precip_sum_3m=_float_or_nan(d["mean_precip_sum_3m"]),
        precip_index_min=int(d["precip_index_min"]),
        precip_index_max=int(d["precip_index_max"]),
        n_regions_with_precip_deficit=int(d["n_regions_with_precip_deficit"]),
        n_regions_with_soil_moisture_deficit=int(d["n_regions_with_soil_moisture_deficit"]),
        discharge=_discharge_from_dict(d["discharge"]),
    )


# ---------------------------------------------------------------------------
# HTML rendering helpers
# ---------------------------------------------------------------------------

def _slug(name: str) -> str:
    """Convert a region name to a URL-safe ASCII slug."""
    s = name.lower()
    for old, new in [
        ("ä", "ae"), ("ö", "oe"), ("ü", "ue"),
        ("é", "e"), ("è", "e"), ("ê", "e"),
        ("à", "a"), ("â", "a"), ("ç", "c"),
    ]:
        s = s.replace(old, new)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def _parse_regionen(section_text: str) -> dict[str, str]:
    """Parse ### Region Name headings from the rendered regionen section text."""
    parts = re.split(r"^###\s+(.*)$", section_text, flags=re.MULTILINE)
    result: dict[str, str] = {}
    for i in range(1, len(parts), 2):
        name = parts[i].strip()
        body = parts[i + 1].strip().replace("\n", "<br/>")
        result[name] = _html.escape(body).replace("&lt;br/&gt;", "<br/>")
    return result


def _fmt_q(q: float) -> str:
    """Format a discharge value (m³/s) with magnitude-appropriate precision."""
    if q > 20:
        return f"{q:.0f}"
    if q > 5:
        return f"{q:.1f}"
    if q > 1:
        return f"{q:.2f}"
    return f"{q:.3f}"


def _station_details_html(r: RegionReport, locale: str) -> str:
    """Per-station discharge details for the Situation column."""
    stations = [s for s in r.hydro_stations if not math.isnan(s.current_value)]
    if not stations:
        ds = r.discharge
        if ds.n_total > 0:
            return (
                f'<span style="font-size:.85rem;">'
                f"{ds.n_low}/{ds.n_total} {_html.escape(t('stations_low', locale))}"
                f'<br/><span style="color:var(--muted);">'
                f"{ds.n_very_low} {_html.escape(t('stations_very_low', locale))}"
                f"</span></span>"
            )
        return (
            f'<span style="color:var(--muted);font-size:.85rem;">'
            f"{_html.escape(t('no_stations', locale))}</span>"
        )

    lbl_q = _html.escape(t("metric_abfluss", locale))
    lbl_t1 = _html.escape(t("metric_threshold_t1", locale))
    lbl_mn = _html.escape(t("metric_threshold_min", locale))
    parts: list[str] = []
    for s in stations:
        name = _html.escape(s.station_name)
        t1_str = _fmt_q(s.threshold1) if not math.isnan(s.threshold1) else "–"
        mn_str = _fmt_q(s.min_value) if not math.isnan(s.min_value) else "–"
        parts.append(
            f'<div style="font-size:.82rem;margin-bottom:.55rem;">'
            f"<b>{name}</b><br/>"
            f"{lbl_q}: {_fmt_q(s.current_value)} m³/s<br/>"
            f"{lbl_t1}: {t1_str} m³/s<br/>"
            f"{lbl_mn}: {mn_str} m³/s"
            f"</div>"
        )
    return "".join(parts)


def _cdi_legend_html(locale: str) -> str:
    """Horizontal CDI colour legend strip, CDI 1-5, matching the BAFU map palette."""
    labels = _CDI_LEGEND_LABELS_FR if locale == "fr" else _CDI_LEGEND_LABELS
    title = _html.escape(t("map_legend_title", locale))
    items: list[str] = []
    for cdi_val, colour in sorted(_CDI_LEGEND_COLOURS.items()):
        label = _html.escape(labels.get(cdi_val, str(cdi_val)))
        items.append(
            f'<span class="cdi-legend-item">'
            f'<span class="cdi-swatch" style="background:{colour};"></span>'
            f"{label}"
            f"</span>"
        )
    return (
        f'<div style="margin-top:.75rem;">'
        f'<b style="font-size:.82rem;">{title}</b>'
        f'<div class="cdi-legend">{"".join(items)}</div>'
        f"</div>"
    )


def _generate_map_files(canton: CantonReport, out_dir: Path) -> bool:
    """
    Pre-generate Folium map HTML files for the canton.
    Returns True when both files were written; False on any error (e.g. no network).
    The generated HTML files are self-contained Leaflet pages that load WMS tiles
    from the browser — no backend required at serve time.
    """
    try:
        from src.viz.maps import build_map

        for wms_time, filename in [("1", "map_cdi1.html"), ("2", "map_cdi2.html")]:
            m = build_map(canton_id=canton.canton_id, wms_time=wms_time)
            html_str = _inject_print_resize(m.get_root().render())
            (out_dir / filename).write_text(html_str, encoding="utf-8")
        return True
    except Exception as exc:
        log.warning("Map generation skipped for canton %d: %s", canton.canton_id, exc)
        return False


_FIT_BOUNDS_RE = re.compile(
    r"\.fitBounds\(\s*"
    r"(\[\s*\[\s*[\d.\-]+\s*,\s*[\d.\-]+\s*\]\s*,\s*\[\s*[\d.\-]+\s*,\s*[\d.\-]+\s*\]\s*\])"
)


def _inject_print_resize(html: str) -> str:
    """
    Inject beforeprint + message handlers into a Folium HTML string.
    Parses the fitBounds coordinates so Leaflet re-fits to the canton on print.
    """
    m = _FIT_BOUNDS_RE.search(html)
    bounds_literal = m.group(1) if m else "null"
    script = (
        "<script>"
        "(function(){"
        f"var _b={bounds_literal};"
        "function _fit(){"
        "Object.keys(window).forEach(function(k){"
        "if(k.startsWith('map_')&&window[k]&&typeof window[k].invalidateSize==='function'){"
        "window[k].invalidateSize(true);"
        "if(_b)window[k].fitBounds(_b,{animate:false,padding:[10,10]});"
        "}"
        "});"
        "}"
        "window.addEventListener('beforeprint',_fit);"
        # parent page also sends postMessage when printing
        "window.addEventListener('message',function(e){if(e.data==='drought:beforeprint')_fit();});"
        "}());"
        "</script>"
    )
    return html.replace("</body>", script + "</body>", 1)


def _map_section_html(canton: CantonReport, has_maps: bool) -> str:
    """
    Bilingual map card with CDI/forecast radio toggle.
    Sits outside the lang-de/lang-fr divs so only two iframes are created total.
    """
    name_de = _html.escape(canton.canton_name_de)
    name_fr = _html.escape(canton.canton_name_fr)

    if has_maps:
        map_body = (
            f'<div class="map-controls">'
            f'<div class="map-radio-group">'
            f'<label>'
            f'<input type="radio" name="map-cdi" class="map-radio-btn" value="map-cdi1" checked>'
            f'<span class="lang-de">{_html.escape(t("map_cdi_current", "de"))}</span>'
            f'<span class="lang-fr">{_html.escape(t("map_cdi_current", "fr"))}</span>'
            f"</label>"
            f'<label>'
            f'<input type="radio" name="map-cdi" class="map-radio-btn" value="map-cdi2">'
            f'<span class="lang-de">{_html.escape(t("map_cdi_forecast", "de"))}</span>'
            f'<span class="lang-fr">{_html.escape(t("map_cdi_forecast", "fr"))}</span>'
            f"</label>"
            f"</div>"
            f"</div>"
            f'<iframe id="map-cdi1" class="map-frame" src="map_cdi1.html" loading="lazy"></iframe>'
            f'<iframe id="map-cdi2" class="map-frame" src="map_cdi2.html" loading="lazy"'
            f' style="display:none;"></iframe>'
        )
    else:
        map_body = (
            f'<div class="map-unavailable">'
            f'<span class="lang-de">{_html.escape(t("map_unavailable", "de"))}</span>'
            f'<span class="lang-fr">{_html.escape(t("map_unavailable", "fr"))}</span>'
            f"</div>"
        )

    legend_de = _cdi_legend_html("de")
    legend_fr = _cdi_legend_html("fr")

    return (
        f'<div class="map-card">'
        f"<h2>"
        f'<span class="lang-de">CDI-Karte {name_de}</span>'
        f'<span class="lang-fr">Carte CDI {name_fr}</span>'
        f"</h2>"
        f"{map_body}"
        f'<div id="map-print-label" class="map-print-label"></div>'
        f'<div class="lang-de">{legend_de}</div>'
        f'<div class="lang-fr">{legend_fr}</div>'
        f"</div>"
    )


def _region_table_html(doc, canton: CantonReport, sec_title: str, locale: str) -> str:
    """Render the 'regionen' section as an HTML table with correct locale labels."""
    narratives = _parse_regionen(doc.sections.get("regionen", ""))
    region_names = get_region_names(locale)

    col_canton_recs = _html.escape(t("col_canton_recs", locale))
    placeholder = _html.escape(t("expert_input_placeholder", locale))

    rows: list[str] = []
    for r in canton.regions:
        name_raw = region_names.get(r.region_id, r.region_name_de)
        region_url = (
            f"https://www.trockenheit.admin.ch/{locale}/regionen"
            f"/{r.region_id}-{_slug(name_raw)}/aktuelle-lage#index"
        )
        name_html = (
            f'<a href="{region_url}" target="_blank" rel="noopener">'
            f"{_html.escape(name_raw)}</a>"
        )

        situation = _station_details_html(r, locale)
        narrative = narratives.get(r.region_name_de, "–")

        # Screen: editable textarea. Print: sibling div that mirrors the text (no scroll cutoff).
        rec_ta = (
            f'<textarea class="canton-rec" data-region-id="{r.region_id}"'
            f' placeholder="{placeholder}" rows="3"></textarea>'
            f'<div class="canton-rec-print" id="canton-rec-print-{r.region_id}"></div>'
        )

        rows.append(
            f"<tr>"
            f"<td><span class='wl wl-{r.warnlevel}'>{r.warnlevel}</span></td>"
            f"<td><b>{name_html}</b></td>"
            f"<td>{situation}</td>"
            f"<td style='font-size:.85rem;'>{narrative}</td>"
            f"<td>{rec_ta}</td>"
            f"</tr>"
        )

    col_warnstufe = _html.escape(t("col_warnstufe", locale))
    col_region = _html.escape(t("col_region", locale))
    col_situation = _html.escape(t("col_situation", locale))
    sec_esc = _html.escape(sec_title)

    return (
        f'<div class="card">'
        f"<h2>{sec_esc}</h2>"
        f'<table class="region-table"><thead><tr>'
        f"<th>{col_warnstufe}</th><th>{col_region}</th>"
        f"<th>{col_situation}</th><th>{sec_esc}</th>"
        f"<th>{col_canton_recs}</th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table>"
        f"</div>"
    )


def _allgemeine_lage_html(doc_de, doc_fr, ruleset) -> str:
    """Render the allgemeine-lage section as a bilingual card for the grid layout."""
    sec = next((s for s in ruleset.sections if s.id == "allgemeine-lage"), None)
    text_de = doc_de.sections.get("allgemeine-lage", "")
    text_fr = doc_fr.sections.get("allgemeine-lage", "")
    if not (sec and (text_de or text_fr)):
        return ""
    title_de = _html.escape(sec.title.get("de", "Allgemeine Lage"))
    title_fr = _html.escape(sec.title.get("fr", "Situation générale"))
    return (
        f'<div class="lage-card card">'
        f'<h2 class="lang-de">{title_de}</h2>'
        f'<h2 class="lang-fr">{title_fr}</h2>'
        f'<div class="card-text lang-de">{_html.escape(text_de)}</div>'
        f'<div class="card-text lang-fr">{_html.escape(text_fr)}</div>'
        f"</div>"
    )


def _sections_html(
    doc, canton: CantonReport, ruleset, locale: str,
    skip: frozenset[str] = frozenset(),
) -> str:
    """Render all briefing sections for the given locale using CSS card classes."""
    parts: list[str] = []
    for sec in ruleset.sections:
        if sec.id in skip or sec.id not in doc.sections:
            continue
        sec_title = sec.title.get(locale, sec.title.get("de", sec.id))
        if sec.id == "regionen":
            parts.append(_region_table_html(doc, canton, sec_title, locale))
        else:
            body = _html.escape(doc.sections[sec.id])
            parts.append(
                f'<div class="card">'
                f"<h2>{_html.escape(sec_title)}</h2>"
                f'<div class="card-text">{body}</div>'
                f"</div>"
            )
    return "\n".join(parts)


def _load_sources(sources_path: Path) -> list[dict]:
    """Load data sources list from config/sources.yaml. Returns [] on error."""
    try:
        raw = yaml.safe_load(sources_path.read_text(encoding="utf-8"))
        return raw.get("data_sources", []) if isinstance(raw, dict) else []
    except Exception as exc:
        log.warning("Could not load %s: %s", sources_path, exc)
        return []


def _sources_card_html(sources: list[dict]) -> str:
    """Render data sources as a bilingual card (DE / FR toggled by JS)."""
    if not sources:
        return ""

    def _item(src: dict, lang: str) -> str:
        title_raw = src.get("title", "")
        if isinstance(title_raw, dict):
            title = _html.escape(title_raw.get(lang) or title_raw.get("de", ""))
        else:
            title = _html.escape(str(title_raw))
        provider = _html.escape(src.get("provider", ""))
        label = f"{title}: {provider}" if provider else title
        url = _html.escape(src.get("url", ""))
        return f'<li><a href="{url}" target="_blank" rel="noopener">{label}</a></li>'

    valid = [s for s in sources if s.get("url") and s.get("title")]
    items_de = "".join(_item(s, "de") for s in valid)
    items_fr = "".join(_item(s, "fr") for s in valid)
    return (
        f'<div class="card" style="margin-top:1.5rem;">'
        f'<h2>'
        f'<span class="lang-de">Datenquellen</span>'
        f'<span class="lang-fr">Sources de donn&eacute;es</span>'
        f"</h2>"
        f'<ul class="lang-de further-links">{items_de}</ul>'
        f'<ul class="lang-fr further-links">{items_fr}</ul>'
        f"</div>"
    )


def _banner_html(doc_de, doc_fr) -> str:
    parts: list[str] = []
    for locale, doc in (("de", doc_de), ("fr", doc_fr)):
        if not doc.banner:
            continue
        links = " · ".join(
            f'<a href="{_html.escape(b["url"])}">{_html.escape(b["label"])}</a>'
            for b in doc.banner
        )
        parts.append(f'<p class="banner-links lang-{locale}">{links}</p>')
    return "\n".join(parts)


def _further_links_html(doc_de, doc_fr) -> str:
    """Render weiterfuehrende_links as a bilingual card with heading."""
    def _items(doc) -> str:
        return "".join(
            f'<li><a href="{_html.escape(lk["url"])}">{_html.escape(lk["label"])}</a></li>'
            for lk in (doc.weiterfuehrende_links or [])
        )
    items_de = _items(doc_de)
    items_fr = _items(doc_fr)
    if not items_de and not items_fr:
        return ""
    return (
        f'<div class="card">'
        f'<h2 class="lang-de">Weiterf&uuml;hrende Links</h2>'
        f'<h2 class="lang-fr">Liens compl&eacute;mentaires</h2>'
        f'<ul class="lang-de further-links">{items_de}</ul>'
        f'<ul class="lang-fr further-links">{items_fr}</ul>'
        f"</div>"
    )


# ---------------------------------------------------------------------------
# Page builders
# ---------------------------------------------------------------------------

def _header_html(back_href: str) -> str:
    return f"""\
<header class="site-header">
  <div class="container header-inner">
    <a href="{back_href}" class="site-brand">
      <span class="beta-badge">BETA</span>
      <img src="{_FAVICON_URL}" width="18" height="18" alt="" aria-hidden="true"
           style="image-rendering:auto;display:block;">
      <span class="lang-de">Trockenheitsbriefing</span>
      <span class="lang-fr">Bulletin s&eacute;cheresse</span>
    </a>
    <div class="header-actions">
      <button class="action-btn lang-de" onclick="exportBriefing()">&#11015; Export Briefing</button>
      <button class="action-btn lang-fr" onclick="exportBriefing()">&#11015; Exporter le briefing</button>
      <button class="action-btn lang-de" onclick="copyPermalink()">&#128279; Link kopieren</button>
      <button class="action-btn lang-fr" onclick="copyPermalink()">&#128279; Copier le lien</button>
      <div class="lang-toggle">
        <button class="lang-btn" data-lang="de">DE</button>
        <button class="lang-btn" data-lang="fr">FR</button>
      </div>
    </div>
  </div>
</header>"""


def _footer_html() -> str:
    return """\
<footer class="site-footer">
  <div class="container">
    <p class="lang-de">Quelle: BAFU / MeteoSchweiz / swisstopo &middot;
      <a href="https://www.trockenheit.admin.ch">trockenheit.admin.ch</a></p>
    <p class="lang-fr">Source: OFEV / M&eacute;t&eacute;oSuisse / swisstopo &middot;
      <a href="https://www.trockenheit.admin.ch">trockenheit.admin.ch</a></p>
    <p class="impressum lang-de">Impressum: Automatisiertes Trockenheitsbriefing f&uuml;r Schweizer Beh&ouml;rden &ndash;
      von offenen Bundesdaten zum ver&ouml;ffentlichungsfertigen Bericht in Sekundenschnelle.
      Entwickelt am GovTech Hackathon 2026 in Zusammenarbeit mit swisstopo, BAFU (FOEN) und MeteoSchweiz.
      Team: David Oesch &middot; Joan Sturm &middot; Fabia Huesler &middot; Christopher Boodnee &middot;
      Lea Stauber &middot; Benjamin Meyer &middot; Luca Huesler &middot; Simon Jaun &middot; Chantal Camenisch</p>
    <p class="impressum lang-fr">Impressum&nbsp;: Bulletin de s&eacute;cheresse automatis&eacute; pour les autorit&eacute;s suisses &ndash;
      des donn&eacute;es ouvertes de la Conf&eacute;d&eacute;ration au rapport pr&ecirc;t &agrave; publier en quelques secondes.
      D&eacute;velopp&eacute; lors du GovTech Hackathon 2026 en collaboration avec swisstopo, l&rsquo;OFEV (BAFU) et M&eacute;t&eacute;oSuisse.
      &Eacute;quipe&nbsp;: David Oesch &middot; Joan Sturm &middot; Fabia Huesler &middot; Christopher Boodnee &middot;
      Lea Stauber &middot; Benjamin Meyer &middot; Luca Huesler &middot; Simon Jaun &middot; Chantal Camenisch</p>
  </div>
</footer>"""


def _canton_page(
    canton: CantonReport,
    doc_de,
    doc_fr,
    ruleset,
    has_maps: bool = False,
    sources: list[dict] | None = None,
) -> str:
    """Generate a bilingual canton briefing page (single HTML, language-toggled by JS)."""
    bg, fg = _WARNSTUFE_COLOURS.get(canton.max_warnlevel, ("#cccccc", "#1a1a1a"))
    ts = (
        canton.data_timestamp.strftime("%d.%m.%Y")
        if isinstance(canton.data_timestamp, datetime)
        else str(canton.data_timestamp)
    )
    q = canton.quality
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Trockenheitsbriefing {_html.escape(canton.canton_name_de)} / \
Bulletin s&eacute;cheresse {_html.escape(canton.canton_name_fr)}</title>
  <link rel="icon" href="{_FAVICON_URL}">
  <link rel="stylesheet" href="../../assets/style.css">
</head>
<body>
{_header_html("../../index.html")}

<main class="container">
  <div class="page-header">
    <h1 class="page-title lang-de">{_html.escape(canton.canton_name_de)}</h1>
    <h1 class="page-title lang-fr">{_html.escape(canton.canton_name_fr)}</h1>
    <p class="page-subtitle">
      <span class="lang-de">Trockenheitsbriefing &middot; Stand: {ts}</span>
      <span class="lang-fr">Bulletin s&eacute;cheresse &middot; &Eacute;tat: {ts}</span>
    </p>
  </div>

  <div class="lead-card" style="background:{bg};color:{fg};">
    <div class="lead-content">
      <div class="lang-de">
        <div class="lead-headline">{_html.escape(doc_de.lead_headline)}</div>
        <div class="lead-meta">{_html.escape(doc_de.lead_meta)}</div>
      </div>
      <div class="lang-fr">
        <div class="lead-headline">{_html.escape(doc_fr.lead_headline)}</div>
        <div class="lead-meta">{_html.escape(doc_fr.lead_meta)}</div>
      </div>
    </div>
    <div class="badge-large">{canton.max_warnlevel}</div>
  </div>

  {_banner_html(doc_de, doc_fr)}

  <div class="map-lage-grid">
    {_allgemeine_lage_html(doc_de, doc_fr, ruleset)}
    {_map_section_html(canton, has_maps)}
  </div>

  <div class="lang-de">
    {_sections_html(doc_de, canton, ruleset, "de", skip=frozenset({"allgemeine-lage", "datenquellen"}))}
  </div>
  <div class="lang-fr">
    {_sections_html(doc_fr, canton, ruleset, "fr", skip=frozenset({"allgemeine-lage", "datenquellen"}))}
  </div>

  {_further_links_html(doc_de, doc_fr)}

  {_sources_card_html(sources or [])}

  <div class="quality-bar">
    <span class="lang-de">
      Aktualit&auml;t: {q.data_age_days}&nbsp;Tage &middot;
      Abdeckung: {q.coverage_pct:.0%}
    </span>
    <span class="lang-fr">
      Actualit&eacute;: {q.data_age_days}&nbsp;jours &middot;
      Couverture: {q.coverage_pct:.0%}
    </span>
  </div>
</main>

{_footer_html()}
<script src="../../assets/app.js"></script>
</body>
</html>"""


def _generate_index(cantons: list[CantonReport], site_dir: Path, sources: list[dict] | None = None) -> None:
    cards: list[str] = []
    # A) Sort alphabetically by German canton name
    for c in sorted(cantons, key=lambda x: x.canton_name_de):
        abbrev = CANTON_ABBREV.get(c.canton_id, str(c.canton_id))
        ts = (
            c.data_timestamp.strftime("%d.%m.%Y")
            if isinstance(c.data_timestamp, datetime)
            else str(c.data_timestamp)
        )
        bg, fg = _WARNSTUFE_COLOURS.get(c.max_warnlevel, ("#cccccc", "#1a1a1a"))
        badge = (
            f'<span class="wl wl-{c.max_warnlevel}" '
            f'style="background:{bg};color:{fg};">'
            f"{c.max_warnlevel}</span>"
        )
        cards.append(
            f'<a href="canton/{abbrev}/index.html" class="canton-card">'
            f"{badge}"
            f'<div class="canton-card-info">'
            f'<div class="canton-name lang-de">{_html.escape(c.canton_name_de)}</div>'
            f'<div class="canton-name lang-fr">{_html.escape(c.canton_name_fr)}</div>'
            f'<div class="canton-ts">{_html.escape(ts)}</div>'
            f"</div>"
            f"</a>"
        )

    page = f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Trockenheitsbriefing / Bulletin s&eacute;cheresse</title>
  <link rel="icon" href="{_FAVICON_URL}">
  <link rel="stylesheet" href="assets/style.css">
</head>
<body>
{_header_html("#")}

<main class="container">
  <div class="page-header">
    <h1 class="page-title">
      <span class="lang-de">Aktuelle Trockenheitslage</span>
      <span class="lang-fr">Situation s&eacute;cheresse actuelle</span>
    </h1>
    <p class="page-subtitle">
      <span class="lang-de">trockenheit.admin.ch &mdash; Alle Kantone</span>
      <span class="lang-fr">trockenheit.admin.ch &mdash; Tous les cantons</span>
    </p>
  </div>
  <div class="canton-grid">
    {chr(10).join(cards)}
  </div>
  {_sources_card_html(sources or [])}
</main>

{_footer_html()}
<script src="assets/app.js"></script>
</body>
</html>"""

    (site_dir / "index.html").write_text(page, encoding="utf-8")
    log.info("  index.html")


# ---------------------------------------------------------------------------
# Main site generation logic
# ---------------------------------------------------------------------------

def generate_site(
    processed_dir: Path,
    ruleset_path: Path,
    site_dir: Path,
) -> None:
    """
    Read all canton JSONs from processed_dir, render bilingual briefing pages,
    and write the complete static site to site_dir.
    """
    canton_dir = processed_dir / "cantons"
    if not canton_dir.exists():
        log.error(
            "Cantons directory not found: %s — run scripts/aggregate.py first.", canton_dir
        )
        sys.exit(1)

    json_files = sorted(canton_dir.glob("*.json"))
    if not json_files:
        log.error("No canton JSON files found in %s.", canton_dir)
        sys.exit(1)

    log.info("Loading ruleset from %s ...", ruleset_path)
    ruleset = load_ruleset(ruleset_path)

    sources = _load_sources(SOURCES_PATH)
    log.info("Loaded %d data sources from %s", len(sources), SOURCES_PATH)

    site_dir.mkdir(parents=True, exist_ok=True)
    _write_assets(site_dir)

    # Copy processed JSON for transparency (browser can inspect, future JS use)
    site_data_dir = site_dir / "data" / "cantons"
    site_data_dir.mkdir(parents=True, exist_ok=True)

    cantons: list[CantonReport] = []
    errors: list[str] = []

    for path in json_files:
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            canton = canton_from_dict(d)
        except Exception as exc:
            log.error("Failed to load %s: %s", path.name, exc)
            errors.append(path.name)
            continue

        # Copy the processed JSON into site/data/cantons/ (keyed by numeric ID)
        shutil.copy2(path, site_data_dir / path.name)

        # C) Use the official canton abbreviation (e.g. BE, ZH) for the URL
        abbrev = CANTON_ABBREV.get(canton.canton_id, str(canton.canton_id))
        out_dir = site_dir / "canton" / abbrev
        out_dir.mkdir(parents=True, exist_ok=True)

        has_maps = _generate_map_files(canton, out_dir)

        try:
            doc_de = render_briefing(canton, ruleset, locale="de")
            doc_fr = render_briefing(canton, ruleset, locale="fr")
            page_html = _canton_page(
                canton, doc_de, doc_fr, ruleset,
                has_maps=has_maps, sources=sources,
            )
            (out_dir / "index.html").write_text(page_html, encoding="utf-8")
            log.info("  canton/%s/index.html  (maps=%s)", abbrev, has_maps)
        except Exception as exc:
            log.error("Failed to render canton %s: %s", abbrev, exc)
            errors.append(path.name)

        cantons.append(canton)

    if cantons:
        _generate_index(cantons, site_dir, sources=sources)

    if errors:
        log.error("Site generation completed with %d error(s): %s", len(errors), errors)
        sys.exit(1)

    log.info("Static site written to %s (%d cantons)", site_dir, len(cantons))


def main() -> None:
    generate_site(PROCESSED_DIR, RULESET_PATH, SITE_DIR)


if __name__ == "__main__":
    main()

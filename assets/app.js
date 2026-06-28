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

  /* ---- feedback popover ---- */
  window.toggleFeedback = function (e) {
    e.stopPropagation();
    var pop = e.currentTarget.closest('.feedback-wrap').querySelector('.feedback-popover');
    var isOpen = pop.classList.contains('open');
    document.querySelectorAll('.feedback-popover.open').forEach(function (p) { p.classList.remove('open'); });
    if (!isOpen) pop.classList.add('open');
  };
  document.addEventListener('click', function () {
    document.querySelectorAll('.feedback-popover.open').forEach(function (p) { p.classList.remove('open'); });
  });

  /* ---- canton recommendation textareas (no persistence — always start empty) ---- */
  function initCantonRecs() {
    document.querySelectorAll('.canton-rec').forEach(function (ta) {
      ta.addEventListener('input', function () {
        var id = ta.dataset.regionId;
        var val = ta.value;
        /* Sync to the DE+FR twin textarea so switching language keeps the text */
        document.querySelectorAll('.canton-rec[data-region-id="' + id + '"]').forEach(function (other) {
          if (other !== ta) other.value = val;
        });
        /* Update all print divs for this region (one per language) */
        document.querySelectorAll('[id="canton-rec-print-' + id + '"]').forEach(function (div) {
          div.textContent = val;
        });
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

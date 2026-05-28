# src/export/report.py
from __future__ import annotations

import html

from src.i18n.strings import t
from src.models import BriefingDocument, CantonReport

_WARNSTUFE_PALETTE: dict[int, tuple[str, str]] = {
    1: ("#6bbd50", "#ffffff"),
    2: ("#f7e84c", "#1a1a1a"),
    3: ("#ff8c00", "#ffffff"),
    4: ("#e02020", "#ffffff"),
    5: ("#8b0000", "#ffffff"),
}


def to_html(
    doc: BriefingDocument,
    canton_report: CantonReport,
    ruleset: "RulesetSchema | None" = None,
    chart_fig=None,
    map_png: bytes | None = None,
) -> str:
    # Fix 4: Locale-aware title and canton label
    canton_label = (
        canton_report.canton_name_fr if doc.locale == "fr" else canton_report.canton_name_de
    )
    title_prefix = t("export_doc_title", doc.locale)
    title = f"{title_prefix} {canton_label}"

    # Fix 1: Per-level WCAG-compliant text colour
    bg, fg = _WARNSTUFE_PALETTE.get(canton_report.max_warnlevel, ("#cccccc", "#1a1a1a"))
    # Fix 2: html.escape on all user strings in badge
    badge_html = (
        f'<div style="background:{bg};color:{fg};padding:14px;border-radius:6px;">'
        f'<div style="font-size:24px;font-weight:700;">{html.escape(doc.lead_headline)}</div>'
        f'<div style="font-size:11px;opacity:.85;">{html.escape(doc.lead_meta)}</div>'
        f'</div>'
    )

    # Fix 3: Section titles from ruleset (human-readable), falling back to sec_id keys
    if ruleset is not None:
        sections_html = "\n".join(
            f'<section>'
            f'<h2>{html.escape(sec.title.get(doc.locale, sec.title.get("de", sec.id)))}</h2>'
            f'<div>{html.escape(doc.sections[sec.id])}</div>'
            f'</section>'
            for sec in ruleset.sections
            if sec.id in doc.sections
        )
    else:
        # Fallback: use sec_id keys (backward compat when ruleset not passed)
        sections_html = "\n".join(
            f'<section><h2>{html.escape(sec_id)}</h2><div>{body}</div></section>'
            for sec_id, body in doc.sections.items()
        )

    # Fix 6: Quality summary block
    q = canton_report.quality
    quality_html = (
        f'<section class="quality">'
        f'<h2>{html.escape(t("quality_expander", doc.locale))}</h2>'
        f'<p>{html.escape(t("data_age", doc.locale))}: {q.data_age_days} {html.escape(t("days", doc.locale))} · '
        f'{html.escape(t("coverage", doc.locale))}: {q.coverage_pct:.0%}</p>'
        f'</section>'
    )

    return f"""<!DOCTYPE html>
<html lang="{html.escape(doc.locale)}">
<head><meta charset="UTF-8"><title>{html.escape(title)}</title></head>
<body>
<header><h1>{html.escape(title)}</h1>{badge_html}</header>
<main>{sections_html}
{quality_html}</main>
</body>
</html>"""

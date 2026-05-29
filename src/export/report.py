# src/export/report.py
from __future__ import annotations

import html
import math
import re

from src.i18n.strings import get_cdi_labels, get_region_names, t
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
    expert_notes: dict[str, str] | None = None,
) -> str:
    expert_notes = expert_notes or {}
    
    canton_label = (
        canton_report.canton_name_fr if doc.locale == "fr" else canton_report.canton_name_de
    )
    title_prefix = t("export_doc_title", doc.locale)
    title = f"{title_prefix} {canton_label}"

    bg, fg = _WARNSTUFE_PALETTE.get(canton_report.max_warnlevel, ("#cccccc", "#1a1a1a"))
    badge_html = (
        f'<div style="background:{bg};color:{fg};padding:14px;border-radius:6px;">'
        f'<div style="font-size:24px;font-weight:700;">{html.escape(doc.lead_headline)}</div>'
        f'<div style="font-size:11px;opacity:.85;">{html.escape(doc.lead_meta)}</div>'
        f'</div>'
    )

    # Extract narratives from the generated Markdown for the table
    regional_narratives = {}
    if "regionen" in doc.sections:
        parts = re.split(r'^###\s+(.*)$', doc.sections["regionen"], flags=re.MULTILINE)
        for i in range(1, len(parts), 2):
            r_name = parts[i].strip()
            r_text = parts[i+1].strip().replace('\n', '<br/>')
            # Escape HTML but preserve the `<br/>` tags we just injected
            regional_narratives[r_name] = html.escape(r_text).replace("&lt;br/&gt;", "<br/>")

    region_names = get_region_names(doc.locale)
    cdi_labels = get_cdi_labels(doc.locale)
    
    sections_html_parts = []

    if ruleset is not None:
        iterable_sections = [(sec.id, sec.title.get(doc.locale, sec.title.get("de", sec.id))) for sec in ruleset.sections if sec.id in doc.sections]
    else:
        iterable_sections = [(sec_id, sec_id) for sec_id in doc.sections.keys()]

    for sec_id, sec_title in iterable_sections:
        if sec_id == "regionen":
            # Intercept "regionen" to build the HTML table rather than outputting raw text
            table_html = [
                f'<section><h2>{html.escape(sec_title)}</h2>',
                "<table style='width: 100%; text-align: left; border-collapse: collapse; font-family: sans-serif;'>",
                "<thead><tr style='border-bottom: 2px solid #ddd; background-color: rgba(0,0,0,0.05);'>",
                f"<th style='padding: 12px 8px; width: 10%;'>{html.escape(t('col_warnstufe', doc.locale))}</th>",
                f"<th style='padding: 12px 8px; width: 15%;'>{html.escape(t('col_region', doc.locale))}</th>",
                f"<th style='padding: 12px 8px; width: 20%;'>{html.escape(t('col_situation', doc.locale))}</th>",
                f"<th style='padding: 12px 8px; width: 30%;'>{html.escape(sec_title)}</th>",
                f"<th style='padding: 12px 8px; width: 25%;'>{html.escape(t('col_canton_recs', doc.locale))}</th>",
                "</tr></thead><tbody>"
            ]

            for r in canton_report.regions:
                rbg, rfg = _WARNSTUFE_PALETTE.get(r.warnlevel, ("#cccccc", "#1a1a1a"))
                badge = f"<div style='background:{rbg}; color:{rfg}; padding:6px; border-radius:6px; text-align:center; font-weight:bold; width:max-content; min-width:30px;'>{r.warnlevel}</div>"
                
                name_raw = region_names.get(r.region_id, r.region_name_de)
                slug = name_raw.lower()
                slug = slug.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
                slug = slug.replace("é", "e").replace("è", "e").replace("ê", "e")
                slug = slug.replace("à", "a").replace("â", "a").replace("ç", "c")
                slug = re.sub(r'[^a-z0-9]+', '-', slug).strip('-')
                region_url = f"https://www.trockenheit.admin.ch/{doc.locale}/regionen/{r.region_id}-{slug}/aktuelle-lage#index"
                
                name_html = f"<a href='{region_url}' target='_blank' style='color: inherit; text-decoration: underline;'>{html.escape(name_raw)}</a>"
                
                # Discharge stats summary
                ds = r.discharge
                if ds.n_total > 0:
                    situation = (
                        f"<span style='font-size:13px;'>"
                        f"{ds.n_low}/{ds.n_total} Stationen tief"
                        f"<br/><span style='color:#555;'>{ds.n_very_low} sehr tief</span>"
                        f"</span>"
                    )
                else:
                    situation = "<span style='color:#999; font-size: 13px;'>Keine Stationen/Daten</span>"
                
                narrative = regional_narratives.get(r.region_name_de, "–")
                
                expert_val = html.escape(expert_notes.get(f"expert_{r.region_id}", "")).strip()
                if not expert_val:
                    expert_val = f"<span style='color:#999;'>—</span>"
                else:
                    expert_val = expert_val.replace("\n", "<br/>")

                table_html.append(
                    f"<tr style='border-bottom: 1px solid #eee; vertical-align: top;'>"
                    f"<td style='padding: 16px 8px;'>{badge}</td>"
                    f"<td style='padding: 16px 8px;'><b>{name_html}</b></td>"
                    f"<td style='padding: 16px 8px; font-size: 14px;'>{situation}</td>"
                    f"<td style='padding: 16px 8px; font-size: 14px; line-height: 1.4;'>{narrative}</td>"
                    f"<td style='padding: 16px 8px; font-size: 14px; line-height: 1.4;'>{expert_val}</td>"
                    f"</tr>"
                )
            table_html.append("</tbody></table></section>")
            sections_html_parts.append("".join(table_html))
        else:
            body = html.escape(doc.sections[sec_id])
            sections_html_parts.append(
                f'<section>'
                f'<h2>{html.escape(sec_title)}</h2>'
                f'<div>{body}</div>'
                f'</section>'
            )

    sections_html = "\n".join(sections_html_parts)

    # Banner link row (top) and weiterführende Links (bottom)
    banner_html = " · ".join(
        f'<a href="{html.escape(b["url"])}">{html.escape(b["label"])}</a>'
        for b in doc.banner
    )
    banner_block = f'<p class="banner">{banner_html}</p>' if banner_html else ""
    links_items = "".join(
        f'<li><a href="{html.escape(link["url"])}">{html.escape(link["label"])}</a></li>'
        for link in doc.weiterfuehrende_links
    )
    links_block = f'<section class="links"><ul>{links_items}</ul></section>' if links_items else ""

    # Quality summary block
    q = canton_report.quality
    quality_html = (
        f'<section class="quality" style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #eee;">'
        f'<h2>{html.escape(t("quality_expander", doc.locale))}</h2>'
        f'<p>{html.escape(t("data_age", doc.locale))}: {q.data_age_days} {html.escape(t("days", doc.locale))} · '
        f'{html.escape(t("coverage", doc.locale))}: {q.coverage_pct:.0%}</p>'
        f'</section>'
    )

    return f"""<!DOCTYPE html>
<html lang="{html.escape(doc.locale)}">
<head>
    <meta charset="UTF-8">
    <title>{html.escape(title)}</title>
    <style>
        body {{ font-family: sans-serif; margin: 2rem; color: #1a1a1a; }}
        h1, h2 {{ color: #1a1a1a; }}
        section {{ margin-bottom: 2rem; }}
    </style>
</head>
<body>
<header><h1>{html.escape(title)}</h1>{badge_html}{banner_block}</header>
<main>{sections_html}
{links_block}
{quality_html}</main>
</body>
</html>"""
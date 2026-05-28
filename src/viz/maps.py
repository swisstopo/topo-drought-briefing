# src/viz/maps.py
"""
Two map renderers:
  build_map()        -> interactive folium.Map for Streamlit (st_folium)
  build_export_map() -> static PNG bytes via matplotlib/geopandas (for PDF export)
"""
from __future__ import annotations

import io

import folium
import geopandas as gpd
import matplotlib.pyplot as plt

from config.settings import BERNE_REGION_NAMES, CDI_COLOURS, GEOJSON_FIXTURE
from src.models import RegionReport


def _load_geodataframe() -> gpd.GeoDataFrame:
    if GEOJSON_FIXTURE.exists():
        return gpd.read_file(GEOJSON_FIXTURE)
    raise FileNotFoundError(f"GeoJSON fixture not found: {GEOJSON_FIXTURE}")


def build_map(
    selected_report: RegionReport,
    all_reports: list[RegionReport],
) -> folium.Map:
    gdf = _load_geodataframe()
    cdi_by_id = {r.region_id: r.cdi for r in all_reports}

    m = folium.Map(
        location=[46.80, 7.55],
        zoom_start=9,
        tiles="CartoDB dark_matter",
    )

    def style_fn(feature):
        rid = feature["properties"]["drought_region_id"]
        cdi = cdi_by_id.get(rid, 0)
        is_selected = rid == selected_report.region_id
        return {
            "fillColor": CDI_COLOURS.get(cdi, "#cccccc"),
            "color": "#ffffff" if is_selected else "#888888",
            "weight": 3 if is_selected else 1,
            "fillOpacity": 0.75,
        }

    folium.GeoJson(
        gdf.__geo_interface__,
        style_function=style_fn,
        tooltip=folium.GeoJsonTooltip(
            fields=["drought_region_id", "name_de"],
            aliases=["Region-ID:", "Name:"],
        ),
    ).add_to(m)

    return m


def build_export_map(
    selected_report: RegionReport,
    all_reports: list[RegionReport],
) -> bytes:
    """Returns PNG bytes of a static choropleth map for use in HTML/PDF export."""
    gdf = _load_geodataframe()
    cdi_by_id = {r.region_id: r.cdi for r in all_reports}
    gdf = gdf.copy()
    gdf["cdi"] = gdf["drought_region_id"].map(cdi_by_id).fillna(0).astype(int)
    gdf["colour"] = gdf["cdi"].map(CDI_COLOURS).fillna("#cccccc")
    gdf["edge_width"] = gdf["drought_region_id"].apply(
        lambda rid: 2.5 if rid == selected_report.region_id else 0.8
    )

    fig, ax = plt.subplots(figsize=(6, 4), facecolor="#0d1117")
    ax.set_facecolor("#0d1117")

    for _, row in gdf.iterrows():
        gpd.GeoDataFrame([row], geometry="geometry", crs=gdf.crs).plot(
            ax=ax,
            color=row["colour"],
            edgecolor="#ffffff" if row["drought_region_id"] == selected_report.region_id else "#666666",
            linewidth=row["edge_width"],
            alpha=0.85,
        )
        cx = row["geometry"].centroid.x
        cy = row["geometry"].centroid.y
        name = BERNE_REGION_NAMES.get(row["drought_region_id"], "")
        short_name = name.replace("Berner ", "").replace("Westliches ", "W.").replace("Östliches ", "Ö.")
        ax.text(cx, cy, f"{short_name}\nCDI {row['cdi']}", ha="center", va="center",
                fontsize=5, color="white", fontweight="bold")

    ax.set_axis_off()
    ax.set_title("CDI-Karte Kanton Bern", color="white", fontsize=9, pad=6)
    plt.tight_layout(pad=0.5)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight", facecolor="#0d1117")
    plt.close(fig)
    buf.seek(0)
    return buf.read()
